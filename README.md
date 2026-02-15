You only need to have Poetry installed; on Debian/Ubuntu you can install it with:

- `apt-get install python3-poetry` (install `python-is-python3` if you don't already have `python`)

Alternatively, if you have `pip` you can install Poetry to the user site (do not use `sudo`):

- `pip install --user --break-system-packages poetry`

This will install Poetry to `~/.local/bin/poetry`.

Usage (after cloning this repository):

```bash
git clone <this-repo-url>
cd <this-repo>
# create a Poetry environment at tools/poetryenv and install deps
poetry -P tools/poetryenv install
# activate that environment
eval `poetry -P tools/poetryenv env activate)`
# build with PlatformIO
pio run -e esp32dev
```

Notes:
- The `-P tools/poetryenv` option tells Poetry to create an isolated environment under `tools/poetryenv` so it doesn't interfere with your global Python.
- If `pio` is installed inside that environment you can run `poetry run pio --version` to verify.
