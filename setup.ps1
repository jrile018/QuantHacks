# One-step setup for Windows (PowerShell):  powershell -ExecutionPolicy Bypass -File setup.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# Find a Python 3.10+
$py = $null
foreach ($cand in @("py -3", "python", "python3")) {
    $parts = $cand.Split(" ")
    $exe = $parts[0]; $extra = @($parts | Select-Object -Skip 1)
    if (Get-Command $exe -ErrorAction SilentlyContinue) {
        & $exe @extra -c "import sys; sys.exit(sys.version_info < (3, 10))" 2>$null
        if ($LASTEXITCODE -eq 0) { $py = @($exe) + $extra; break }
    }
}
if (-not $py) {
    Write-Error "Python 3.10 or later is required. Install it from https://www.python.org/downloads/ (tick 'Add python.exe to PATH') and re-run."
}
$pyExe = $py[0]; $pyArgs = @($py | Select-Object -Skip 1)
Write-Host "Using $(& $pyExe @pyArgs --version)"

if (-not (Test-Path .venv)) {
    Write-Host "Creating .venv ..."
    & $pyExe @pyArgs -m venv .venv
}
$vpy = ".venv\Scripts\python.exe"

Write-Host "Installing packages ..."
& $vpy -m pip install --upgrade pip --quiet
& $vpy -m pip install -r requirements.txt --quiet

Write-Host "Registering the Jupyter kernel ..."
& $vpy -m ipykernel install --user --name gator-quant-hacks --display-name "Python (Gator Quant Hacks .venv)" | Out-Null

if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
    Write-Host "`n>> Created .env - open it and replace 'your-key-here' with your Massive API key."
} elseif (Select-String -Path .env -Pattern "your-key-here" -Quiet) {
    Write-Host "`n>> .env still has the placeholder - replace 'your-key-here' with your Massive API key."
} else {
    Write-Host ".env found."
}

Write-Host "`nDone. Start Jupyter with:"
Write-Host "  .venv\Scripts\activate; jupyter lab"
Write-Host "then open the notebook and pick the kernel `"Python (Gator Quant Hacks .venv)`"."
