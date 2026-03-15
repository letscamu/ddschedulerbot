#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Sets up SSH key-based auth on the ZBook for the Mac Studio connection.
.DESCRIPTION
    Run this as Admin on the ZBook after generating an SSH key on the Mac Studio.
    It configures the authorized_keys file and sshd for Azure AD accounts.
#>

Write-Host "`n=== ZBook SSH Key Setup ===" -ForegroundColor Cyan

# Step 1: Ensure OpenSSH Server is installed and running
$sshdService = Get-Service -Name sshd -ErrorAction SilentlyContinue
if (-not $sshdService) {
    Write-Host "Installing OpenSSH Server..." -ForegroundColor Yellow
    Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
    $sshdService = Get-Service -Name sshd
}

if ($sshdService.Status -ne 'Running') {
    Write-Host "Starting sshd service..." -ForegroundColor Yellow
    Start-Service sshd
    Set-Service -Name sshd -StartupType Automatic
}
Write-Host "[OK] sshd is running" -ForegroundColor Green

# Step 2: Get the public key from the user
Write-Host "`nOn the Mac Studio, run:" -ForegroundColor Yellow
Write-Host "  cat ~/.ssh/id_ed25519.pub" -ForegroundColor White
Write-Host ""
$pubKey = Read-Host "Paste the public key here"

if ([string]::IsNullOrWhiteSpace($pubKey)) {
    Write-Host "No key provided. Aborting." -ForegroundColor Red
    exit 1
}

# Step 3: Write to administrators_authorized_keys (required for Azure AD accounts)
$authKeysPath = "C:\ProgramData\ssh\administrators_authorized_keys"

# Create the file if it doesn't exist
if (-not (Test-Path $authKeysPath)) {
    New-Item -Path $authKeysPath -ItemType File -Force | Out-Null
    Write-Host "Created $authKeysPath" -ForegroundColor Yellow
}

# Check if key already exists
$existing = Get-Content $authKeysPath -ErrorAction SilentlyContinue
if ($existing -and ($existing -contains $pubKey)) {
    Write-Host "[OK] Key already present in authorized_keys" -ForegroundColor Green
} else {
    Add-Content -Path $authKeysPath -Value $pubKey
    Write-Host "[OK] Key added to $authKeysPath" -ForegroundColor Green
}

# Step 4: Fix permissions (critical — sshd ignores the file if permissions are wrong)
icacls $authKeysPath /inheritance:r /grant "SYSTEM:(F)" /grant "Administrators:(F)" | Out-Null
Write-Host "[OK] Permissions set on authorized_keys" -ForegroundColor Green

# Step 5: Ensure sshd_config uses the right authorized_keys file for admins
$sshdConfig = "C:\ProgramData\ssh\sshd_config"
$matchBlock = Get-Content $sshdConfig -Raw

if ($matchBlock -notmatch "administrators_authorized_keys") {
    Write-Host "`n[INFO] Verify that sshd_config has this at the bottom:" -ForegroundColor Yellow
    Write-Host "  Match Group administrators" -ForegroundColor White
    Write-Host "    AuthorizedKeysFile __PROGRAMDATA__/ssh/administrators_authorized_keys" -ForegroundColor White
    Write-Host "(This is the Windows default — if SSH still fails, check this.)" -ForegroundColor Gray
}

# Step 6: Restart sshd to pick up changes
Restart-Service sshd
Write-Host "[OK] sshd restarted" -ForegroundColor Green

# Done
Write-Host "`n=== Setup Complete ===" -ForegroundColor Cyan
Write-Host "Now test from the Mac Studio:" -ForegroundColor White
Write-Host "  ssh seanfilipow@192.168.86.33" -ForegroundColor Yellow
Write-Host ""
