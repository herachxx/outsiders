param(
    [ValidateSet('predict', 'serve', 'test')][string]$Action = 'serve',
    [string]$InputPath,
    [string]$OutputPath,
    [string]$Rules = $env:GRAND_RULES_PATH,
    [string]$Model = $env:GRAND_MODEL_PATH,
    [string]$Python = 'python'
)
$ErrorActionPreference = 'Stop'
if ($Action -eq 'test') {
    & $Python -m pytest -q
    exit $LASTEXITCODE
}
if (-not $Rules) { throw 'Specify -Rules or GRAND_RULES_PATH.' }
if ($Action -eq 'serve') {
    $env:GRAND_RULES_PATH = $Rules
    if ($Model) { $env:GRAND_MODEL_PATH = $Model }
    & $Python -m uvicorn app.api:app --host 127.0.0.1 --port 8000
} else {
    if (-not $InputPath -or -not $OutputPath) { throw 'Specify -InputPath and -OutputPath.' }
    if (Test-Path -LiteralPath $OutputPath) { throw 'Output already exists; refusing overwrite.' }
    $batchArgs = @('-m', 'app.batch', '--input', $InputPath, '--output', $OutputPath, '--rules', $Rules)
    if ($Model) { $batchArgs += @('--model', $Model) }
    & $Python @batchArgs
}
exit $LASTEXITCODE
