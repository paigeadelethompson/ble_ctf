#!/usr/bin/env python3
"""Simple continuous BLE scanner that prints a Rich table to stdout.

This version intentionally does not use any TUI framework — it repeatedly
prints a properly formatted Rich table to stdout so the terminal scrolls.
Use Ctrl-C to stop.
"""
from __future__ import annotations

import argparse
import asyncio
import datetime
import io
import sys
from typing import Dict, Optional

from rich.console import Console
from rich.table import Table


def build_table(devices: Dict[str, Dict], max_rows: Optional[int] = None) -> Table:
    t = Table(show_header=True, header_style="bold cyan")
    t.add_column("Address", style="dim", width=17)
    t.add_column("Name", overflow="fold")
    t.add_column("RSSI", justify="right", width=6)
    t.add_column("Last Seen", justify="right", width=10)

    rows = 0
    for addr, info in sorted(devices.items()):
        if max_rows is not None and rows >= max_rows:
            break
        t.add_row(addr, info.get('name', ''), str(info.get('rssi', '')), info.get('last_seen', ''))
        rows += 1
    return t


async def scan_loop(iface: str, interval: float = 1.0, duration: Optional[float] = None) -> int:
    from dbus_next.aio import MessageBus
    from dbus_next.constants import BusType

    bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
    root_introspect = await bus.introspect('org.bluez', '/')
    root_obj = bus.get_proxy_object('org.bluez', '/', root_introspect)
    manager = root_obj.get_interface('org.freedesktop.DBus.ObjectManager')

    adapter_path = f"/org/bluez/{iface}"
    adapter_introspect = await bus.introspect('org.bluez', adapter_path)
    adapter_obj = bus.get_proxy_object('org.bluez', adapter_path, adapter_introspect)
    adapter = adapter_obj.get_interface('org.bluez.Adapter1')

    devices: Dict[str, Dict] = {}
    console = Console(file=sys.stdout)

    try:
        await adapter.call_start_discovery()
    except Exception as e:
        console.print(f"[yellow]Warning: start_discovery failed: {e}[/]")

    start = asyncio.get_event_loop().time()
    try:
        while True:
            if duration is not None and asyncio.get_event_loop().time() - start >= duration:
                break

            objs = await manager.call_get_managed_objects()
            for path, ifaces in objs.items():
                if 'org.bluez.Device1' not in ifaces:
                    continue
                props = ifaces['org.bluez.Device1']
                addr = getattr(props.get('Address') or props.get('address') or '', 'value', props.get('Address') or props.get('address') or '')
                if not addr:
                    continue
                name = getattr(props.get('Name') or props.get('Alias') or '', 'value', props.get('Name') or props.get('Alias') or '')
                rssi_raw = getattr(props.get('RSSI') or props.get('rssi') or None, 'value', props.get('RSSI') or props.get('rssi') or None)
                try:
                    rssi_val = int(rssi_raw) if rssi_raw is not None and rssi_raw != '' else ''
                except Exception:
                    rssi_val = ''

                devices[str(addr)] = {
                    'name': str(name) if name else '',
                    'rssi': rssi_val,
                    'last_seen': datetime.datetime.now().strftime('%H:%M:%S'),
                }

            total = len(devices)
            with_rssi = sum(1 for v in devices.values() if v.get('rssi') != '')
            # Render table to a plain-text buffer (no ANSI) then write to stdout
            buf = io.StringIO()
            plain_console = Console(file=buf, force_terminal=False, color_system=None)
            plain_console.print(f"Discovered: {total}   With RSSI: {with_rssi}")
            plain_console.print(build_table(devices))
            sys.stdout.write(buf.getvalue())
            sys.stdout.flush()

            await asyncio.sleep(interval)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            await adapter.call_stop_discovery()
        except Exception:
            pass

    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog='scan-ble')
    ap.add_argument('--iface', default='hci0')
    ap.add_argument('--interval', type=float, default=1.0, help='Seconds between table prints')
    ap.add_argument('--duration', type=float, default=None, help='Optional total scan duration in seconds')
    args = ap.parse_args()

    return asyncio.run(scan_loop(args.iface, interval=args.interval, duration=args.duration))


if __name__ == '__main__':
    raise SystemExit(main())
