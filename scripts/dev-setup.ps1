# PowerShell Script for RoadResQ Developer Setup
Write-Host "🚀 Initializing RoadResQ Development Environment Setup..." -ForegroundColor Cyan

if (-not (Test-Path ".env")) {
    Write-Host "Creating .env from .env.example..." -ForegroundColor Yellow
    Copy-Item ".env.example" ".env"
    Write-Host "✅ .env created successfully." -ForegroundColor Green
} else {
    Write-Host "ℹ️ .env already exists. Preserving local .env file." -ForegroundColor Gray
}

Write-Host "🐳 Building and starting Docker containers..." -ForegroundColor Cyan
docker compose up -d --build

Write-Host "🎉 RoadResQ Environment is up and running!" -ForegroundColor Green
Write-Host "FastAPI Docs: http://localhost:8000/docs" -ForegroundColor Yellow
Write-Host "Customer Web: http://localhost:3000" -ForegroundColor Yellow
