#!/usr/bin/env bash
#
# Build a Lambda deployment zip for the bargain-hunter serverless backup.
#
# Produces aws/dist/lambda.zip containing:
#   bargain_hunter/          the deal pipeline package (with templates)
#   config/settings.yaml     shared config (read via SETTINGS_PATH=/var/task/config/...)
#   handler.py               the Lambda entry point
#   <deps>/                  3rd-party deps built for the Lambda runtime
#
# boto3/botocore are intentionally NOT bundled — the Lambda Python runtime
# provides them. Deps with native extensions (pydantic-core) are installed with
# manylinux wheels so they run on Amazon Linux regardless of the build host
# (e.g. macOS/arm).
#
# Usage:
#   aws/build.sh                 # x86_64 (default; matches Terraform architectures)
#   LAMBDA_ARCH=arm64 aws/build.sh
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/.." && pwd)"
BUILD_DIR="$HERE/build"
DIST_DIR="$HERE/dist"
ZIP_PATH="$DIST_DIR/lambda.zip"

PY_VERSION="${LAMBDA_PY_VERSION:-3.12}"
ARCH="${LAMBDA_ARCH:-x86_64}"
case "$ARCH" in
  x86_64) PLATFORM="manylinux2014_x86_64" ;;
  arm64)  PLATFORM="manylinux2014_aarch64" ;;
  *) echo "Unsupported LAMBDA_ARCH: $ARCH (use x86_64 or arm64)" >&2; exit 1 ;;
esac

echo "==> Clean"
rm -rf "$BUILD_DIR" "$ZIP_PATH"
mkdir -p "$BUILD_DIR" "$DIST_DIR"

echo "==> Install dependencies ($PLATFORM, py$PY_VERSION)"
# Runtime deps only — keep in sync with [project.dependencies] in pyproject.toml.
# boto3/botocore omitted (provided by the Lambda runtime).
pip install \
  --platform "$PLATFORM" \
  --python-version "$PY_VERSION" \
  --implementation cp \
  --only-binary=:all: \
  --upgrade \
  --target "$BUILD_DIR" \
  "httpx>=0.27" \
  "pydantic>=2.7" \
  "pyyaml>=6.0" \
  "defusedxml>=0.7" \
  "notion-client>=2.2" \
  "jinja2>=3.1" \
  "beautifulsoup4>=4.12"

echo "==> Copy application source"
cp -r "$REPO_ROOT/src/bargain_hunter" "$BUILD_DIR/bargain_hunter"
mkdir -p "$BUILD_DIR/config"
cp "$REPO_ROOT/config/settings.yaml" "$BUILD_DIR/config/settings.yaml"
cp "$HERE/handler.py" "$BUILD_DIR/handler.py"

echo "==> Prune"
find "$BUILD_DIR" -type d -name "__pycache__" -prune -exec rm -rf {} +
find "$BUILD_DIR" -type d -name "*.dist-info" -prune -exec rm -rf {} +
find "$BUILD_DIR" -type d -name "tests" -prune -exec rm -rf {} +

echo "==> Zip"
( cd "$BUILD_DIR" && zip -qr "$ZIP_PATH" . -x "*.pyc" )

echo "==> Done: $ZIP_PATH ($(du -h "$ZIP_PATH" | cut -f1))"
