"""
Sample script: list all nodes in the Proxmox cluster.

Copy .env.example to .env and fill in your API token before running:
    uv run examples/list_nodes.py
"""

import asyncio

from settings import Settings

from proxio.client import ProxmoxClient


async def main() -> None:
    settings = Settings()
    async with ProxmoxClient(host=settings.prox_host, token=settings.prox_api_token, verify=False, trust_env=True) as client:
        async for node in client.get_nodes():
            print(node)


if __name__ == "__main__":
    asyncio.run(main())
