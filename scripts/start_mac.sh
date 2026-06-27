#!/usr/bin/env bash
set -e

IMAGE_NAME="finally"
CONTAINER_NAME="finally-app"
PORT=8000
DB_VOLUME="finally-data"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$PROJECT_ROOT/.env"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Error: .env not found at $ENV_FILE"
  echo "Copy the template first:  cp .env.example .env"
  exit 1
fi

if [[ "$1" == "--build" ]] || ! docker image inspect "$IMAGE_NAME" &>/dev/null; then
  echo "Building Docker image..."
  docker build -t "$IMAGE_NAME" "$PROJECT_ROOT"
fi

if docker ps -aq -f name="^${CONTAINER_NAME}$" | grep -q .; then
  echo "Removing existing container..."
  docker rm -f "$CONTAINER_NAME" >/dev/null
fi

echo "Starting FinAlly..."
docker run -d \
  --name "$CONTAINER_NAME" \
  -p "$PORT:8000" \
  -v "$DB_VOLUME:/app/db" \
  --env-file "$ENV_FILE" \
  "$IMAGE_NAME"

echo "FinAlly is running at http://localhost:$PORT"

if command -v open &>/dev/null; then
  sleep 2
  open "http://localhost:$PORT"
fi
