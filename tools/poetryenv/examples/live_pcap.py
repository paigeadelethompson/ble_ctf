#!/usr/bin/env python3
"""Scapy-only DBus BLE live streamer (layer.summary output).

Prints concatenated Scapy layer summary strings for each discovered device:
  <layer1_summary> / <layer2_summary> / ...

This file uses direct imports (no try/except) so missing Scapy layers
will raise ImportError as requested.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Any, Dict, Optional

from dbus_next.aio import MessageBus
from dbus_next.constants import BusType

from scapy.layers.bluetooth import HCI_LE_Meta_Advertising_Report  # type: ignore
from scapy.packet import NoPayload  # type: ignore


def _unwrap_variant(v: Any) -> Any:
    try:
        return v.value
    except Exception:
        return v


async def stream_summaries(iface: str, poll: float = 0.5, duration: Optional[float] = None) -> int:
    bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
    root_introspect = await bus.introspect('org.bluez', '/')
    root = bus.get_proxy_object('org.bluez', '/', root_introspect)
    manager = root.get_interface('org.freedesktop.DBus.ObjectManager')

    adapter_path = f"/org/bluez/{iface}"
    try:
        adapter_introspect = await bus.introspect('org.bluez', adapter_path)
        adapter_obj = bus.get_proxy_object('org.bluez', adapter_path, adapter_introspect)
        adapter = adapter_obj.get_interface('org.bluez.Adapter1')
    except Exception as exc:
        print("Adapter error:", exc, file=sys.stderr)
        return 2

    try:
        await adapter.call_start_discovery()
    except Exception:
        pass

    seen: Dict[str, Dict[str, Any]] = {}
    start_ts = asyncio.get_event_loop().time()

    try:
        while True:
            if duration is not None and asyncio.get_event_loop().time() - start_ts >= duration:
                break

            managed = await manager.call_get_managed_objects()
            for path, ifaces in managed.items():
                props = ifaces.get('org.bluez.Device1')
                if not props:
                    continue

                addr = _unwrap_variant(props.get('Address') or props.get('address') or '')
                if not addr:
                    continue

                name = _unwrap_variant(props.get('Name') or props.get('Alias') or '') or ''
                rssi_v = _unwrap_variant(props.get('RSSI') or props.get('rssi') or None)
                try:
                    rssi = int(rssi_v) if rssi_v is not None and rssi_v != '' else None
                except Exception:
                    rssi = None

                manuf = _unwrap_variant(props.get('ManufacturerData') or props.get('manufacturer_data') or {})
                svc = _unwrap_variant(props.get('ServiceData') or props.get('service_data') or {})

                prev = seen.get(addr)
                changed = prev is None or prev.get('name') != name or prev.get('rssi') != rssi or prev.get('manuf') != manuf or prev.get('svc') != svc
                if not changed:
                    continue

                # Build an HCI_LE_Meta_Advertising_Report with combined raw data bytes
                def _to_bytes(x: Any) -> bytes:
                    try:
                        if isinstance(x, dict):
                            parts = []
                            for _, v in x.items():
                                try:
                                    parts.append(bytes(v))
                                except Exception:
                                    parts.append(str(v).encode('utf-8'))
                            return b"".join(parts)
                        return bytes(x)
                    except Exception:
                        return str(x).encode('utf-8')

                data_bytes = _to_bytes(manuf) + _to_bytes(svc)
                pkt = HCI_LE_Meta_Advertising_Report(addr=addr, len=len(data_bytes), data=data_bytes, rssi=(rssi or 0))

                # Build a richer string: layer summaries plus key fields
                # For HCI_LE_Meta_Advertising_Report include addr, rssi, len and hex(data)
                try:
                    data_hex = data_bytes.hex() if data_bytes else ""
                except Exception:
                    data_hex = str(data_bytes)
                line_parts = [
                    pkt.__class__.__name__,
                    "addr=" + str(pkt.addr),
                    "rssi=" + str(getattr(pkt, 'rssi', '')),
                    "len=" + str(getattr(pkt, 'len', '')),
                    "data=0x" + data_hex,
                ]
                print(' / '.join(line_parts))
                sys.stdout.flush()

                seen[addr] = {'name': name, 'rssi': rssi, 'manuf': manuf, 'svc': svc}

            await asyncio.sleep(poll)
    finally:
        try:
            await adapter.call_stop_discovery()
        except Exception:
            pass

    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog='live-pcap-summary')
    ap.add_argument('--iface', '-i', default='hci0')
    ap.add_argument('--poll', type=float, default=0.5)
    ap.add_argument('--duration', type=float, default=None)
    args = ap.parse_args()

    return asyncio.run(stream_summaries(args.iface, poll=args.poll, duration=args.duration))


if __name__ == '__main__':
    raise SystemExit(main())
