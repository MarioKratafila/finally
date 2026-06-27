param([switch]$Build)

$ErrorActionPreference = "Stop"

$ImageName = "finally"
$ContainerName = "finally-app"
$Port = 8000
$DbVolume = "finally-data"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$EnvFile = Join-Path $ProjectRoot ".env"

if (-not (Test-Path $EnvFile)) {
    Write-Host "Error: .env not found at $EnvFile"
    Write-Host "Copy the template first:  Copy-Item .env.example .env"
    exit 1
}

$imageExists = docker image inspect $ImageName 2>$null
if ($Build -or -not $imageExists) {
    Write-Host "Building Docker image..."
    docker build -t $ImageName $ProjectRoot
}

$existing = docker ps -aq -f "name=^$ContainerName$"
if ($existing) {
    Write-Host "Removing existing container..."
    docker rm -f $ContainerName | Out-Null
}

Write-Host "Starting FinAlly..."
docker run -d `
    --name $ContainerName `
    -p "${Port}:8000" `
    -v "${DbVolume}:/app/db" `
    --env-file "$EnvFile" `
    $ImageName

Write-Host "FinAlly is running at http://localhost:$Port"
Start-Process "http://localhost:$Port"
