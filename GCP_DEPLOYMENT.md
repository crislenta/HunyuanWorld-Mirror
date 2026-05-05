# Deploy HunyuanWorld-Mirror on GCP

This repo now includes a basic Gradio UI (`gcp_basic_ui.py`) and Cloud Run GPU deployment assets.

## What the UI does

- Accepts a small image sequence or one video upload.
- Runs the existing `infer.py` pipeline.
- Shows resized inputs, depth maps, normal maps, and rendered video when generated.
- Provides downloads for point cloud PLY, Gaussian splat PLY, sparse point PLY, and a ZIP archive of the full output directory.

The first run downloads `tencent/HunyuanWorld-Mirror` weights from Hugging Face unless they are already present in the container cache.

## Prerequisites

1. A GCP project with billing enabled.
2. `gcloud` installed and authenticated.
3. Required APIs enabled:

```sh
gcloud services enable \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  run.googleapis.com
```

4. Cloud Run GPU quota in the target region. NVIDIA L4 availability varies by region.

## Deploy

From the repo root:

```sh
export PROJECT_ID="your-gcp-project"
export REGION="us-central1"
export SERVICE_NAME="hunyuan-world-mirror"

./deploy_gcp_cloud_run.sh
```

The script creates an Artifact Registry repository if needed, builds `Dockerfile.gcp` with Cloud Build, and deploys the service to Cloud Run.
The Docker build config includes apt retry settings because Ubuntu mirror indexes can occasionally be in sync during Cloud Build.

## Useful settings

The deploy script supports these environment variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `PROJECT_ID` | active gcloud project | GCP project to deploy into |
| `REGION` | `us-central1` | Cloud Run and Artifact Registry region |
| `SERVICE_NAME` | `hunyuan-world-mirror` | Cloud Run service name |
| `REPOSITORY` | `hunyuan-world-mirror` | Artifact Registry repository |
| `IMAGE_NAME` | `hunyuan-world-mirror-ui` | Artifact Registry image name |
| `IMAGE_TAG` | `latest` | Container image tag |
| `GPU_TYPE` | `nvidia-l4` | Cloud Run GPU type |
| `GPU_COUNT` | `1` | Number of GPUs |
| `CPU` | `8` | Cloud Run CPU allocation |
| `MEMORY` | `32Gi` | Cloud Run memory allocation |
| `TIMEOUT` | `3600` | Request timeout in seconds |
| `MAX_INSTANCES` | `2` | Maximum service instances |
| `MIN_INSTANCES` | `1` | Minimum warm service instances |
| `CONCURRENCY` | `80` | Concurrent HTTP requests per instance |
| `ALLOW_UNAUTHENTICATED` | `true` | Whether to expose the UI publicly |

Example private deployment:

```sh
ALLOW_UNAUTHENTICATED=false ./deploy_gcp_cloud_run.sh
```

## Local smoke test

On a CUDA machine:

```sh
pip install torch==2.4.0 torchvision==0.19.0 --index-url https://download.pytorch.org/whl/cu124
pip install -r requirements_gcp.txt
pip install gsplat --index-url https://docs.gsplat.studio/whl/pt24cu124
python gcp_basic_ui.py
```

Open `http://localhost:8080`.

## Notes

- The model is large; CPU-only execution is not a practical deployment target.
- `Dockerfile.gcp` uses CUDA-enabled PyTorch and gsplat wheels on top of a slim Python base image to keep the build independent from Ubuntu CUDA image package mirrors.
- The UI skips rendered-video generation by default because `gsplat` video rendering requires CUDA kernels.
- Cloud Run instances are ephemeral. Download generated results from the UI before replacing or scaling down the service.
- If Hugging Face rate limits or private checkpoints are involved, deploy with appropriate environment variables or secret mounts for the Hugging Face cache/token.

## Compute Engine L4 fallback

Cloud Run GPU quota is separate from Compute Engine GPU quota. If Cloud Run L4 quota is unavailable but Compute Engine L4 quota exists, run the same container on a G2 VM:

```sh
gcloud compute firewall-rules create allow-hwm-ui-8080 \
  --allow tcp:8080 \
  --target-tags hwm-ui \
  --source-ranges 0.0.0.0/0

gcloud compute instances create hwm-l4-ui \
  --zone us-central1-c \
  --machine-type g2-standard-8 \
  --accelerator type=nvidia-l4,count=1 \
  --maintenance-policy TERMINATE \
  --boot-disk-size 200GB \
  --image-family common-cu129-ubuntu-2204-nvidia-580 \
  --image-project deeplearning-platform-release \
  --scopes cloud-platform \
  --tags hwm-ui \
  --metadata-from-file startup-script=gce_startup_hwm.sh
```
