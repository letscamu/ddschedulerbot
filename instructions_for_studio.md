# ZBook (Defiant) ↔ Mac Studio (Mothership) — Setup Complete

## What's Working (as of 2026-03-15)

### SSH (key-based auth, no password)
```bash
ssh seanfilipow@192.168.86.33
```

### Ollama API
```bash
curl http://192.168.86.33:11434/api/generate \
  -d '{"model": "llama3.1", "prompt": "Hello", "stream": false}'
```

---

## Setup Notes (for reference if you need to redo this)

### The Problem
- ZBook uses Azure AD (`azuread\seanfilipow`), which Windows SSH doesn't recognize
- Had to create a **local** `seanfilipow` account for SSH

### What Was Done on the ZBook (Admin PowerShell)

1. **Created local account:**
   ```powershell
   net user seanfilipow Temp1234 /add
   net localgroup Administrators seanfilipow /add
   ```

2. **Wrote SSH key to the correct home directory** (`seanfilipow.DEFIANT`, not `seanfilipow`):
   ```powershell
   New-Item -Path "C:\Users\seanfilipow.DEFIANT\.ssh" -ItemType Directory -Force
   Set-Content -Path "C:\Users\seanfilipow.DEFIANT\.ssh\authorized_keys" -Value "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOl/DknTAwb+Req0D31ZN3vpdI1G5OSdReTQmqKfO8mn sean@figsocap.com"
   ```

3. **Enabled PubkeyAuthentication** in `C:\ProgramData\ssh\sshd_config`:
   - Uncommented `PubkeyAuthentication yes`
   - Commented out the `Match Group administrators` block (was overriding authorized_keys path)

4. **Restarted sshd:**
   ```powershell
   Restart-Service sshd
   ```

### Mac Studio Key
- Key: `~/.ssh/id_ed25519`
- Generated: 2026-03-10
- Comment: `sean@figsocap.com`

### Network
- ZBook (Defiant): `192.168.86.33`
- Mac Studio (Mothership): `192.168.86.30`
- Ollama port: `11434`
