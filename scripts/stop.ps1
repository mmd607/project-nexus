# Stop the Project Nexus server listening on the given port (Windows).
#   powershell -ExecutionPolicy Bypass -File scripts\stop.ps1 [-Port 8765]
param([int]$Port = 8765)
$conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if (-not $conns) { Write-Host "Nothing is listening on port $Port."; exit 0 }
$pids = $conns | Select-Object -ExpandProperty OwningProcess -Unique
foreach ($p in $pids) {
  $name = (Get-Process -Id $p -ErrorAction SilentlyContinue).ProcessName
  Stop-Process -Id $p -Force -ErrorAction SilentlyContinue
  Write-Host "Stopped $name (pid $p) on port $Port."
}
