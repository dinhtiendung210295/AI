# MultiVibe review runtime source

This directory contains the source needed to build the `multivibe-v1-edge`
runtime and the local control-plane launcher.

## Contents

- `source/` — Rust workspace and host source from the MultiVibe review build.
- `start_pilot_control.py` — starts the isolated Node control plane after a
  host runtime has been built or supplied locally.

The prebuilt Windows host package and Rust `target/` output are deliberately
not committed. They are large, platform-specific build artifacts. Build the
Rust edge binary from `source/` with:

```powershell
cd .\multivibe-pilot\multivibe-review\source
cargo build --release --bin multivibe-v1-edge
```

For the control plane, point the launcher at a locally installed host app:

```powershell
$env:MULTIVIBE_HOST_APP = 'C:\path\to\multivibe-host\app'
python .\multivibe-pilot\multivibe-review\start_pilot_control.py
```

Credentials, account stores, runtime packages, logs, and local state remain
outside Git. See `..\local\README.md` for the local secrets file.
