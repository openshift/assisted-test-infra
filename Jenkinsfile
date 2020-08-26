String cron_string = BRANCH_NAME == "master" ? "@hourly" : ""

pipeline {
    agent { label 'test-infra' }

    parameters {
        string(name: 'SERVICE', defaultValue: 'quay.io/ocpmetal/assisted-service:latest', description: 'assisted-service image to use for test')
        string(name: 'INVENTORY_BRANCH', defaultValue: 'master', description: 'assisted-service branch')
        string(name: 'INVENTORY_REPO', defaultValue: 'https://github.com/openshift/assisted-service', description: 'assisted service repository')
        string(name: 'KUBECONFIG_GENERATE_IMAGE', defaultValue: '', description: 'ignition-manifests-and-kubeconfig-generate image ')
        string(name: 'INSTALLER_IMAGE', defaultValue: '', description: 'installer image to use')
        string(name: 'DEPLOY_TAG', defaultValue: '', description: 'Deploy tag')
        string(name: 'NUM_WORKERS', defaultValue: "2", description: 'Number of workers')
    }

    triggers { cron(cron_string) }


    environment {
        SKIPPER_PARAMS = " "
        PULL_SECRET = credentials('7f094807-fac7-4e47-9ed1-407dd9bf72cd')
        OCPMETAL_CREDS = credentials('docker_ocpmetal_cred')
        SLACK_TOKEN = credentials('slack-token')
    }
    options {
      timeout(time: 1, unit: 'HOURS')
    }

    stages {
        stage('Init') {
            steps {
                sh "make delete_all_virsh_resources || true"
                sh "make create_full_environment"

                // Login
                sh "minikube ssh \"docker login --username ${OCPMETAL_CREDS_USR} --password ${OCPMETAL_CREDS_PSW}\""
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
            sh '''
                echo '{"text":"Seems like one or more tests fail in the assisted-test-infra tests, Check' > data.txt
	            echo ${BUILD_URL} >> data.txt
                echo '"}' >> data.txt

                curl -X POST -H 'Content-type: application/json' --data-binary "@data.txt"  https://hooks.slack.com/services/$SLACK_TOKEN
            '''
        }

        always {
            sh '''
                kubectl get pods -A

                # Get assisted-service log
                kubectl  get pods -o=custom-columns=NAME:.metadata.name -A | grep assisted-service | xargs -I {} sh -c "kubectl logs {} -n  assisted-installer > test_dd.log"
                mv test_dd.log ${WORKSPACE}/${BUILD_NUMBER}-assisted-service.log || true

                # Get mariadb log
                kubectl  get pods -o=custom-columns=NAME:.metadata.name -A | grep mariadb | xargs -I {} sh -c "kubectl logs {} -n  assisted-installer > test_dd.log"
                mv test_dd.log ${WORKSPACE}/${BUILD_NUMBER}-mariadb.log || true

                # Get createimage log
                kubectl  get pods -o=custom-columns=NAME:.metadata.name -A | grep createimage | xargs -I {} sh -c "kubectl logs {} -n  assisted-installer > test_dd.log"
                mv test_dd.log ${WORKSPACE}/${BUILD_NUMBER}-createimage.log || true

                # Get controller log
                kubectl  get pods -o=custom-columns=NAME:.metadata.name -A | grep controller | xargs -I {} sh -c "kubectl logs {} -n  kube-system > test_dd.log"
                mv test_dd.log ${WORKSPACE}/${BUILD_NUMBER}-assisted-installer-controller.log || true

                # Get generate-kubeconfig logs
                kubectl  get pods -o=custom-columns=NAME:.metadata.name -A | grep ignition-generator| xargs -I {} sh -c "kubectl logs {} -n  assisted-installer > test_dd.log"
                mv test_dd.log ${WORKSPACE}/${BUILD_NUMBER}-ignition-generator.log || true
            '''
        }
    }
}
