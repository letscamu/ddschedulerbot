# Run this in an ADMIN PowerShell on the ZBook
# Adds the Mac Studio's SSH public key so it can connect without a password

Add-Content -Path "C:\ProgramData\ssh\administrators_authorized_keys" -Value "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOl/DknTAwb+Req0D31ZN3vpdI1G5OSdReTQmqKfO8mn sean@figsocap.com"

icacls "C:\ProgramData\ssh\administrators_authorized_keys" /inheritance:r /grant "SYSTEM:(F)" /grant "Administrators:(F)"

Write-Host "Done! Now test from the Mac Studio: ssh seanfilipow@192.168.86.33"
