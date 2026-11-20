// CI/CD pipeline for the Disaster Response Resource Coordinator backend.
// Requires a Linux agent with Python 3.12+, Docker (with the compose plugin) and the JUnit plugin.
pipeline {
    agent any

    options {
        timestamps()
        disableConcurrentBuilds()
        buildDiscarder(logRotator(numToKeepStr: '20'))
        timeout(time: 30, unit: 'MINUTES')
    }

    environment {
        IMAGE_NAME = 'disaster-response-backend'
        IMAGE_TAG  = "${env.BUILD_NUMBER}"
        VENV       = '.venv'
        REPORTS    = 'reports'
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
                sh 'git log -1 --oneline'
            }
        }

        stage('Install Dependencies') {
            steps {
                sh '''
                    python3 -m venv "$VENV"
                    . "$VENV/bin/activate"
                    pip install --upgrade pip
                    pip install -r requirements-dev.txt
                '''
            }
        }

        stage('Run Tests') {
            steps {
                sh '''
                    . "$VENV/bin/activate"
                    mkdir -p "$REPORTS"
                    python -m pytest \
                        --junitxml="$REPORTS/junit.xml" \
                        --cov=app \
                        --cov-report=term \
                        --cov-report=xml:"$REPORTS/coverage.xml" \
                        --cov-report=html:"$REPORTS/coverage-html"
                '''
            }
            post {
                always {
                    // Publish results even when tests fail, so failures are visible in Jenkins.
                    junit allowEmptyResults: true, testResults: "${REPORTS}/junit.xml"
                }
            }
        }

        stage('Generate Test Reports') {
            steps {
                sh '''
                    . "$VENV/bin/activate"
                    python - <<'EOF'
import xml.etree.ElementTree as ET
suite = ET.parse("reports/junit.xml").getroot()
suite = suite if suite.tag == "testsuite" else suite.find("testsuite")
cov = ET.parse("reports/coverage.xml").getroot()
summary = (
    f"Tests: {suite.get('tests')}  Failures: {suite.get('failures')}  "
    f"Errors: {suite.get('errors')}  Skipped: {suite.get('skipped')}  Time: {suite.get('time')}s\\n"
    f"Line coverage: {float(cov.get('line-rate')) * 100:.1f}%\\n"
)
open("reports/summary.txt", "w").write(summary)
print(summary)
EOF
                '''
                archiveArtifacts artifacts: "${REPORTS}/**", fingerprint: true
            }
        }

        stage('Build Docker Image') {
            steps {
                sh 'docker build -t "$IMAGE_NAME:$IMAGE_TAG" -t "$IMAGE_NAME:latest" .'
            }
        }

        stage('Deployment Preparation') {
            steps {
                sh '''
                    # 1. Validate the compose file (uses the example env when no .env exists on the agent).
                    [ -f .env ] || cp .env.example .env
                    docker compose config --quiet

                    # 2. Smoke-test the built image: migrations run, server starts, health endpoint answers.
                    SMOKE="drrc-smoke-$BUILD_NUMBER"
                    docker rm -f "$SMOKE" >/dev/null 2>&1 || true
                    docker run -d --name "$SMOKE" \
                        -e SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')" \
                        -e JWT_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')" \
                        "$IMAGE_NAME:$IMAGE_TAG"
                    ok=0
                    for i in $(seq 1 20); do
                        if docker exec "$SMOKE" python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/api/health', timeout=3)" 2>/dev/null; then
                            ok=1; break
                        fi
                        sleep 2
                    done
                    docker logs "$SMOKE" | tail -n 20
                    docker rm -f "$SMOKE" >/dev/null
                    [ "$ok" = "1" ] || { echo "Smoke test failed: health check did not pass"; exit 1; }

                    # 3. Record the release manifest; push only when a registry is configured.
                    echo "$IMAGE_NAME:$IMAGE_TAG" > "$REPORTS/image-tag.txt"
                    if [ -n "$DOCKER_REGISTRY" ]; then
                        docker tag "$IMAGE_NAME:$IMAGE_TAG" "$DOCKER_REGISTRY/$IMAGE_NAME:$IMAGE_TAG"
                        docker push "$DOCKER_REGISTRY/$IMAGE_NAME:$IMAGE_TAG"
                    else
                        echo "DOCKER_REGISTRY not set; skipping image push."
                    fi
                '''
                archiveArtifacts artifacts: "${REPORTS}/image-tag.txt, docker-compose.yml, .env.example", fingerprint: true
            }
        }
    }

    post {
        success { echo "Pipeline succeeded: ${IMAGE_NAME}:${IMAGE_TAG} is ready for deployment." }
        failure { echo 'Pipeline failed. See the stage logs and test reports.' }
        cleanup { sh 'rm -f .env || true' }
    }
}
