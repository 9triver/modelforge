#!/bin/bash
set -e
cd "$(dirname "$0")/.."

echo "==> Building modelforge-runtime:timeseries"
docker build -f docker/Dockerfile.timeseries -t modelforge-runtime:timeseries .

echo "==> Building modelforge-runtime:vision"
docker build -f docker/Dockerfile.vision -t modelforge-runtime:vision .

echo "==> Done"
docker images modelforge-runtime
