$ErrorActionPreference = "Stop"

$ContainerName = "finally-app"

$existing = docker ps -aq -f "name=^$ContainerName$"
if ($existing) {
    docker rm -f $ContainerName | Out-Null
    Write-Host "FinAlly stopped. Data volume preserved."
} else {
    Write-Host "FinAlly is not running."
}
