# Multi-account pilot router

These scripts are the local control layer for the OpenCode `pilot_multivibe`
provider:

- `pilot_router.py` keeps one account active until the 5-hour quota is at or
  below the configured threshold, then selects the eligible account with the
  most weekly quota remaining. Upstream quota errors trigger one safe retry on
  another account.
- `pilot_service.py` manages the router, quota refresh, and local edge proxy.

The scripts read credentials from a local secrets file selected by
`PILOT_SECRETS_FILE` (default: the existing pilot installation store). Never
commit that file, account stores, logs, or runtime state.

Example:

```powershell
$env:PILOT_SECRETS_FILE = (Resolve-Path .\multivibe-pilot\local\pilot-secrets.json)
python .\multivibe-pilot\router\pilot_service.py status
```
