#!/bin/bash
# Development server with hot reload
# Usage: ./run.sh [--docker] [--build]

set -e
cd "$(dirname "$0")"

if [[ "$1" == "--docker" ]]; then
    # Docker development mode
    BUILD_FLAGS=""
    if [[ "$2" == "--rebuild" ]]; then
        docker compose build --no-cache
        BUILD_FLAGS="--build"
    elif [[ "$2" == "--build" ]]; then
        BUILD_FLAGS="--build"
    fi

    echo "Starting jarvis-config-service stack..."
    docker compose --env-file .env up $BUILD_FLAGS
else
    # Local development mode
    if [ -f .env ]; then
        export $(cat .env | grep -v '^#' | xargs)
    fi

    PORT=${PORT:-8013}

    echo "Starting jarvis-config-service locally on port $PORT..."
    uvicorn app.main:app --reload --host 0.0.0.0 --port $PORT
fi
