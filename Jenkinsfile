String cron_string = BRANCH_NAME == "master" ? "@hourly" : ""


pipeline {
    agent { label 'test-infra' }

    parameters {
        string(name: 'SERVICE', defaultValue: 'quay.io/ocpmetal/assisted-service:latest', description: 'assisted-service image to use for test')
        string(name: 'SERVICE_BRANCH', defaultValue: 'master', description: 'assisted-service branch')
        string(name: 'SERVICE_REPO', defaultValue: 'https://github.com/openshift/assisted-service', description: 'assisted service repository')
        string(name: 'INSTALLER_IMAGE', defaultValue: '', description: 'Installer image to use')
        string(name: 'CONTROLLER_IMAGE', defaultValue: '', description: 'Controller image to use')
        string(name: 'OPENSHIFT_INSTALL_RELEASE_IMAGE', defaultValue: '', description: 'OCP Release Image from ocpmetal repository in Quay.io')
        string(name: 'OPENSHIFT_VERSION', defaultValue: '', description: 'OCP version going to be installed')
        string(name: 'OPENSHIFT_VERSIONS', defaultValue: '', description: 'Hashmap of all the supported OCP versions. Defaults in https://github.com/openshift/assisted-service/blob/master/default_ocp_versions.json')
        string(name: 'DEPLOY_TAG', defaultValue: '', description: 'Deploy tag')
        string(name: 'NUM_WORKERS', defaultValue: "2", description: 'Number of workers')
        string(name: 'JOB_NAME', defaultValue: "#${BUILD_NUMBER}", description: 'Job name')
        booleanParam(name: 'NOTIFY', defaultValue: true, description: 'Notify on fail (on master branch)')
        booleanParam(name: 'POST_DELETE', defaultValue: true, description: 'Whether to delete the cluster on post actions')
    }

    triggers { cron(cron_string) }

    environment {
        SKIPPER_PARAMS = " "
        BASE_DNS_DOMAINS = credentials('route53_dns_domain')
        ROUTE53_SECRET = credentials('route53_secret')
        RUN_ID = UUID.randomUUID().toString().take(8)
        PROFILE = "test-infra-${RUN_ID}"
        NAMESPACE = "test-infra-${RUN_ID}"
        LOGS_DEST = "${WORKSPACE}/cluster_logs"

        // Credentials
        PULL_SECRET = credentials('assisted-test-infra-pull-secret-no-svc')
        OCPMETAL_CREDS = credentials('docker_ocpmetal_cred')
        SLACK_TOKEN = credentials('slack-token')
    }
    options {
      timeout(time: 2, unit: 'HOURS')
    }

    stages {
        stage('Init') {
            steps {
                script {
                    currentBuild.displayName = "${JOB_NAME}"
                }
                sh "make clean"
                sh "make image_build"
                sh "make create_full_environment"

                // Login
                sh "minikube --profile ${PROFILE} ssh \"docker login --username ${OCPMETAL_CREDS_USR} --password ${OCPMETAL_CREDS_PSW}\""
            }
        }

        stage('Test') {
            steps {
                sh "make run_full_flow_with_install"
            }
        }
    }

    post {
         always {
            script {
                if ((env.BRANCH_NAME == 'master') && params.NOTIFY && (currentBuild.currentResult == "ABORTED" || currentBuild.currentResult == "FAILURE")){
                    script {
                        def data = [text: "Attention! ${BUILD_TAG} job failed, see: ${BUILD_URL}"]
                        writeJSON(file: 'data.txt', json: data, pretty: 4)
                    }
                    sh '''curl -X POST -H 'Content-type: application/json' --data-binary "@data.txt"  https://hooks.slack.com/services/${SLACK_TOKEN}'''
                }

                try {
                    ip = sh(returnStdout: true, script: "minikube ip --profile ${PROFILE}").trim()
                    minikube_url = "https://${ip}:8443"

                    sh "make download_service_logs KUBECTL='kubectl --server=${minikube_url}'"
                    sh "make download_cluster_logs ADDITIONAL_PARAMS='--download-all' KUBECTL='kubectl --server=${minikube_url}'"
                } finally {
                    if (params.POST_DELETE) {
                        sh "make destroy"
                    }
                }
            }

            archiveArtifacts artifacts: '*.log', fingerprint: true
            archiveArtifacts artifacts: 'cluster_logs/**/**', fingerprint: true
        }
    }
}
