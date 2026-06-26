param(
    [int]$Interval = 300,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$ProjectRoot = "C:\Users\frenc\OneDrive\Documents\AI-Stock"
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$ScriptPath = Join-Path $ProjectRoot "hermes_loop.py"

if (-not (Test-Path $PythonExe)) {
    throw "Python executable not found at $PythonExe"
}
if (-not (Test-Path $ScriptPath)) {
    throw "Hermes script not found at $ScriptPath"
}

$arguments = @($ScriptPath, "run", "--interval", $Interval)

if ($DryRun) {
    Write-Output "Would run: $PythonExe $($arguments -join ' ')"
    exit 0
}

Set-Location $ProjectRoot
& $PythonExe @arguments
