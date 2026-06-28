param(
    [int]$Interval = 300,
    [switch]$DryRun,
    [switch]$TestNow,
    [switch]$VerboseOutput,
    [switch]$SingleInstance
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

if ($TestNow) {
    $arguments += "--test-now"
}
if ($VerboseOutput) {
    $arguments += "--verbose"
}

if ($DryRun) {
    Write-Output "Would run: $PythonExe $($arguments -join ' ')"
    exit 0
}

if ($SingleInstance) {
    $existing = Get-CimInstance Win32_Process |
        Where-Object {
            $_.Name -eq "python.exe" -and
            $_.CommandLine -like "*hermes_loop.py*" -and
            $_.ProcessId -ne $PID
        }

    foreach ($proc in $existing) {
        Write-Output "Stopping existing Hermes process PID=$($proc.ProcessId)"
        Stop-Process -Id $proc.ProcessId -Force
    }
}

Set-Location $ProjectRoot
& $PythonExe @arguments
