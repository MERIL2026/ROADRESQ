# PowerShell Script to test RoadResQ health endpoints
Write-Host "🔍 Testing RoadResQ API Health Endpoints..." -ForegroundColor Cyan

try {
    $liveness = Invoke-RestMethod -Uri "http://localhost:8000/health" -Method Get
    Write-Host "✅ Liveness Check Passed:" -ForegroundColor Green
    Write-Host ($liveness | ConvertTo-Json) -ForegroundColor Gray

    $readiness = Invoke-RestMethod -Uri "http://localhost:8000/health/ready" -Method Get
    Write-Host "✅ Readiness Check Passed (PostgreSQL + PostGIS + Redis):" -ForegroundColor Green
    Write-Host ($readiness | ConvertTo-Json) -ForegroundColor Gray
} catch {
    Write-Host "❌ Health check failed. Ensure docker containers are running with 'docker compose up'." -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
}
