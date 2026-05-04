#!/usr/bin/env bash
set -euo pipefail

: "${PROJECT_ID:?Set PROJECT_ID to your GCP project ID.}"

REGION="${REGION:-us-central1}"
SERVICE_NAME="${SERVICE_NAME:-hunyuan-world-mirror}"
REPOSITORY="${REPOSITORY:-hunyuan-world-mirror}"
IMAGE_NAME="${IMAGE_NAME:-hunyuan-world-mirror-ui}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
GPU_TYPE="${GPU_TYPE:-nvidia-l4}"
GPU_COUNT="${GPU_COUNT:-1}"
MEMORY="${MEMORY:-32Gi}"
CPU="${CPU:-8}"
TIMEOUT="${TIMEOUT:-3600}"
MAX_INSTANCES="${MAX_INSTANCES:-2}"
MIN_INSTANCES="${MIN_INSTANCES:-1}"
CONCURRENCY="${CONCURRENCY:-80}"
ALLOW_UNAUTHENTICATED="${ALLOW_UNAUTHENTICATED:-true}"

IMAGE_URI="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/${IMAGE_NAME}:${IMAGE_TAG}"

gcloud config set project "${PROJECT_ID}"
gcloud services enable \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  run.googleapis.com

if ! gcloud artifacts repositories describe "${REPOSITORY}" \
  --location "${REGION}" >/dev/null 2>&1; then
  gcloud artifacts repositories create "${REPOSITORY}" \
    --repository-format docker \
    --location "${REGION}" \
    --description "HunyuanWorld-Mirror container images"
fi

gcloud builds submit \
  --config cloudbuild.gcp.yaml \
  --substitutions "_REGION=${REGION},_REPOSITORY=${REPOSITORY},_IMAGE_NAME=${IMAGE_NAME},_IMAGE_TAG=${IMAGE_TAG}" \
  .

AUTH_FLAG="--allow-unauthenticated"
if [[ "${ALLOW_UNAUTHENTICATED}" == "false" ]]; then
  AUTH_FLAG="--no-allow-unauthenticated"
fi

gcloud run deploy "${SERVICE_NAME}" \
  --image "${IMAGE_URI}" \
  --region "${REGION}" \
  --gpu "${GPU_COUNT}" \
  --gpu-type "${GPU_TYPE}" \
  --cpu "${CPU}" \
  --memory "${MEMORY}" \
  --timeout "${TIMEOUT}" \
  --max-instances "${MAX_INSTANCES}" \
  --min-instances "${MIN_INSTANCES}" \
  --concurrency "${CONCURRENCY}" \
  --port 8080 \
  "${AUTH_FLAG}" \
  --execution-environment gen2 \
  --no-cpu-throttling

gcloud run services describe "${SERVICE_NAME}" \
  --region "${REGION}" \
  --format "value(status.url)"
