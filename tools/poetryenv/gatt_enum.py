#!/usr/bin/env python3
"""GATT enumerator using BlueZ D-Bus (dbus-next).

Usage: gatt_enum.py <MAC>

Uses D-Bus to locate the device by address, enumerate GATT characteristics
and attempt to read readable characteristics via `org.bluez.GattCharacteristic1.ReadValue`.
Prints results using `rich.Table`.
"""
import sys
import binascii

from rich.table import Table
from rich.console import Console


def fmt_val(b: bytes) -> str:
    if not b:
        return ""
    try:
        s = b.decode('utf-8')
        if any(ord(c) < 32 for c in s):
            raise ValueError
        return s
    except Exception:
        return binascii.hexlify(b).decode('ascii')


def main():
    if len(sys.argv) < 2:
        print("Usage: gatt_enum.py <MAC>")
        return 2
    mac = sys.argv[1].upper()

    try:
        from dbus_next import SystemBus, Variant
    except Exception:
        print("dbus-next is required. Install it in your environment.", file=sys.stderr)
        return 3

    bus = SystemBus()

    # Use ObjectManager to find device matching MAC
    try:
        root_introspect = bus.introspect('org.bluez', '/')
        obj = bus.get_proxy_object('org.bluez', '/', root_introspect)
        manager = obj.get_interface('org.freedesktop.DBus.ObjectManager')
        managed = manager.GetManagedObjects()
    except Exception as e:
        print(f"Failed to get managed objects from BlueZ: {e}", file=sys.stderr)
        return 4

    device_path = None
    for path, interfaces in managed.items():
        if 'org.bluez.Device1' in interfaces:
            props = interfaces['org.bluez.Device1']
            addr = props.get('Address') or props.get('address')
            if addr and addr.upper() == mac:
                device_path = path
                break

    if not device_path:
        print(f"Device {mac} not found via BlueZ. Make sure it's visible to the adapter.", file=sys.stderr)
        return 5

    rows = []
    # find characteristics under device path
    for path, interfaces in managed.items():
        if not path.startswith(device_path):
            continue
        if 'org.bluez.GattCharacteristic1' in interfaces:
            props = interfaces['org.bluez.GattCharacteristic1']
            uuid = props.get('UUID', '')
            flags = props.get('Flags', []) or []
            r_flag = 'Y' if any('read' in f.lower() for f in flags) else ''
            w_flag = 'Y' if any('write' in f.lower() for f in flags) else ''
            n_flag = 'Y' if any('notify' in f.lower() for f in flags) else ''
            i_flag = 'Y' if any('indicate' in f.lower() for f in flags) else ''

            # attempt read using D-Bus method if readable
            value = ''
            if r_flag:
                try:
                    char_introspect = bus.introspect('org.bluez', path)
                    char_obj = bus.get_proxy_object('org.bluez', path, char_introspect)
                    char_iface = char_obj.get_interface('org.bluez.GattCharacteristic1')
                    val = char_iface.ReadValue({})
                    # val may be list of ints
                    if isinstance(val, (list, tuple)):
                        raw = bytes(val)
                    elif isinstance(val, (bytes, bytearray)):
                        raw = bytes(val)
                    else:
                        raw = b''
                    value = fmt_val(raw)
                except Exception:
                    value = ''

            rows.append((path.rsplit('/', 1)[-1], uuid, r_flag, w_flag, n_flag, i_flag, value))

    console = Console()
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Handle", style="dim")
    table.add_column("UUID")
    table.add_column("R", justify="center")
    table.add_column("W", justify="center")
    table.add_column("N", justify="center")
    table.add_column("I", justify="center")
    table.add_column("Value", overflow="fold")

    for r in rows:
        table.add_row(*[str(x) for x in r])

    console.print(table)
    return 0


if __name__ == '__main__':
    sys.exit(main())
