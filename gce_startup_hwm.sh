#!/usr/bin/env bash
set -euxo pipefail

exec > >(tee /var/log/hwm-startup.log) 2>&1

IMAGE="us-central1-docker.pkg.dev/pure-polymer-481718-h3/hunyuan-world-mirror/hunyuan-world-mirror-ui:latest"
DOCKER_VERSION="27.5.1"

apt-get update
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL "https://download.docker.com/linux/static/stable/x86_64/docker-${DOCKER_VERSION}.tgz" \
    -o /tmp/docker.tgz
  tar -xzf /tmp/docker.tgz -C /tmp
  cp /tmp/docker/* /usr/local/bin/
fi

if ! command -v nvidia-ctk >/dev/null 2>&1; then
  curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
    | gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
  curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
    | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
    > /etc/apt/sources.list.d/nvidia-container-toolkit.list
  apt-get update
  apt-get install -y nvidia-container-toolkit
fi

nvidia-ctk runtime configure --runtime=docker

pkill dockerd || true
nohup /usr/local/bin/dockerd \
  --host=unix:///var/run/docker.sock \
  --data-root=/var/lib/docker \
  > /var/log/dockerd.log 2>&1 &
for _ in $(seq 1 30); do
  if /usr/local/bin/docker version >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

gcloud auth configure-docker us-central1-docker.pkg.dev --quiet

mkdir -p /models /var/lib/hunyuan-world-mirror
/usr/local/bin/docker pull "${IMAGE}"
/usr/local/bin/docker rm -f hwm-ui || true
/usr/local/bin/docker run -d \
  --name hwm-ui \
  --restart unless-stopped \
  --gpus all \
  -p 8080:8080 \
  -e HWM_RENDER_VIDEO=true \
  -e HWM_OUTPUT_ROOT=/var/lib/hunyuan-world-mirror \
  -e HF_HOME=/models/huggingface \
  -e TORCH_HOME=/models/torch \
  -v /models:/models \
  -v /var/lib/hunyuan-world-mirror:/var/lib/hunyuan-world-mirror \
  "${IMAGE}"
