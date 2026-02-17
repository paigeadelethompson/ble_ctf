#!/usr/bin/env python3
"""GATT enumerator using BlueZ D-Bus (dbus-next).

Usage: gatt_enum.py <MAC>

Uses D-Bus to locate the device by address, enumerate GATT characteristics
and attempt to read readable characteristics via `org.bluez.GattCharacteristic1.ReadValue`.
Prints results using `rich.Table`.
"""
import sys
import binascii
import asyncio

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

    from dbus_next.aio import MessageBus
    from dbus_next.constants import BusType
    from dbus_next import Variant

    async def main_async(mac: str) -> int:
        try:
            bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        except Exception as e:
            print(f"Failed to connect to system bus: {e}", file=sys.stderr)
            return 4

        # Use ObjectManager to find device matching MAC. Call method directly
        # via a low-level Message to avoid ProxyInterface method name issues.
        try:
            root_introspect = await bus.introspect('org.bluez', '/')
            from dbus_next import Message
            msg = Message(destination='org.bluez', path='/', interface='org.freedesktop.DBus.ObjectManager', member='GetManagedObjects', signature='', body=[])
            reply = await bus.call(msg)
            managed = reply.body[0]

            pass
        except Exception as e:
            print(f"Failed to get managed objects from BlueZ: {e}", file=sys.stderr)
            return 4

        device_path = None
        def _unwrap(v):
            # Extract underlying value from dbus-next return types
            try:
                # common pattern: (signature, value) or Variant-like
                if isinstance(v, (list, tuple)) and len(v) == 2 and not isinstance(v[0], dict):
                    return v[1]
            except Exception:
                pass
            # objects may have a `value` attribute
            if hasattr(v, 'value'):
                return v.value
            return v

        mac_underscore = mac.replace(':', '_').lower()
        mac_nodelim = mac.replace(':', '').lower()

        for path, interfaces in managed.items():
            if 'org.bluez.Device1' in interfaces:
                props = interfaces['org.bluez.Device1']
                addr = props.get('Address') or props.get('address')
                addr = _unwrap(addr) if addr is not None else None
                if addr and str(addr).upper() == mac:
                    device_path = path
                    break
            # fallback: match device path containing MAC with underscores or hyphens
            lp = path.lower()
            if mac_underscore in lp or mac_nodelim in lp:
                device_path = path
                break

        if not device_path:
            # Try starting discovery programmatically and re-check managed objects
            try:
                from dbus_next import Message
                adapter_path = '/org/bluez/hci0'
                start_msg = Message(destination='org.bluez', path=adapter_path, interface='org.bluez.Adapter1', member='StartDiscovery', signature='', body=[])
                await bus.call(start_msg)
                await asyncio.sleep(2)
                msg2 = Message(destination='org.bluez', path='/', interface='org.freedesktop.DBus.ObjectManager', member='GetManagedObjects', signature='', body=[])
                reply2 = await bus.call(msg2)
                managed = reply2.body[0]

                pass

                # retry device lookup
                for path, interfaces in managed.items():
                    if 'org.bluez.Device1' in interfaces:
                        props = interfaces['org.bluez.Device1']
                        addr = props.get('Address') or props.get('address')
                        addr = _unwrap(addr) if addr is not None else None
                        if addr and str(addr).upper() == mac:
                            device_path = path
                            break
                    lp = path.lower()
                    if mac_underscore in lp or mac_nodelim in lp:
                        device_path = path
                        break
            except Exception as e:
                print(f"StartDiscovery retry failed: {e}", file=sys.stderr)

            if not device_path:
                print(f"Device {mac} not found via BlueZ. Make sure it's visible to the adapter.", file=sys.stderr)
                return 5

        # Attempt to connect to the device to force service resolution
        try:
            from dbus_next import Message
            conn_msg = Message(destination='org.bluez', path=device_path, interface='org.bluez.Device1', member='Connect', signature='', body=[])
            await bus.call(conn_msg)
            await asyncio.sleep(1)
            # refresh managed objects after connect
            refresh_msg = Message(destination='org.bluez', path='/', interface='org.freedesktop.DBus.ObjectManager', member='GetManagedObjects', signature='', body=[])
            reply3 = await bus.call(refresh_msg)
            managed = reply3.body[0]
            pass
        except Exception as e:
            print(f"Connect attempt failed (continuing): {e}", file=sys.stderr)

        rows = []
        # find characteristics under device path
        for path, interfaces in managed.items():
            if not path.startswith(device_path):
                continue
            if 'org.bluez.GattCharacteristic1' in interfaces:
                props = interfaces['org.bluez.GattCharacteristic1']
                uuid = props.get('UUID', '')
                uuid = _unwrap(uuid) if uuid is not None else ''
                raw_flags = props.get('Flags', []) or []
                uf = _unwrap(raw_flags) if raw_flags is not None else []
                if isinstance(uf, (list, tuple)):
                    flags_list = [str(x) for x in uf]
                else:
                    flags_list = [str(uf)] if uf else []
                r_flag = 'Y' if any('read' in f.lower() for f in flags_list) else ''
                w_flag = 'Y' if any('write' in f.lower() for f in flags_list) else ''
                n_flag = 'Y' if any('notify' in f.lower() for f in flags_list) else ''
                i_flag = 'Y' if any('indicate' in f.lower() for f in flags_list) else ''

                # Attempt to call ReadValue via low-level Message call
                value = ''
                if r_flag:
                    try:
                        from dbus_next import Message
                        read_msg = Message(destination='org.bluez', path=path, interface='org.bluez.GattCharacteristic1', member='ReadValue', signature='a{sv}', body=[{}])
                        read_reply = await bus.call(read_msg)
                        raw_val = read_reply.body[0]
                        if isinstance(raw_val, (list, tuple)):
                            raw = bytes(raw_val)
                        elif isinstance(raw_val, (bytes, bytearray)):
                            raw = bytes(raw_val)
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

    # run async main
    exit_code = asyncio.run(main_async(mac))
    return exit_code


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: gatt_enum.py <MAC>")
        sys.exit(2)
    mac = sys.argv[1].upper()
    sys.exit(asyncio.run(main_async(mac)))
