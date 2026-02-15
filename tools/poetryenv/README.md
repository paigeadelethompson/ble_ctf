# BLE CTF Tools (Poetry environment)

This folder contains a small Poetry-managed Python environment with helper
utilities for interacting with BlueZ/LE devices on the host. It is intended
for interactive use during the BLE CTF/workshop.

Location
- Project: `tools/poetryenv`

Quick setup

1. Install dependencies into the Poetry project (from the repo root):

```bash
poetry -P tools/poetryenv install
```

2. Run an example script (these are exposed as Poetry scripts or can be run
   directly via Python):

```bash
# interactive GATT CLI
poetry -P tools/poetryenv run gatt-cli

# simple continuous scanner (prints Rich tables)
poetry -P tools/poetryenv run scan-ble

# list adapters
poetry -P tools/poetryenv run list-adapters

# live pcap-style printer
poetry -P tools/poetryenv run live-pcap --iface hci0
```

Examples
- Example scripts are located in `tools/poetryenv/examples/`.

Interactive helpers
- `gatt-cli` opens an IPython shell with convenience helpers such as:
  - `list_devices()` — print a Rich table of discovered devices (print-only)
  - `get_devices()` — return a list of device dicts for scripting
  - `connect(addr)` — returns a `DeviceSession` with `list_chars()`, `read()`, `write()`, `disconnect()`
  - `read_by_address(addr, uuid=None)` — read a characteristic by address (auto-connect)
  - `show_devices()` / `show_chars(addr)` — pretty Rich tables

Notes
- All tools use library APIs only (no subprocess calls). BlueZ D-Bus access
  may require privileges on some systems (run as a user with access to the
  system bus or use a suitable Polkit policy).
- If a script is missing or moved to `examples/`, you can run it directly:

```bash
poetry -P tools/poetryenv run python tools/poetryenv/examples/scan_ble.py
```

License
- Code in this folder follows the repository's licensing. See the repo root
  for full license details.
