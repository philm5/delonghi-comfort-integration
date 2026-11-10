# /// script
# requires-python = ">=3.14.2,<3.15"
# dependencies = ["homeassistant==2026.11.1"]
# ///
"""
Dump raw De'Longhi API responses for device discovery.

Usage:
    DELONGHI_USERNAME=you@email.com DELONGHI_PASSWORD=secret uv run discover.py

Run from the repository root. uv uses the inline script dependencies rather
than the project's .venv or uv.lock.

Output is written to stdout (pipe to a file to save):
    ... | tee discovery_output.json
"""

import asyncio
import json
import os
import sys

import aiohttp

sys.path.insert(0, ".")
from custom_components.delonghi_comfort.api import DeLonghiAPI


async def main() -> None:
    username = os.environ.get("DELONGHI_USERNAME")
    password = os.environ.get("DELONGHI_PASSWORD")

    if not username or not password:
        print(
            "ERROR: Set DELONGHI_USERNAME and DELONGHI_PASSWORD environment variables.",
            file=sys.stderr,
        )
        sys.exit(1)

    async with aiohttp.ClientSession() as session:
        api = DeLonghiAPI(username, password, session, "en")

        print("Authenticating...", file=sys.stderr)
        if not await api.authenticate():
            print("ERROR: Authentication failed.", file=sys.stderr)
            sys.exit(1)
        print("OK\n", file=sys.stderr)

        devices = await api.get_devices()
        print("=== DEVICES ===")
        print(json.dumps(devices, indent=2))

        for device in devices:
            info = device["device"]
            dsn = info["dsn"]
            name = info.get("product_name", dsn)
            oem_model = info.get("oem_model", "unknown")

            print(f"\n=== PROPERTIES: {name}  |  oem_model={oem_model}  |  dsn={dsn} ===")
            props = await api.get_device_properties(dsn)
            print(json.dumps(props, indent=2))

            # Summarise property names and current values in a compact table
            print(f"\n--- SUMMARY: {name} ---")
            for prop in props:
                if "property" in prop:
                    p = prop["property"]
                    writable = "rw" if p.get("read_only") is False else "ro"
                    print(f"  [{writable}]  {p['name']:<40}  = {p['value']}")


asyncio.run(main())
