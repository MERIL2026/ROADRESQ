# PowerShell Script for Destructive Database Reset
Write-Host "⚠️ WARNING: THIS WILL DESTROY ALL LOCAL POSTGRESQL AND REDIS VOLUMES!" -ForegroundColor Red
$confirmation = Read-Host "Are you sure you want to wipe local development database data? (y/N)"

if ($confirmation -eq 'y' -or $confirmation -eq 'Y') {
    Write-Host "🔥 Stopping containers and deleting volumes..." -ForegroundColor Yellow
    docker compose down -v
    Write-Host "Restarting fresh database environment..." -ForegroundColor Cyan
    docker compose up -d
    Write-Host "✅ Database reset complete." -ForegroundColor Green
} else {
    Write-Host "Aborted. No data was deleted." -ForegroundColor Gray
}
