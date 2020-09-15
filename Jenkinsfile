String cron_string = BRANCH_NAME == "master" ? "@hourly" : ""


pipeline {
    agent { label 'test-infra' }

    parameters {
        string(name: 'SERVICE', defaultValue: 'quay.io/ocpmetal/assisted-service:latest', description: 'assisted-service image to use for test')
        string(name: 'SERVICE_BRANCH', defaultValue: 'master', description: 'assisted-service branch')
        string(name: 'SERVICE_REPO', defaultValue: 'https://github.com/openshift/assisted-service', description: 'assisted service repository')
        string(name: 'IGNITION_GENERATE_IMAGE', defaultValue: '', description: 'assisted-ignition-generator image')
        string(name: 'INSTALLER_IMAGE', defaultValue: '', description: 'installer image to use')
        string(name: 'DEPLOY_TAG', defaultValue: '', description: 'Deploy tag')
        string(name: 'NUM_WORKERS', defaultValue: "2", description: 'Number of workers')
    }

    triggers { cron(cron_string) }

    environment {
        SKIPPER_PARAMS = " "
        PULL_SECRET = credentials('assisted-test-infra-pull-secret')
        OCPMETAL_CREDS = credentials('docker_ocpmetal_cred')
        SLACK_TOKEN = credentials('slack-token')
        BASE_DNS_DOMAINS = credentials('route53_dns_domain')
        ROUTE53_SECRET = credentials('route53_secret')
        RUN_ID = UUID.randomUUID().toString().take(8)
        PROFILE = "${RUN_ID}"
        NAMESPACE = "${RUN_ID}"
    }
    options {
      timeout(time: 1, unit: 'HOURS')
    }

    stages {
        stage('Init') {
            steps {
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
        failure {
            script {
                if (env.BRANCH_NAME == 'master') {
                    script {
                        def data = [text: "Attention! assisted-test-infra branch  test failed, see: ${BUILD_URL}"]
                        writeJSON(file: 'data.txt', json: data, pretty: 4)
                    }
                    sh '''curl -X POST -H 'Content-type: application/json' --data-binary "@data.txt"  https://hooks.slack.com/services/${SLACK_TOKEN}'''
                }
            }
        }

        always {
            script {
                ip = sh(returnStdout: true, script: "minikube ip --profile ${PROFILE}").trim()
                minikube_url = "https://${ip}:8443"

                sh "kubectl --server=${minikube_url} get pods -A"


                for (service in ["assisted-service","postgres","scality","createimage"]) {
                    sh "kubectl --server=${minikube_url} get pods -o=custom-columns=NAME:.metadata.name -A | grep ${service} | xargs -r -I {} sh -c \"kubectl --server=${minikube_url} logs {} -n ${NAMESPACE} > {}.log\" || true"
                }

                sh "make destroy"
            }

            archiveArtifacts artifacts: '*.log', fingerprint: true
        }
    }
}
