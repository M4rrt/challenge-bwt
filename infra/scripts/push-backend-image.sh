#!/usr/bin/env bash
# Builds backend/'s image and pushes it to the ECR repository provisioned by infra/ecs.tf,
# tagged with the current git commit SHA (not `latest`) so deploys are reproducible/rollback-able.
#
# Usage:
#   ./push-backend-image.sh                                          # real AWS
#   LOCALSTACK_ENDPOINT=http://localhost:4566 ./push-backend-image.sh # target LocalStack instead
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$(dirname "$SCRIPT_DIR")"
BACKEND_DIR="$(dirname "$INFRA_DIR")/backend"

TAG="$(git -C "$INFRA_DIR" rev-parse --short HEAD)"
REPO_URL="$(terraform -chdir="$INFRA_DIR" output -raw ecr_repository_url)"
IMAGE="$REPO_URL:$TAG"

echo "Building $IMAGE ..."
docker build -t "$IMAGE" "$BACKEND_DIR"

if [[ -n "${LOCALSTACK_ENDPOINT:-}" ]]; then
  export AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID:-test}"
  export AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY:-test}"
  export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-east-1}"
  REGISTRY="${REPO_URL%%/*}"
  echo "test" | docker login --username AWS --password-stdin "$REGISTRY"
else
  aws ecr get-login-password --region "${AWS_REGION:-us-east-1}" \
    | docker login --username AWS --password-stdin "${REPO_URL%%/*}"
fi

echo "Pushing $IMAGE ..."
docker push "$IMAGE"

echo "Pushed. Deploy it with: terraform apply -var=\"image_tag=$TAG\""
