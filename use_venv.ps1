# Add this project's virtual environment to the current PowerShell session.
# Load it with: . .\use_venv.ps1

$projectRoot = $PSScriptRoot
$venvRoot = Join-Path $projectRoot ".venv"
$venvScripts = Join-Path $venvRoot "Scripts"
$venvPython = Join-Path $venvScripts "python.exe"

if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    throw "Project virtual environment Python was not found at: $venvPython"
}

$resolvedScripts = (Resolve-Path -LiteralPath $venvScripts).Path.TrimEnd('\')
$pathEntries = $env:Path -split ';'
if ($pathEntries -notcontains $resolvedScripts) {
    $env:Path = "$resolvedScripts;$env:Path"
}
$env:VIRTUAL_ENV = $venvRoot

Write-Host "Project virtual environment is active: $venvRoot"
Write-Host "Python: $venvPython"
