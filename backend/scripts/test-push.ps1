# Schedule (or send) a one-off TEST push to diagnose notification delivery
# (wraps scripts/test_push.py). Touches no in-app setting. Pulls the
# production credentials from Railway on each run — nothing is stored
# locally. Requires the Railway CLI, logged in and linked to the tada project.
#
# Usage (from anywhere):
#   .\scripts\test-push.ps1 -In 5              # the worker sends it 5 minutes from now
#   .\scripts\test-push.ps1 -At 15:45          # today at 3:45 PM her local time (tomorrow if past)
#   .\scripts\test-push.ps1 -Now               # send right now, from this machine
#   .\scripts\test-push.ps1 -Now -Device apple # ...to one device only (fcm | apple)
#   .\scripts\test-push.ps1 -List              # every test so far: scheduled vs actually sent
#   .\scripts\test-push.ps1 -Cancel            # drop the tests that haven't gone out yet
# Add -Body "..." to replace the default text, -User "Name" for someone else.
param(
    [int]$In,
    [string]$At,
    [switch]$Now,
    [switch]$List,
    [switch]$Cancel,
    [ValidateSet('all', 'fcm', 'apple')][string]$Device = 'all',
    [string]$Body,
    [string]$User = 'Maryann'
)

$modes = @()
if ($PSBoundParameters.ContainsKey('In')) { $modes += @('--in', "$In") }
if ($At) { $modes += @('--at', $At) }
if ($Now) { $modes += '--now' }
if ($List) { $modes += '--list' }
if ($Cancel) { $modes += '--cancel' }
$chosen = @($PSBoundParameters.Keys | Where-Object { $_ -in 'In', 'At', 'Now', 'List', 'Cancel' })
if ($chosen.Count -ne 1) {
    Write-Host "Pick exactly one of -In, -At, -Now, -List, -Cancel (usage is at the top of this script)."
    exit 1
}

Set-Location (Split-Path $PSScriptRoot -Parent)

# The reminder worker's service ("cron") holds every variable the script
# needs — DATABASE_URL, SECRET_KEY, the VAPID keys — and asking for it by
# name means this works however the CLI happens to be linked.
$kv = @{}
railway variables --service cron --kv | ForEach-Object { $k, $v = $_ -split '=', 2; $kv[$k] = $v }
if (-not $kv['SECRET_KEY']) {
    Write-Host "Couldn't read the cron service's variables from Railway. Is the CLI logged in (railway login) and linked to the tada project (railway link)?"
    exit 1
}
$env:SECRET_KEY = $kv['SECRET_KEY']
$env:VAPID_PRIVATE_KEY = $kv['VAPID_PRIVATE_KEY']
$env:VAPID_PUBLIC_KEY = $kv['VAPID_PUBLIC_KEY']
$env:VAPID_CLAIMS_EMAIL = $kv['VAPID_CLAIMS_EMAIL']

# The service's DATABASE_URL points at Railway's private network, which is
# unreachable from a local machine — swap in the Postgres service's public
# proxy URL, keeping the psycopg3 driver scheme the app expects.
$public = (railway variables --service Postgres --kv |
        Where-Object { $_ -like 'DATABASE_PUBLIC_URL=*' }) -replace '^DATABASE_PUBLIC_URL=', ''
$env:DATABASE_URL = $public -replace '^postgresql://', 'postgresql+psycopg://'

# The test titles carry emoji, which the console's default code page can't print.
$env:PYTHONIOENCODING = 'utf-8'

$pyArgs = @('-m', 'scripts.test_push', '--user', $User, '--device', $Device) + $modes
if ($Body) { $pyArgs += @('--body', $Body) }
& .venv\Scripts\python.exe @pyArgs
exit $LASTEXITCODE
