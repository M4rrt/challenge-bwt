#!/usr/bin/env bash
# Builds frontend/ and syncs the output to the S3 bucket provisioned by infra/frontend.tf.
#
# Usage:
#   ./deploy-frontend.sh                                    # real AWS, reads bucket from terraform output
#   LOCALSTACK_ENDPOINT=http://localhost:4566 ./deploy-frontend.sh   # target LocalStack instead
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$(dirname "$SCRIPT_DIR")"
FRONTEND_DIR="$(dirname "$INFRA_DIR")/frontend"

BUCKET="$(terraform -chdir="$INFRA_DIR" output -raw frontend_bucket)"

AWS_ARGS=()
if [[ -n "${LOCALSTACK_ENDPOINT:-}" ]]; then
  AWS_ARGS+=(--endpoint-url "$LOCALSTACK_ENDPOINT")
  export AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID:-test}"
  export AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY:-test}"
  export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-east-1}"
fi

echo "Building frontend..."
(cd "$FRONTEND_DIR" && npm run build)

echo "Syncing frontend/dist to s3://$BUCKET ..."
aws "${AWS_ARGS[@]}" s3 sync "$FRONTEND_DIR/dist" "s3://$BUCKET" --delete

if [[ -z "${LOCALSTACK_ENDPOINT:-}" ]]; then
  DISTRIBUTION_ID="$(terraform -chdir="$INFRA_DIR" output -raw cloudfront_distribution_id)"
  echo "Invalidating CloudFront cache ($DISTRIBUTION_ID) ..."
  aws cloudfront create-invalidation --distribution-id "$DISTRIBUTION_ID" --paths "/*"
else
  echo "Skipping CloudFront invalidation (LocalStack community doesn't support CloudFront)."
fi

echo "Done."
