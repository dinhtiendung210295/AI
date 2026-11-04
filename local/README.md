# Local secrets

`pilot-secrets.json` is machine-local configuration copied from the local
pilot installation. It contains the four account records and control keys.
It is intentionally ignored by Git and must never be committed or pasted
into chat.

Run the service with:

```powershell
$env:PILOT_SECRETS_FILE = (Resolve-Path .\local\pilot-secrets.json)
python .\tools\multivibe-review\pilot_service.py start
```

If `accounts` is present, `pilot_service.py` uses those local records to
create the runtime snapshot. Without it, the service falls back to the
existing account store under `%LOCALAPPDATA%`.
