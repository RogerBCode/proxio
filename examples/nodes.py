"""
Sample script: list all nodes in the Proxmox cluster.

Copy .env.example to .env and fill in your API token before running:
    uv run examples/list_nodes.py
"""

import asyncio
from pprint import pprint

from settings import Settings

from proxio.client import ProxmoxClient


async def list_nodes() -> None:
    settings = Settings()
    async with ProxmoxClient(host=settings.prox_host, token=settings.prox_api_token, verify=False, trust_env=True) as client:
        async for node in client.get_nodes():
            pprint(node)


async def get_single_node(name: str) -> None:
    settings = Settings()
    async with ProxmoxClient(host=settings.prox_host, token=settings.prox_api_token, verify=False, trust_env=True) as client:
        try:
            node = await client.get_node(name)
        except LookupError:
            print(f"No node named {name!r} found in the cluster")
        else:
            pprint(node)
            node_status = await node.get_status()
            pprint(node_status, indent=4, width=160, compact=True, sort_dicts=True)


async def main() -> None:
    await list_nodes()
    await get_single_node("pve")


if __name__ == "__main__":
    asyncio.run(main())
