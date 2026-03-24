pipeline {
    agent any

    environment {
        HARBOR_REGISTRY = '192.168.68.110:80'
        IMAGE_NAME = 'breedly/breedly-backend'
        HARBOR_USER = credentials('harbor-username')
        HARBOR_PASS = credentials('harbor-password')
        VM_CREDS = credentials('vm-ssh-credentials')
    }

    stages {
        stage('Login to Harbor') {
            steps {
                echo "Logging in to Harbor registry at ${HARBOR_REGISTRY}..."
                sh 'echo "$HARBOR_PASS" | docker login $HARBOR_REGISTRY -u "$HARBOR_USER" --password-stdin'
                echo "Harbor login successful"
            }
        }

        stage('Build') {
            steps {
                echo "Building Docker image: ${HARBOR_REGISTRY}/${IMAGE_NAME}:${BUILD_NUMBER}"
                echo "Platform: linux/amd64"
                echo "Dockerfile: deploy/Dockerfile"
                sh """
                    docker build \
                        --platform linux/amd64 \
                        -t ${HARBOR_REGISTRY}/${IMAGE_NAME}:latest \
                        -t ${HARBOR_REGISTRY}/${IMAGE_NAME}:${BUILD_NUMBER} \
                        -f deploy/Dockerfile \
                        .
                """
                echo "Docker image built successfully"
                sh "docker images ${HARBOR_REGISTRY}/${IMAGE_NAME} --format 'table {{.Repository}}\\t{{.Tag}}\\t{{.Size}}'"
            }
        }

        stage('Push') {
            steps {
                echo "Pushing image to Harbor..."
                sh "docker push ${HARBOR_REGISTRY}/${IMAGE_NAME}:latest"
                echo "Pushed :latest"
                sh "docker push ${HARBOR_REGISTRY}/${IMAGE_NAME}:${BUILD_NUMBER}"
                echo "Pushed :${BUILD_NUMBER}"
                echo "All images pushed to Harbor successfully"
            }
        }

        stage('Deploy to Dev') {
            steps {
                echo "Deploying to dev server at 192.168.68.113..."
                script {
                    def remote = [:]
                    remote.name = 'breedly-vm'
                    remote.host = '192.168.68.113'
                    remote.user = VM_CREDS_USR
                    remote.password = VM_CREDS_PSW
                    remote.allowAnyHosts = true

                    echo "Copying docker-compose.yml and .env to dev server..."
                    sshCommand remote: remote, command: 'mkdir -p /home/breedly/breedly-app'
                    sshPut remote: remote, from: 'delivery/docker-compose.yml', into: '/home/breedly/breedly-app/'
                    sshPut remote: remote, from: 'delivery/.env', into: '/home/breedly/breedly-app/'

                    echo "Logging into Harbor on dev server..."
                    sshCommand remote: remote, command: "echo '${HARBOR_PASS}' | docker login ${HARBOR_REGISTRY} -u '${HARBOR_USER}' --password-stdin"

                    echo "Pulling latest backend image on dev server..."
                    sshCommand remote: remote, command: 'cd /home/breedly/breedly-app && docker compose pull backend migration seed'

                    echo "Restarting services (includes migration + seed)..."
                    sshCommand remote: remote, command: 'cd /home/breedly/breedly-app && docker compose up -d'

                    echo "Waiting for services to stabilize..."
                    sshCommand remote: remote, command: 'sleep 15 && cd /home/breedly/breedly-app && docker compose ps'
                }
                echo "Deployment to dev server complete"
            }
        }
    }

    post {
        always {
            echo "Cleaning up local images..."
            sh "docker rmi ${HARBOR_REGISTRY}/${IMAGE_NAME}:latest || true"
            sh "docker rmi ${HARBOR_REGISTRY}/${IMAGE_NAME}:${BUILD_NUMBER} || true"
        }
        success {
            echo "Pipeline completed successfully! Backend deployed to https://api.dev.breedly.us"
        }
        failure {
            echo "Pipeline failed. Check logs above for details."
        }
    }
}
