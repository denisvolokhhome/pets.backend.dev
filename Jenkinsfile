pipeline {
    agent any

    environment {
        HARBOR_REGISTRY = '192.168.68.110:80'
        IMAGE_NAME = 'breedly/breedly-backend'
        HARBOR_CREDS = credentials('harbor-credentials')
    }

    stages {
        stage('Login to Harbor') {
            steps {
                sh 'echo $HARBOR_CREDS_PSW | docker login $HARBOR_REGISTRY -u $HARBOR_CREDS_USR --password-stdin'
            }
        }

        stage('Build') {
            steps {
                sh """
                    docker build \
                        --platform linux/amd64 \
                        -t ${HARBOR_REGISTRY}/${IMAGE_NAME}:latest \
                        -t ${HARBOR_REGISTRY}/${IMAGE_NAME}:${BUILD_NUMBER} \
                        -f deploy/Dockerfile \
                        .
                """
            }
        }

        stage('Push') {
            steps {
                sh "docker push ${HARBOR_REGISTRY}/${IMAGE_NAME}:latest"
                sh "docker push ${HARBOR_REGISTRY}/${IMAGE_NAME}:${BUILD_NUMBER}"
            }
        }
    }

    post {
        always {
            sh "docker rmi ${HARBOR_REGISTRY}/${IMAGE_NAME}:latest || true"
            sh "docker rmi ${HARBOR_REGISTRY}/${IMAGE_NAME}:${BUILD_NUMBER} || true"
        }
    }
}
