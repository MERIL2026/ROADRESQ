#!/usr/bin/env bash
set -e

echo "⚠️ WARNING: THIS WILL DESTROY ALL LOCAL POSTGRESQL AND REDIS VOLUMES!"
read -p "Are you sure you want to wipe local development database data? (y/N) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "🔥 Stopping containers and deleting volumes..."
    docker compose down -v
    echo "Restarting fresh database environment..."
    docker compose up -d
    echo "✅ Database reset complete."
else
    echo "Aborted. No data was deleted."
fi
