#!/usr/bin/env bash
set -e

echo "🔍 Testing RoadResQ API Health Endpoints..."

echo "1. Liveness Check (http://localhost:8000/health):"
curl -s http://localhost:8000/health | python -m json.tool || echo "❌ Liveness probe failed"

echo -e "\n2. Readiness Check (http://localhost:8000/health/ready):"
curl -s http://localhost:8000/health/ready | python -m json.tool || echo "❌ Readiness probe failed"
