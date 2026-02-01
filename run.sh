#!/bin/bash
set -e

# Load .env if it exists
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Run the app
uvicorn app.main:app --host ${HOST:-0.0.0.0} --port ${PORT:-8013} --reload
