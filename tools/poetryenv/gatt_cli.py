#!/usr/bin/env python3
"""Interactive GATT CLI using BlueZ D-Bus and IPython embed.

Provides synchronous helper functions in an IPython shell for listing
adapters/devices, connecting, listing services/characteristics, and
reading/writing characteristics. All Bluetooth operations use dbus-next
and no subprocesses.

Usage: `poetry -P tools/poetryenv run gatt-cli`
Inside the IPython shell you'll have helpers: `list_devices()`,
`connect(addr)`, `disconnect(addr)`, `list_chars(addr)`, `read(char_path)`,
`write(char_path, data_bytes)`.
"""
from __future__ import annotations

import argparse
import asyncio
from typing import Dict, Any, List

from IPython import embed
from dbus_next.aio import MessageBus
from dbus_next.constants import BusType
from rich.console import Console
from rich.table import Table


def _unwrap(v: Any):
    try:
        return v.value
    except Exception:
        return v


async def _get_managed_objects():
    bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
    introspect = await bus.introspect('org.bluez', '/')
    root = bus.get_proxy_object('org.bluez', '/', introspect)
    manager = root.get_interface('org.freedesktop.DBus.ObjectManager')
    return await manager.call_get_managed_objects()


async def _start_discovery(iface: str = 'hci0') -> None:
    bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
    adapter_path = f"/org/bluez/{iface}"
    introspect = await bus.introspect('org.bluez', adapter_path)
    adapter_obj = bus.get_proxy_object('org.bluez', adapter_path, introspect)
    adapter = adapter_obj.get_interface('org.bluez.Adapter1')
    try:
        await adapter.call_start_discovery()
    except Exception:
        pass


async def _stop_discovery(iface: str = 'hci0') -> None:
    bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
    adapter_path = f"/org/bluez/{iface}"
    introspect = await bus.introspect('org.bluez', adapter_path)
    adapter_obj = bus.get_proxy_object('org.bluez', adapter_path, introspect)
    adapter = adapter_obj.get_interface('org.bluez.Adapter1')
    try:
        await adapter.call_stop_discovery()
    except Exception:
        pass


async def _device_path_for_address(address: str) -> str | None:
    objs = await _get_managed_objects()
    for path, ifaces in objs.items():
        dev = ifaces.get('org.bluez.Device1')
        if not dev:
            continue
        addr = _unwrap(dev.get('Address') or dev.get('address') or '')
        if addr and addr.upper() == address.upper():
            return path
    return None


async def _connect(address: str) -> bool:
    path = await _device_path_for_address(address)
    if not path:
        print('Device not found')
        return None
    bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
    introspect = await bus.introspect('org.bluez', path)
    obj = bus.get_proxy_object('org.bluez', path, introspect)
    dev = obj.get_interface('org.bluez.Device1')
    try:
        await dev.call_connect()
        return path
    except Exception as e:
        print('Connect error:', e)
        return None


async def _disconnect(address: str) -> bool:
    path = await _device_path_for_address(address)
    if not path:
        print('Device not found')
        return False
    bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
    introspect = await bus.introspect('org.bluez', path)
    obj = bus.get_proxy_object('org.bluez', path, introspect)
    dev = obj.get_interface('org.bluez.Device1')
    try:
        await dev.call_disconnect()
        print('Disconnected')
        return True
    except Exception as e:
        print('Disconnect error:', e)
        return False


async def _list_devices() -> List[Dict[str, Any]]:
    objs = await _get_managed_objects()
    out = []
    for path, ifaces in objs.items():
        dev = ifaces.get('org.bluez.Device1')
        if not dev:
            continue
        out.append({
            'path': path,
            'address': _unwrap(dev.get('Address') or dev.get('address') or ''),
            'name': _unwrap(dev.get('Name') or dev.get('Alias') or ''),
            'connected': _unwrap(dev.get('Connected') or False),
        })
    return out


async def _list_devices_with_discovery(iface: str = 'hci0', timeout: float = 1.0) -> List[Dict[str, Any]]:
    # If no devices found initially, start discovery for `timeout` seconds and retry
    devices = await _list_devices()
    if devices:
        return devices
    await _start_discovery(iface)
    await asyncio.sleep(timeout)
    devices = await _list_devices()
    try:
        await _stop_discovery(iface)
    except Exception:
        pass
    return devices


async def _list_chars_for(address: str) -> List[Dict[str, Any]]:
    path = await _device_path_for_address(address)
    if not path:
        return []
    objs = await _get_managed_objects()
    chars = []
    for p, ifaces in objs.items():
        if not p.startswith(path):
            continue
        ch = ifaces.get('org.bluez.GattCharacteristic1')
        if not ch:
            continue
        chars.append({'path': p, 'uuid': _unwrap(ch.get('UUID') or ch.get('uuid') or ''), 'flags': _unwrap(ch.get('Flags') or [])})
    return chars


async def _read_char(char_path: str) -> bytes:
    bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
    introspect = await bus.introspect('org.bluez', char_path)
    obj = bus.get_proxy_object('org.bluez', char_path, introspect)
    ch = obj.get_interface('org.bluez.GattCharacteristic1')
    val = await ch.call_read_value({})
    # val may be a list of ints or array of bytes
    try:
        return bytes(val)
    except Exception:
        # if it's a Variant-wrapped sequence
        try:
            return bytes(_unwrap(val))
        except Exception:
            return b''


async def _write_char(char_path: str, data: bytes) -> bool:
    bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
    introspect = await bus.introspect('org.bluez', char_path)
    obj = bus.get_proxy_object('org.bluez', char_path, introspect)
    ch = obj.get_interface('org.bluez.GattCharacteristic1')
    arr = list(data)
    try:
        await ch.call_write_value(arr, {})
        return True
    except Exception as e:
        print('Write error:', e)
        return False


# Synchronous wrappers for the IPython shell
def list_devices():
    # Print a Rich table for interactive use and do NOT return the list
    devs = asyncio.run(_list_devices_with_discovery())
    t = Table(title="Bluetooth Devices")
    t.add_column("Path", no_wrap=True)
    t.add_column("Address")
    t.add_column("Name")
    t.add_column("Connected")
    for d in devs:
        t.add_row(d.get('path', ''), d.get('address', ''), str(d.get('name', '')), str(d.get('connected', False)))
    _console.print(t)
    return None


def get_devices():
    """Return device list for programmatic use (no printing)."""
    return asyncio.run(_list_devices_with_discovery())


def connect(address: str):
    """Connect to a device and return a `DeviceSession` on success.

    Example:
      svc = connect('AA:BB:CC:11:22:33')
      svc.list_chars()
      svc.read('/org/bluez/...')
    """
    path = asyncio.run(_connect(address))
    if not path:
        return None
    return DeviceSession(address, path)


class DeviceSession:
    """Lightweight synchronous wrapper around a connected device.

    Methods call the existing async helpers via the synchronous wrappers
    already defined in this module.
    """
    def __init__(self, address: str, path: str):
        self.address = address
        self.path = path

    def list_chars(self):
        return list_chars(self.address)

    def _find_char_path(self, uuid: str) -> str | None:
        chars = list_chars(self.address)
        for c in chars:
            if c.get('uuid', '').lower() == uuid.lower():
                return c.get('path')
        return None

    def read(self, char_path_or_uuid: str) -> bytes:
        if char_path_or_uuid.startswith('/org/bluez/'):
            return read(char_path_or_uuid)
        # treat as uuid
        p = self._find_char_path(char_path_or_uuid)
        if not p:
            raise RuntimeError(f'Characteristic {char_path_or_uuid} not found')
        return read(p)

    def write(self, char_path_or_uuid: str, data: bytes) -> bool:
        if char_path_or_uuid.startswith('/org/bluez/'):
            return write(char_path_or_uuid, data)
        p = self._find_char_path(char_path_or_uuid)
        if not p:
            raise RuntimeError(f'Characteristic {char_path_or_uuid} not found')
        return write(p, data)

    def disconnect(self) -> bool:
        return disconnect(self.address)


def start_discovery(iface: str = 'hci0'):
    return asyncio.run(_start_discovery(iface))


def stop_discovery(iface: str = 'hci0'):
    return asyncio.run(_stop_discovery(iface))


def disconnect(address: str):
    return asyncio.run(_disconnect(address))


def list_chars(address: str):
    return asyncio.run(_list_chars_for(address))


def read(char_path: str) -> bytes:
    return asyncio.run(_read_char(char_path))


def write(char_path: str, data: bytes) -> bool:
    return asyncio.run(_write_char(char_path, data))


async def _read_char_by_address(address: str, uuid: str | None = None) -> bytes:
    # Ensure device exists and find characteristic path
    path = await _device_path_for_address(address)
    if not path:
        raise RuntimeError('Device not found')

    # Find matching characteristic path
    chars = await _list_chars_for(address)
    char_path = None
    if uuid:
        for c in chars:
            if c.get('uuid', '').lower() == uuid.lower():
                char_path = c.get('path')
                break
        if not char_path:
            raise RuntimeError(f'Characteristic {uuid} not found for {address}')
    else:
        if not chars:
            raise RuntimeError(f'No characteristics found for {address}')
        char_path = chars[0].get('path')

    # Connect if not connected
    objs = await _get_managed_objects()
    dev_ifaces = objs.get(path, {})
    connected = bool(_unwrap(dev_ifaces.get('org.bluez.Device1', {}).get('Connected') if dev_ifaces else False))
    if not connected:
        try:
            await _connect(address)
        except Exception:
            # _connect prints error
            pass

    return await _read_char(char_path)


def read_by_address(address: str, uuid: str | None = None) -> bytes:
    """Read a characteristic by device `address` and optional `uuid`.

    If `uuid` is omitted the first characteristic found will be read.
    This will attempt to connect the device if not already connected.
    """
    return asyncio.run(_read_char_by_address(address, uuid))


def read_auto(target: str, uuid: str | None = None) -> bytes:
    """Read a characteristic when `target` is either a char path or a device address.

    - If `target` looks like an object path (starts with '/org/bluez/'), the
      existing `read()` behavior is used.
    - Otherwise `target` is treated as a device address and `uuid` must be
      supplied or the first characteristic will be read.
    """
    if target.startswith('/org/bluez/'):
        return read(target)
    return read_by_address(target, uuid)


# Rich table helpers for interactive shell
_console = Console()


def show_devices():
    """Pretty-print discovered devices as a Rich table."""
    devs = asyncio.run(_list_devices_with_discovery())
    t = Table(title="Bluetooth Devices")
    t.add_column("Path", no_wrap=True)
    t.add_column("Address")
    t.add_column("Name")
    t.add_column("Connected")
    for d in devs:
        t.add_row(d.get('path', ''), d.get('address', ''), str(d.get('name', '')), str(d.get('connected', False)))
    _console.print(t)


def show_chars(address: str):
    """Pretty-print GATT characteristics for a device address as a Rich table."""
    chs = list_chars(address)
    t = Table(title=f"GATT Chars for {address}")
    t.add_column("Path", no_wrap=True)
    t.add_column("UUID")
    t.add_column("Flags")
    for c in chs:
        t.add_row(c.get('path', ''), c.get('uuid', ''), ','.join(c.get('flags', [])))
    _console.print(t)


def main() -> int:
    ap = argparse.ArgumentParser(prog='gatt-cli')
    ap.add_argument('--iface', '-i', default='hci0')
    args = ap.parse_args()

    banner = (
        "gatt-cli interactive shell\n"
        "Helpers:\n"
        "  - list_devices()        : print devices table (returns None)\n"
        "  - get_devices()         : return device list for scripts\n"
        "  - connect(addr)         : connect and return DeviceSession\n"
        "      svc.list_chars()\n"
        "      svc.read(char_path_or_uuid)\n"
        "      svc.write(char_path_or_uuid, bytes)\n"
        "      svc.disconnect()\n"
        "  - read_by_address(addr, uuid=None) : read char by addr (auto-connect)\n"
        "  - read_auto(target, uuid=None)     : target is char path or address\n"
        "  - show_devices(), show_chars(addr): Rich table helpers\n"
        "  - start_discovery()/stop_discovery(): control adapter discovery\n"
    )
    embed(colors='Linux', banner1=banner, user_ns={
        'list_devices': list_devices,
        'get_devices': get_devices,
        'connect': connect,
        'disconnect': disconnect,
        'list_chars': list_chars,
        'read': read,
        'write': write,
        'read_by_address': read_by_address,
        'read_auto': read_auto,
        'show_devices': show_devices,
        'show_chars': show_chars,
        'start_discovery': start_discovery,
        'stop_discovery': stop_discovery,
    })
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
