# Start Project Nexus in the background on http://localhost:8765 (Windows).
#   powershell -ExecutionPolicy Bypass -File scripts\start.ps1 [-Add "D:\Projects"] [-Port 8765]
param([string]$Add = "", [int]$Port = 8765, [switch]$OpenBrowser)
$root = Split-Path $PSScriptRoot -Parent
$args = @("-m", "nexus", "--port", "$Port")
if (-not $OpenBrowser) { $args += "--no-browser" }
if ($Add) { $args += @("--add", $Add) }
$proc = Start-Process -FilePath "python" -ArgumentList $args -WorkingDirectory $root -WindowStyle Hidden -PassThru
Start-Sleep -Seconds 3
try {
  $health = Invoke-RestMethod "http://127.0.0.1:$Port/api/health" -TimeoutSec 5
  Write-Host "Project Nexus $($health.version) is running: http://localhost:$Port/  (pid $($proc.Id))"
} catch {
  Write-Host "Started (pid $($proc.Id)) but the health check failed; see %LOCALAPPDATA%\ProjectNexus\logs\nexus.log"
}
