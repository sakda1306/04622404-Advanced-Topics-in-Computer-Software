param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('up', 'down', 'logs', 'smoke', 'warmup', 'config')]
    [string]$Task
)

$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath '.env')) {
    throw 'Copy .env.example to .env and set local passwords and provider keys first.'
}

$composeArgs = @('compose', '--env-file', '.env', '-f', 'docker-compose.yml')
switch ($Task) {
    'up' { $composeArgs += @('up', '--build', '-d', '--wait') }
    'down' { $composeArgs += @('down') }
    'logs' { $composeArgs += @('logs', '-f', '--tail=100') }
    'smoke' { $composeArgs += @('run', '--rm', '--no-deps', 'checks', 'python', '/tools/smoke.py') }
    'warmup' { $composeArgs += @('run', '--rm', '--no-deps', 'checks', 'python', '/tools/warmup.py') }
    'config' { $composeArgs += @('config', '--quiet') }
}

& docker @composeArgs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
