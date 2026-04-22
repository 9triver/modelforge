#!/bin/bash
set -e
cd "$(dirname "$0")/.."

echo "==> Building modelforge-runtime:timeseries"
docker build -f docker/Dockerfile.timeseries -t modelforge-runtime:timeseries .

echo "==> Preparing vision wheels (torch+torchvision cu124)"
mkdir -p wheels
if [ ! -f wheels/torch-*.whl ]; then
    pip download torch==2.6.0+cu124 torchvision --index-url https://mirror.sjtu.edu.cn/pytorch-wheels/cu124 -d wheels --no-deps
fi

echo "==> Building modelforge-runtime:vision"
docker build -f docker/Dockerfile.vision -t modelforge-runtime:vision .

echo "==> Done"
docker images modelforge-runtime
