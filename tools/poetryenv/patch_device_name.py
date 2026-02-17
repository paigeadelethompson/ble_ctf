#!/usr/bin/env python3
"""
Patch an embedded device name string inside a PlatformIO firmware binary.

Installed as a poetry script entrypoint `patch-device-name`.
"""
import argparse
import shutil
from pathlib import Path
import sys


def find_all(data: bytes, needle: bytes):
    offs = []
    i = data.find(needle)
    while i != -1:
        offs.append(i)
        i = data.find(needle, i + 1)
    return offs


def find_adv_name_field(data: bytes):
    """Find Complete Local Name field in a raw adv buffer by matching a known
    prefix and returning (name_offset, name_max_len).

    Looks for: 02 01 06 02 0a eb 03 03 FF 00 <len> 09 <name...>
    Returns None if not found.
    """
    prefix = bytes([0x02, 0x01, 0x06, 0x02, 0x0a, 0xeb, 0x03, 0x03, 0xFF, 0x00])
    i = data.find(prefix)
    while i != -1:
        pos = i + len(prefix)
        # need at least length and type
        if pos + 2 <= len(data):
            L = data[pos]
            t = data[pos + 1]
            if t == 0x09 and L >= 1 and (pos + 2 + (L - 1)) <= len(data):
                name_offset = pos + 2
                name_len = L - 1
                return name_offset, name_len
        i = data.find(prefix, i + 1)
    return None


def main():
    p = argparse.ArgumentParser(description="Patch device name in firmware binary")
    p.add_argument("--name", required=True, help="New device name (ASCII)")
    p.add_argument("--firmware", "-f", type=Path,
                   help="Path to firmware binary (overrides --env)")
    p.add_argument("--env", "-e", default="ble_ctf",
                   help="PlatformIO env name to locate firmware under .pio/build/<env>/firmware.bin")
    p.add_argument("--needle", "-n", default="BLECTF",
                   help="Existing ASCII needle to find and replace (default: BLECTF)")
    p.add_argument("--out", "-o", type=Path,
                   help="Output path for patched firmware (defaults to overwrite input)")
    args = p.parse_args()

    needle = args.needle.encode('ascii')
    newname = args.name.encode('ascii')

    if args.firmware:
        firmware = args.firmware
    else:
        firmware = Path('.pio') / 'build' / args.env / 'firmware.bin'

    if not firmware.exists():
        print(f"Firmware not found: {firmware}")
        sys.exit(2)

    data = firmware.read_bytes()

    occ = find_all(data, needle)
    patched = bytearray(data)

    if occ:
        if len(newname) > len(needle):
            print(f"New name too long ({len(newname)} > {len(needle)}). Max {len(needle)}")
            sys.exit(4)
        # choose first occurrence by default
        offset = occ[0]
        print(f"Found needle at offset 0x{offset:x} (first of {len(occ)})")
        # show current embedded name (trim NULs)
        orig_slice = data[offset:offset+len(needle)]
        try:
            orig_name = orig_slice.split(b'\x00', 1)[0].decode('ascii', errors='replace')
        except Exception:
            orig_name = repr(orig_slice)
        print(f"Current name: '{orig_name}'")
        # prepare patched buffer
        patched[offset:offset+len(newname)] = newname
        if len(newname) < len(needle):
            # NUL-pad the remainder
            for i in range(offset+len(newname), offset+len(needle)):
                patched[i] = 0x00
    else:
        # fallback: try to locate the Complete Local Name field in raw adv buffer
        adv = find_adv_name_field(data)
        if not adv:
            print(f"Needle {needle!r} not found and adv-name pattern not found in {firmware}")
            sys.exit(3)
        name_offset, name_max = adv
        if len(newname) > name_max:
            print(f"New name too long ({len(newname)} > {name_max}). Max {name_max}")
            sys.exit(4)
        print(f"Found adv name field at offset 0x{name_offset:x} (max {name_max} bytes)")
        orig_slice = data[name_offset:name_offset+name_max]
        try:
            orig_name = orig_slice.split(b'\x00', 1)[0].decode('ascii', errors='replace')
        except Exception:
            orig_name = repr(orig_slice)
        print(f"Current name: '{orig_name}'")
        # write new name and NUL-pad remainder of the field
        patched[name_offset:name_offset+len(newname)] = newname
        for i in range(name_offset+len(newname), name_offset+name_max):
            patched[i] = 0x00

    outpath = args.out or firmware

    # backup
    bak = firmware.with_suffix(firmware.suffix + '.bak')
    if not bak.exists():
        shutil.copy2(firmware, bak)
        print(f"Backed up original to {bak}")

    outpath.write_bytes(bytes(patched))
    print(f"Wrote patched firmware to {outpath}")
    # show resulting embedded name; determine slice bounds depending on which branch ran
    if occ:
        result_off = offset
        result_len = len(needle)
    else:
        result_off = name_offset
        result_len = name_max
    new_slice = patched[result_off:result_off+result_len]
    try:
        new_name = new_slice.split(b'\x00', 1)[0].decode('ascii', errors='replace')
    except Exception:
        new_name = repr(new_slice)
    print(f"New name: '{new_name}'")


if __name__ == '__main__':
    main()
