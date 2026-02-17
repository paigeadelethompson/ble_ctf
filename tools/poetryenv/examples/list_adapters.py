#!/usr/bin/env python3
"""List Bluetooth HCI adapters on the host.

This utility prefers reading `/sys/class/bluetooth` and falls back to
`hciconfig` output. Prints a table of interfaces, addresses and state.
"""
import sys
from rich.table import Table
from rich.console import Console


def main():
    # Use dbus-next asyncio API to connect to system bus and query BlueZ
    import asyncio
    from dbus_next.aio import MessageBus
    from dbus_next.constants import BusType

    async def run():
        bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        try:
            root_introspect = await bus.introspect('org.bluez', '/')
            obj = bus.get_proxy_object('org.bluez', '/', root_introspect)
            manager = obj.get_interface('org.freedesktop.DBus.ObjectManager')
            managed = await manager.call_get_managed_objects()
        except Exception as e:
            print(f"Failed to query BlueZ via D-Bus: {e}", file=sys.stderr)
            return 3

        adapters = []
        def _unwrap(v):
            try:
                return v.value
            except Exception:
                return v

        for path, interfaces in managed.items():
            if 'org.bluez.Adapter1' in interfaces:
                props = interfaces['org.bluez.Adapter1']
                iface = path.rsplit('/', 1)[-1]
                address = _unwrap(props.get('Address', '') or '')
                powered = bool(_unwrap(props.get('Powered', False)))
                adapters.append({'iface': iface, 'address': address, 'powered': powered, 'props': props})

        console = Console()
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Interface", style="dim", width=8)
        table.add_column("Address", width=20)
        table.add_column("State", width=12)
        table.add_column("Details", overflow="fold")

        for a in adapters:
            iface = a['iface']
            address = a.get('address', '')
            state = 'up' if a.get('powered') else 'down'
            details = ', '.join(f"{k}={_unwrap(v)}" for k, v in a.get('props', {}).items())
            table.add_row(iface, address, state, details)

        console.print(table)
        return 0

    return asyncio.run(run())


if __name__ == '__main__':
    main()
