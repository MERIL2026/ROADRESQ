#!/usr/bin/env bash
set -e

echo "🚀 Initializing RoadResQ Development Environment Setup..."

if [ ! -f ".env" ]; then
    echo "Creating .env from .env.example..."
    cp .env.example .env
    echo "✅ .env created successfully."
else
    echo "ℹ️ .env already exists. Preserving local .env file."
fi

echo "🐳 Building and starting Docker containers..."
docker compose up -d --build

echo "🎉 RoadResQ Environment is up and running!"
echo "FastAPI Docs: http://localhost:8000/docs"
echo "Customer Web: http://localhost:3000"
