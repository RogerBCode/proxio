from __future__ import annotations

import asyncio
import base64
import fnmatch
from typing import TYPE_CHECKING, Any, Optional

import httpx
from pydantic import BaseModel, Field


class RootFS(BaseModel):
    avail: int
    total: int
    free: int
    used: int


class CurrentKernel(BaseModel):
    sysname: str
    machine: str
    version: str
    release: str


class KSM(BaseModel):
    shared: int


class Swap(BaseModel):
    total: int
    used: int
    free: int


class BootInfo(BaseModel):
    mode: str


class Memory(BaseModel):
    used: int
    free: int
    total: int


class CPUInfo(BaseModel):
    model: str
    cores: int
    user_hz: int
    mhz: str
    cpus: int
    flags: str
    hvm: str
    sockets: int


class NodeStatus(BaseModel):
    rootfs: RootFS
    current_kernel: Optional[CurrentKernel] = Field(None, alias="current_kernel")
    kversion: Optional[str] = None
    ksm: Optional[KSM] = None
    uptime: Optional[int] = None
    pveversion: Optional[str] = None
    cpu: Optional[float] = None
    loadavg: Optional[list[str]] = None
    swap: Optional[Swap] = None
    boot_info: Optional[BootInfo] = Field(None, alias="boot_info")
    idle: Optional[float] = None
    memory: Optional[Memory] = None
    cpuinfo: Optional[CPUInfo] = None
    wait: Optional[float] = None
    status: Optional[str] = None

    class Config:
        extra = "allow"
        allow_population_by_field_name = True


if TYPE_CHECKING:
    from collections.abc import Awaitable


class VmAgent(BaseModel):
    """Domain-level interface to the QEMU guest agent for a virtual machine."""

    resource: Any

    class Config:
        arbitrary_types_allowed = True

    async def ping(self) -> None:
        response = await self.resource.ping()
        response.raise_for_status()

    async def exec(
        self,
        command: str,
        args: list[str] | None = None,
        input_data: str | None = None,
        timeout: float = 60.0,
        poll_interval: float = 1.0,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"command": command}
        if args:
            payload["args"] = args
        if input_data is not None:
            payload["input-data"] = input_data
        response = await self.resource.exec(payload)
        response.raise_for_status()
        pid: int = response.json()["data"]["pid"]
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while loop.time() < deadline:
            status_response = await self.resource.exec_status(pid)
            status_response.raise_for_status()
            data = status_response.json()["data"]
            if data.get("exited"):
                exitcode = data.get("exitcode", -1)
                if exitcode != 0:
                    stderr = data.get("err-data", "")
                    raise RuntimeError(f"Agent exec {command!r} exited with code {exitcode}: {stderr}")
                return data
            await asyncio.sleep(poll_interval)
        raise TimeoutError(f"Agent exec {command!r} (pid {pid}) did not finish within {timeout}s")

    async def get_osinfo(self) -> dict[str, Any]:
        response = await self.resource.get_osinfo()
        response.raise_for_status()
        return response.json()["data"]["result"]

    async def get_hostname(self) -> str | None:
        response = await self.resource.get_hostname()
        if response.status_code == 500:
            return None
        response.raise_for_status()
        return response.json()["data"]["result"]["host-name"]

    async def get_network_interfaces(self) -> list[dict[str, Any]]:
        response = await self.resource.get_network_interfaces()
        response.raise_for_status()
        return response.json()["data"]["result"]

    async def get_fsinfo(self) -> list[dict[str, Any]]:
        response = await self.resource.get_fsinfo()
        response.raise_for_status()
        return response.json()["data"]["result"]

    async def get_users(self) -> list[dict[str, Any]]:
        response = await self.resource.get_users()
        response.raise_for_status()
        return response.json()["data"]["result"]

    async def set_user_password(self, username: str, password: str, crypted: bool = False) -> None:
        response = await self.resource.set_user_password(username, password, crypted=crypted)
        response.raise_for_status()

    async def file_read(self, path: str) -> bytes:
        response = await self.resource.file_read(path)
        response.raise_for_status()
        return base64.b64decode(response.json()["data"]["content"])

    async def file_write(self, path: str, content: bytes) -> None:
        encoded = base64.b64encode(content).decode()
        response = await self.resource.file_write(path, encoded, encode=False)
        response.raise_for_status()


class VirtualMachine(BaseModel):
    """Domain model for a Proxmox QEMU virtual machine."""

    vmid: int
    name: str
    node: str
    cpus: int
    maxmem: int
    maxdisk: int
    tags: str
    template: bool
    resource: Any
    node_resource: Any
    agent: VmAgent = None

    class Config:
        arbitrary_types_allowed = True

    def __init__(self, **data):
        super().__init__(**data)
        # Initialize agent after resource is set
        object.__setattr__(self, "agent", VmAgent(resource=self.resource.agent))

    @classmethod
    def from_data(cls, data: dict[str, Any], node: str, resource: Any, node_resource: Any) -> "VirtualMachine":
        return cls(
            vmid=data["vmid"],
            name=data.get("name", str(data["vmid"])),
            node=node,
            cpus=data["cpus"],
            maxmem=data["maxmem"],
            maxdisk=data["maxdisk"],
            tags=data.get("tags", ""),
            template=bool(data.get("template", 0)),
            resource=resource,
            node_resource=node_resource,
        )

    # --- Async runtime accessors (always fetch live from the API) ---

    async def _get_runtime(self) -> dict[str, Any]:
        response = await self.resource.status.current()
        response.raise_for_status()
        return response.json()["data"]

    async def get_status(self) -> str:
        data = await self._get_runtime()
        return data["status"]

    async def get_cpu(self) -> float:
        data = await self._get_runtime()
        return data.get("cpu", 0.0)

    async def get_mem(self) -> int:
        data = await self._get_runtime()
        return data.get("mem", 0)

    async def get_uptime(self) -> int:
        data = await self._get_runtime()
        return data.get("uptime", 0)

    async def get_runtime(self) -> dict[str, Any]:
        return await self._get_runtime()

    # --- Task helpers ---

    async def _wait_for_task(self, upid: str, timeout: float = 300.0, poll_interval: float = 2.0) -> None:
        """Poll a Proxmox task until it completes, raising on failure or timeout."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while loop.time() < deadline:
            response = await self.node_resource.tasks.get_status(upid)
            response.raise_for_status()
            data = response.json()["data"]
            if data.get("status") == "stopped":
                exitstatus = data.get("exitstatus", "unknown")
                if exitstatus != "OK":
                    raise RuntimeError(f"Task {upid!r} failed: {exitstatus}")
                return
            await asyncio.sleep(poll_interval)
        raise TimeoutError(f"Task {upid!r} did not complete within {timeout}s")

    async def _run_task_and_wait(self, api_coro: Awaitable[httpx.Response], timeout: float = 300.0) -> None:
        """Run an API coroutine, extract UPID, wait for completion, then invalidate cache."""
        response = await api_coro
        response.raise_for_status()
        upid = response.json()["data"]
        await self._wait_for_task(upid, timeout=timeout)

    # --- Power state ---

    async def start(self, timeout: float = 300.0) -> None:
        """Start the VM and block until it is running."""
        await self._run_task_and_wait(self.resource.status.start(), timeout=timeout)

    async def stop(self, timeout: float = 300.0) -> None:
        """Stop the VM and block until it is stopped."""
        await self._run_task_and_wait(self.resource.status.stop(), timeout=timeout)

    async def shutdown(self, timeout: float = 300.0) -> None:
        """Gracefully shut down the VM and block until it is stopped."""
        await self._run_task_and_wait(self.resource.status.shutdown(), timeout=timeout)

    async def reset(self, timeout: float = 300.0) -> None:
        """Reset the VM and block until the task completes."""
        await self._run_task_and_wait(self.resource.status.reset(), timeout=timeout)

    async def suspend(self, timeout: float = 300.0) -> None:
        """Suspend the VM and block until the task completes."""
        await self._run_task_and_wait(self.resource.status.suspend(), timeout=timeout)

    async def resume(self, timeout: float = 300.0) -> None:
        """Resume the VM and block until the task completes."""
        await self._run_task_and_wait(self.resource.status.resume(), timeout=timeout)

    # --- Snapshots ---

    async def snapshot(self, snapname: str, description: str = "", timeout: float = 300.0) -> None:
        """Create a snapshot and block until the task completes."""
        await self._run_task_and_wait(
            self.resource.snapshots.create({"snapname": snapname, "description": description}),
            timeout=timeout,
        )

    async def rollback(self, snapname: str, timeout: float = 300.0) -> None:
        """Rollback to a snapshot and block until the task completes."""
        await self._run_task_and_wait(self.resource.snapshots.rollback(snapname), timeout=timeout)

    async def list_snapshots(self) -> httpx.Response:
        return await self.resource.snapshots.list()

    # --- Config / lifecycle ---

    async def get_config(self) -> httpx.Response:
        return await self.resource.get_config()

    @staticmethod
    def _build_clone_payload(
        newid: int,
        name: str,
        description: str | None,
        snapname: str | None,
        target: str | None,
        pool: str | None,
        full: bool | None,
        storage: str | None,
        bwlimit: int | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"newid": newid, "name": name}
        optional: dict[str, Any] = {
            "description": description,
            "snapname": snapname,
            "target": target,
            "pool": pool,
            "storage": storage,
            "bwlimit": bwlimit,
        }
        payload.update({k: v for k, v in optional.items() if v is not None})
        if full is not None:
            payload["full"] = int(full)
        return payload

    async def clone(
        self,
        name: str,
        *,
        newid: int | None = None,
        description: str | None = None,
        snapname: str | None = None,
        target: str | None = None,
        pool: str | None = None,
        full: bool | None = None,
        storage: str | None = None,
        bwlimit: int | None = None,
        timeout: float = 600.0,
    ) -> VirtualMachine:
        """Clone the VM, block until the task completes, and return the new VirtualMachine.

        Raises ``RuntimeError`` if the VM is currently running.
        Raises ``ValueError`` if ``full=False`` and no ``snapname`` is provided.

        Args:
            newid: VMID for the clone. Auto-assigned from the cluster if not provided.
            name: Name for the clone.
            description: Description for the clone.
            snapname: Snapshot to clone from. Required when ``full=False``.
            target: Target node. Defaults to the same node as the source VM.
            pool: Resource pool to assign the clone to.
            full: ``True`` for a full clone (independent disk copy), ``False`` for a linked clone.
            storage: Target storage for the clone's disks (required for full clones across storage).
            bwlimit: I/O bandwidth limit in KiB/s during the clone operation.
            timeout: Seconds to wait for the clone task to complete.

        """
        status = await self.get_status()
        if status == "running":
            raise RuntimeError(f"Cannot clone VM {self.vmid} ({self.name!r}): VM is currently running")

        if full is False and snapname is None:
            raise ValueError("A linked clone (full=False) requires a snapname to be specified")

        if newid is None:
            newid = await self.node_resource.next_vmid()

        payload = self._build_clone_payload(newid, name, description, snapname, target, pool, full, storage, bwlimit)
        await self._run_task_and_wait(self.resource.clone(payload), timeout=timeout)

        target_node: str = target if target is not None else self.node
        node_resource = self.node_resource if target_node == self.node else self.node_resource.sibling(target_node)
        vm_resource = node_resource.qemu(newid)
        response = await vm_resource.get_config()
        response.raise_for_status()
        config = response.json()["data"]
        vm_data: dict[str, Any] = {
            "vmid": newid,
            "name": config.get("name", str(newid)),
            "cpus": config.get("cores", 1),
            "maxmem": config.get("memory", 0) * 1024 * 1024,
            "maxdisk": 0,
            "tags": config.get("tags", ""),
            "template": int(config.get("template", 0)),
        }
        return VirtualMachine.from_data(vm_data, node=target_node, resource=vm_resource, node_resource=node_resource)

    async def migrate(self, data: dict[str, Any], timeout: float = 600.0) -> None:
        """Migrate the VM and block until the task completes."""
        await self._run_task_and_wait(self.resource.migrate(data), timeout=timeout)

    async def delete(self, timeout: float = 300.0) -> None:
        """Delete the VM and block until the task completes."""
        await self._run_task_and_wait(self.resource.delete(), timeout=timeout)


class Node(BaseModel):
    """Domain model for a Proxmox node (from /nodes list)."""

    node: str
    type: str
    maxcpu: int
    maxmem: int
    maxdisk: int
    cpu: float
    mem: int
    disk: int
    uptime: int
    status: str
    ssl_fingerprint: str
    id: str
    level: str
    resource: Any = None

    class Config:
        arbitrary_types_allowed = True
        extra = "allow"

    @classmethod
    def from_data(cls, data: dict[str, Any], resource: Any = None) -> "Node":
        return cls(resource=resource, **data)

    # --- Async runtime accessors (always fetch live from the API) ---

    async def _get_runtime(self) -> dict[str, Any]:
        response = await self.resource.get_status()
        response.raise_for_status()
        return response.json()["data"]

    async def get_status(self) -> NodeStatus:
        try:
            data = await self._get_runtime()
        except httpx.TransportError:
            return NodeStatus(rootfs=RootFS(avail=0, total=0, free=0, used=0), status="offline")

        return NodeStatus(**data)

    async def get_cpu(self) -> float:
        data = await self._get_runtime()
        return data.get("cpu", 0.0)

    async def get_mem(self) -> int:
        data = await self._get_runtime()
        return data.get("mem", 0)

    async def get_disk(self) -> int:
        data = await self._get_runtime()
        return data.get("disk", 0)

    async def get_uptime(self) -> int:
        data = await self._get_runtime()
        return data.get("uptime", 0)

    async def get_runtime(self) -> dict[str, Any]:
        return await self._get_runtime()

    async def list_vms(self, template: bool | None = None, name: str | None = None) -> list[VirtualMachine]:
        response = await self.resource.qemu.list()
        response.raise_for_status()
        vms = [
            VirtualMachine.from_data(vm_data, node=self.node, resource=self.resource.qemu(vm_data["vmid"]), node_resource=self.resource)
            for vm_data in response.json()["data"]
        ]
        if template is not None:
            vms = [vm for vm in vms if vm.template is template]
        if name is not None:
            vms = [vm for vm in vms if fnmatch.fnmatch(vm.name, name)]
        return vms

    async def get_vm(self, *, vmid: int | None = None, name: str | None = None) -> VirtualMachine:
        if vmid is None and name is None:
            raise ValueError("At least one of 'vmid' or 'name' must be provided")

        vms = await self.list_vms()

        if vmid is not None:
            by_id = next((vm for vm in vms if vm.vmid == vmid), None)
            if by_id is None:
                raise LookupError(f"No VM with vmid={vmid} found on node {self.node!r}")
            if name is not None and not fnmatch.fnmatch(by_id.name, name):
                raise LookupError(f"VM vmid={vmid} exists but its name {by_id.name!r} does not match {name!r}")
            return by_id

        matches = [vm for vm in vms if fnmatch.fnmatch(vm.name, name)]  # type: ignore[arg-type]
        if not matches:
            raise LookupError(f"No VM with name matching {name!r} found on node {self.node!r}")
        if len(matches) > 1:
            ids = [vm.vmid for vm in matches]
            raise LookupError(f"Multiple VMs match name {name!r} on node {self.node!r}: vmids={ids}")
        return matches[0]
