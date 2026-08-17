# Manually push a custom notification to a user's devices (wraps
# scripts/send_note.py). Pulls the production credentials from Railway on
# each run — nothing is stored locally. Requires the Railway CLI, logged in
# and linked to the tada-cleaning-app project.
#
# Usage (from anywhere):
#   .\scripts\send-note.ps1 "Title" "Body text"            # sends to Maryann
#   .\scripts\send-note.ps1 "Title" "Body text" -User "Name"
param(
    [Parameter(Mandatory = $true, Position = 0)][string]$Title,
    [Parameter(Mandatory = $true, Position = 1)][string]$Body,
    [string]$User = "Maryann"
)

Set-Location (Split-Path $PSScriptRoot -Parent)

$kv = @{}
railway variables --kv | ForEach-Object { $k, $v = $_ -split '=', 2; $kv[$k] = $v }
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

& .venv\Scripts\python.exe -m scripts.send_note $Title $Body --user $User
