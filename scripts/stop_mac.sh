#!/usr/bin/env bash
set -e

CONTAINER_NAME="finally-app"

if docker ps -aq -f name="^${CONTAINER_NAME}$" | grep -q .; then
  docker rm -f "$CONTAINER_NAME" >/dev/null
  echo "FinAlly stopped. Data volume preserved."
else
  echo "FinAlly is not running."
fi
