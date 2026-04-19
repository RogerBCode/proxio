from collections.abc import AsyncGenerator

import httpx

from proxio.models import Node
from proxio.nodes import Nodes


class ProxmoxClient(httpx.AsyncClient):
    """Proxmox Client."""

    def __init__(self, host: str, token: str, verify: bool = True, trust_env: bool = True) -> None:
        self.api_token = token
        self.host = host
        transport = httpx.AsyncHTTPTransport(retries=3, verify=verify)

        super().__init__(
            mounts={"all://": transport},
            base_url=f"https://{self.host}:8006/api2/json",
            headers={"Authorization": f"PVEAPIToken={self.api_token}"},
            timeout=httpx.Timeout(30.0, connect=10.0),
            verify=verify,
            trust_env=trust_env,
        )
        base = str(self.base_url).rstrip("/")
        self.nodes = Nodes(self, httpx.URL(f"{base}/nodes"))
        self._cluster_nextid_url = httpx.URL(f"{base}/cluster/nextid")

    async def next_vmid(self) -> int:
        """Return the next free VMID in the cluster."""
        response = await self.get(self._cluster_nextid_url)
        response.raise_for_status()
        return int(response.json()["data"])

    async def get_nodes(self) -> AsyncGenerator[Node, None]:
        response = await self.nodes.list()
        response.raise_for_status()
        for n in response.json()["data"]:
            yield Node.from_data(n, self.nodes(n["node"]))

    async def get_node(self, name: str) -> Node:
        """Return a single node by name.

        Raises ``LookupError`` if no node with that name exists in the cluster.
        """
        response = await self.nodes.list()
        response.raise_for_status()
        for n in response.json()["data"]:
            if n["node"] == name:
                return Node.from_data(n, self.nodes(n["node"]))
        raise LookupError(f"No node named {name!r} found in the cluster")
