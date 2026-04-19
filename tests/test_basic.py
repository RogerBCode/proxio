import base64
from unittest.mock import AsyncMock, MagicMock

import anyio
import httpx
import pytest

from proxio import version
from proxio.client import ProxmoxClient
from proxio.models import Node, VirtualMachine, VmAgent
from proxio.nodes import NodeResource, Nodes, QemuEndpoint, VmResource

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resp(data=None, status_code=200):
    """Build a mock httpx.Response."""
    mock = MagicMock(spec=httpx.Response)
    mock.status_code = status_code
    mock.json.return_value = {"data": data} if data is not None else {}
    if status_code >= 400:
        mock.raise_for_status.side_effect = httpx.HTTPStatusError("error", request=MagicMock(), response=mock)
    else:
        mock.raise_for_status.return_value = None
    return mock


_VM_DATA = {
    "vmid": 100,
    "name": "test-vm",
    "cpus": 2,
    "maxmem": 2 * 1024**3,
    "maxdisk": 10 * 1024**3,
    "tags": "web",
    "template": 0,
}

_NODE_DATA = {
    "node": "pve1",
    "type": "node",
    "maxcpu": 8,
    "maxmem": 16 * 1024**3,
    "maxdisk": 100 * 1024**3,
    "cpu": 0.0,
    "mem": 0,
    "disk": 0,
    "uptime": 0,
    "status": "online",
    "ssl_fingerprint": "",
    "id": "node/pve1",
    "level": "",
}


def _make_vm_resource():
    r = MagicMock()
    return r


def _make_node_resource():
    return MagicMock()


def _make_vm(vmid=100, name="test-vm", node="pve1", template=False, resource=None, node_resource=None):
    return VirtualMachine(
        vmid=vmid,
        name=name,
        node=node,
        cpus=2,
        maxmem=2 * 1024**3,
        maxdisk=10 * 1024**3,
        tags="",
        template=template,
        resource=resource or _make_vm_resource(),
        node_resource=node_resource or _make_node_resource(),
    )


def _make_node(node="pve1", resource=None):
    data = dict(_NODE_DATA)
    data["node"] = node
    return Node.from_data(data, resource=resource or MagicMock())


# ---------------------------------------------------------------------------
# proxio/__init__.py
# ---------------------------------------------------------------------------


def test_version():
    v = version()
    assert len(v.split(".")) == 3


def test_version_non_empty():
    v = version()
    assert v != ""


# ---------------------------------------------------------------------------
# proxio/nodes.py — synchronous construction
# ---------------------------------------------------------------------------


def test_nodes_call_returns_node_resource():
    client = MagicMock(spec=httpx.AsyncClient)
    nodes = Nodes(client, httpx.URL("https://pve:8006/api2/json/nodes"))
    resource = nodes("pve1")
    assert isinstance(resource, NodeResource)
    assert "pve1" in str(resource._base_url)


def test_node_resource_sibling():
    client = MagicMock(spec=httpx.AsyncClient)
    resource = NodeResource(client, httpx.URL("https://pve:8006/api2/json/nodes/pve1"))
    sibling = resource.sibling("pve2")
    assert isinstance(sibling, NodeResource)
    assert "pve2" in str(sibling._base_url)
    assert "pve1" not in str(sibling._base_url)


def test_qemu_endpoint_call_returns_vm_resource():
    client = MagicMock(spec=httpx.AsyncClient)
    qemu = QemuEndpoint(client, httpx.URL("https://pve:8006/api2/json/nodes/pve1/qemu"))
    vm_res = qemu(100)
    assert isinstance(vm_res, VmResource)
    assert "100" in str(vm_res._base_url)


# ---------------------------------------------------------------------------
# proxio/models.py — VirtualMachine static helpers
# ---------------------------------------------------------------------------


def test_virtual_machine_from_data():
    resource = _make_vm_resource()
    node_resource = _make_node_resource()
    vm = VirtualMachine.from_data(_VM_DATA, node="pve1", resource=resource, node_resource=node_resource)
    assert vm.vmid == 100
    assert vm.name == "test-vm"
    assert vm.node == "pve1"
    assert vm.cpus == 2
    assert vm.template is False
    assert vm.tags == "web"


def test_virtual_machine_from_data_template_flag():
    data = {**_VM_DATA, "template": 1, "name": "base-tpl"}
    vm = VirtualMachine.from_data(data, node="pve1", resource=_make_vm_resource(), node_resource=_make_node_resource())
    assert vm.template is True


def test_virtual_machine_from_data_missing_name_uses_vmid():
    data = {k: v for k, v in _VM_DATA.items() if k != "name"}
    vm = VirtualMachine.from_data(data, node="pve1", resource=_make_vm_resource(), node_resource=_make_node_resource())
    assert vm.name == str(data["vmid"])


def test_build_clone_payload_minimal():
    payload = VirtualMachine._build_clone_payload(200, "clone", None, None, None, None, None, None, None)
    assert payload == {"newid": 200, "name": "clone"}


def test_build_clone_payload_full_clone():
    payload = VirtualMachine._build_clone_payload(201, "full-clone", "desc", "snap1", "pve2", "pool1", True, "local-lvm", 1024)
    assert payload["full"] == 1
    assert payload["storage"] == "local-lvm"
    assert payload["snapname"] == "snap1"
    assert payload["target"] == "pve2"
    assert payload["description"] == "desc"
    assert payload["pool"] == "pool1"
    assert payload["bwlimit"] == 1024


def test_build_clone_payload_linked_clone():
    payload = VirtualMachine._build_clone_payload(202, "linked", None, None, None, None, False, None, None)
    assert payload["full"] == 0


def test_build_clone_payload_excludes_none_optionals():
    payload = VirtualMachine._build_clone_payload(203, "vm", None, None, None, None, None, None, None)
    for key in ("description", "snapname", "target", "pool", "storage", "bwlimit", "full"):
        assert key not in payload


# ---------------------------------------------------------------------------
# proxio/models.py — Node static helpers
# ---------------------------------------------------------------------------


def test_node_from_data():
    resource = MagicMock()
    node = Node.from_data(_NODE_DATA, resource=resource)
    assert node.node == "pve1"
    assert node.type == "node"
    assert node.maxcpu == 8
    assert node.resource is resource


# ---------------------------------------------------------------------------
# proxio/models.py — async VirtualMachine methods
# ---------------------------------------------------------------------------


def test_vm_get_status_running():
    async def _run():
        resource = _make_vm_resource()
        resource.status.current = AsyncMock(return_value=_resp({"status": "running", "cpu": 0.5}))
        vm = _make_vm(resource=resource)
        assert await vm.get_status() == "running"

    anyio.run(_run)


def test_vm_get_cpu():
    async def _run():
        resource = _make_vm_resource()
        resource.status.current = AsyncMock(return_value=_resp({"status": "running", "cpu": 0.75}))
        vm = _make_vm(resource=resource)
        assert await vm.get_cpu() == 0.75

    anyio.run(_run)


def test_vm_get_mem():
    async def _run():
        resource = _make_vm_resource()
        resource.status.current = AsyncMock(return_value=_resp({"status": "running", "mem": 1024}))
        vm = _make_vm(resource=resource)
        assert await vm.get_mem() == 1024

    anyio.run(_run)


def test_vm_clone_raises_when_running():
    async def _run():
        resource = _make_vm_resource()
        resource.status.current = AsyncMock(return_value=_resp({"status": "running"}))
        vm = _make_vm(resource=resource)
        with pytest.raises(RuntimeError, match="currently running"):
            await vm.clone("clone-vm", newid=200)

    anyio.run(_run)


def test_vm_clone_raises_linked_without_snapname():
    async def _run():
        resource = _make_vm_resource()
        resource.status.current = AsyncMock(return_value=_resp({"status": "stopped"}))
        vm = _make_vm(resource=resource)
        with pytest.raises(ValueError, match="linked clone"):
            await vm.clone("linked-clone", newid=200, full=False)

    anyio.run(_run)


def test_vm_start():
    async def _run():
        resource = _make_vm_resource()
        node_resource = _make_node_resource()
        upid = "UPID:pve1:start:task"
        resource.status.start = AsyncMock(return_value=_resp(upid))
        node_resource.tasks.get_status = AsyncMock(return_value=_resp({"status": "stopped", "exitstatus": "OK"}))
        vm = _make_vm(resource=resource, node_resource=node_resource)
        await vm.start()
        resource.status.start.assert_called_once()

    anyio.run(_run)


def test_vm_stop():
    async def _run():
        resource = _make_vm_resource()
        node_resource = _make_node_resource()
        upid = "UPID:pve1:stop:task"
        resource.status.stop = AsyncMock(return_value=_resp(upid))
        node_resource.tasks.get_status = AsyncMock(return_value=_resp({"status": "stopped", "exitstatus": "OK"}))
        vm = _make_vm(resource=resource, node_resource=node_resource)
        await vm.stop()
        resource.status.stop.assert_called_once()

    anyio.run(_run)


def test_vm_snapshot_and_rollback():
    async def _run():
        resource = _make_vm_resource()
        node_resource = _make_node_resource()
        upid = "UPID:pve1:snap:task"
        resource.snapshots.create = AsyncMock(return_value=_resp(upid))
        resource.snapshots.rollback = AsyncMock(return_value=_resp(upid))
        node_resource.tasks.get_status = AsyncMock(return_value=_resp({"status": "stopped", "exitstatus": "OK"}))
        vm = _make_vm(resource=resource, node_resource=node_resource)
        await vm.snapshot("snap1", description="test snap")
        resource.snapshots.create.assert_called_once_with({"snapname": "snap1", "description": "test snap"})
        await vm.rollback("snap1")
        resource.snapshots.rollback.assert_called_once_with("snap1")

    anyio.run(_run)


def test_vm_wait_for_task_failure():
    async def _run():
        resource = _make_vm_resource()
        node_resource = _make_node_resource()
        upid = "UPID:pve1:fail:task"
        resource.status.start = AsyncMock(return_value=_resp(upid))
        node_resource.tasks.get_status = AsyncMock(return_value=_resp({"status": "stopped", "exitstatus": "Error: disk full"}))
        vm = _make_vm(resource=resource, node_resource=node_resource)
        with pytest.raises(RuntimeError, match="failed"):
            await vm.start()

    anyio.run(_run)


# ---------------------------------------------------------------------------
# proxio/models.py — async VmAgent methods
# ---------------------------------------------------------------------------


def test_vm_agent_ping():
    async def _run():
        agent_res = MagicMock()
        agent_res.ping = AsyncMock(return_value=_resp({}))
        agent = VmAgent(resource=agent_res)
        await agent.ping()
        agent_res.ping.assert_called_once()

    anyio.run(_run)


def test_vm_agent_get_hostname():
    async def _run():
        agent_res = MagicMock()
        agent_res.get_hostname = AsyncMock(return_value=_resp({"result": {"host-name": "myhost"}}))
        agent = VmAgent(resource=agent_res)
        hostname = await agent.get_hostname()
        assert hostname == "myhost"

    anyio.run(_run)


def test_vm_agent_get_hostname_vm_not_running():
    async def _run():
        agent_res = MagicMock()
        mock = _resp({}, status_code=500)
        agent_res.get_hostname = AsyncMock(return_value=mock)
        agent = VmAgent(resource=agent_res)
        hostname = await agent.get_hostname()
        assert hostname is None

    anyio.run(_run)


def test_vm_agent_get_osinfo():
    async def _run():
        agent_res = MagicMock()
        osinfo = {"id": "ubuntu", "name": "Ubuntu 22.04"}
        agent_res.get_osinfo = AsyncMock(return_value=_resp({"result": osinfo}))
        agent = VmAgent(resource=agent_res)
        result = await agent.get_osinfo()
        assert result == osinfo

    anyio.run(_run)


def test_vm_agent_get_network_interfaces():
    async def _run():
        agent_res = MagicMock()
        ifaces = [{"name": "eth0", "hardware-address": "aa:bb:cc:dd:ee:ff"}]
        agent_res.get_network_interfaces = AsyncMock(return_value=_resp({"result": ifaces}))
        agent = VmAgent(resource=agent_res)
        result = await agent.get_network_interfaces()
        assert result == ifaces

    anyio.run(_run)


def test_vm_agent_file_read():
    async def _run():
        content = b"hello, world"
        encoded = base64.b64encode(content).decode()
        agent_res = MagicMock()
        agent_res.file_read = AsyncMock(return_value=_resp({"content": encoded}))
        agent = VmAgent(resource=agent_res)
        result = await agent.file_read("/etc/hostname")
        assert result == content
        agent_res.file_read.assert_called_once_with("/etc/hostname")

    anyio.run(_run)


def test_vm_agent_file_write():
    async def _run():
        content = b"new content"
        agent_res = MagicMock()
        agent_res.file_write = AsyncMock(return_value=_resp({}))
        agent = VmAgent(resource=agent_res)
        await agent.file_write("/tmp/test.txt", content)
        expected_encoded = base64.b64encode(content).decode()
        agent_res.file_write.assert_called_once_with("/tmp/test.txt", expected_encoded, encode=False)

    anyio.run(_run)


def test_vm_agent_exec_success():
    async def _run():
        agent_res = MagicMock()
        agent_res.exec = AsyncMock(return_value=_resp({"pid": 42}))
        agent_res.exec_status = AsyncMock(return_value=_resp({"exited": True, "exitcode": 0, "out-data": "ok\n"}))
        agent = VmAgent(resource=agent_res)
        result = await agent.exec("echo", args=["ok"])
        assert result["out-data"] == "ok\n"
        agent_res.exec.assert_called_once()

    anyio.run(_run)


def test_vm_agent_exec_nonzero_raises():
    async def _run():
        agent_res = MagicMock()
        agent_res.exec = AsyncMock(return_value=_resp({"pid": 99}))
        agent_res.exec_status = AsyncMock(return_value=_resp({"exited": True, "exitcode": 1, "err-data": "oops"}))
        agent = VmAgent(resource=agent_res)
        with pytest.raises(RuntimeError, match="exited with code 1"):
            await agent.exec("false")

    anyio.run(_run)


def test_vm_agent_exec_timeout():
    async def _run():
        agent_res = MagicMock()
        agent_res.exec = AsyncMock(return_value=_resp({"pid": 7}))
        # Never finished — exited is always False
        agent_res.exec_status = AsyncMock(return_value=_resp({"exited": False}))
        agent = VmAgent(resource=agent_res)
        with pytest.raises(TimeoutError):
            await agent.exec("sleep", timeout=0.01, poll_interval=0.001)

    anyio.run(_run)


def test_vm_agent_set_user_password():
    async def _run():
        agent_res = MagicMock()
        agent_res.set_user_password = AsyncMock(return_value=_resp({}))
        agent = VmAgent(resource=agent_res)
        await agent.set_user_password("alice", "s3cr3t")
        agent_res.set_user_password.assert_called_once_with("alice", "s3cr3t", crypted=False)

    anyio.run(_run)


# ---------------------------------------------------------------------------
# proxio/models.py — async Node methods
# ---------------------------------------------------------------------------


def test_node_get_status_online():
    async def _run():
        resource = MagicMock()
        resource.get_status = AsyncMock(return_value=_resp({"rootfs": {"avail": 0, "total": 0, "free": 0, "used": 0}, "status": "online", "cpu": 0.1}))
        node = _make_node(resource=resource)
        status = await node.get_status()
        assert status.status == "online"
        assert status.cpu == 0.1

    anyio.run(_run)


def test_node_get_status_offline_on_transport_error():
    async def _run():
        resource = MagicMock()
        resource.get_status = AsyncMock(side_effect=httpx.ConnectError("unreachable"))
        node = _make_node(resource=resource)
        status = await node.get_status()
        assert status.status == "offline"

    anyio.run(_run)


def test_node_get_cpu():
    async def _run():
        resource = MagicMock()
        resource.get_status = AsyncMock(return_value=_resp({"status": "online", "cpu": 0.42}))
        node = _make_node(resource=resource)
        assert await node.get_cpu() == pytest.approx(0.42)

    anyio.run(_run)


def test_node_list_vms_all():
    async def _run():
        resource = MagicMock()
        vm_list = [
            {**_VM_DATA, "vmid": 100, "name": "vm-a", "template": 0},
            {**_VM_DATA, "vmid": 101, "name": "vm-b", "template": 1},
        ]
        resource.qemu.list = AsyncMock(return_value=_resp(vm_list))
        resource.qemu.side_effect = lambda vmid: _make_vm_resource()
        node = _make_node(resource=resource)
        vms = await node.list_vms()
        assert len(vms) == 2

    anyio.run(_run)


def test_node_list_vms_filter_template():
    async def _run():
        resource = MagicMock()
        vm_list = [
            {**_VM_DATA, "vmid": 100, "name": "vm-a", "template": 0},
            {**_VM_DATA, "vmid": 101, "name": "tpl-b", "template": 1},
        ]
        resource.qemu.list = AsyncMock(return_value=_resp(vm_list))
        resource.qemu.side_effect = lambda vmid: _make_vm_resource()
        node = _make_node(resource=resource)
        templates = await node.list_vms(template=True)
        assert len(templates) == 1
        assert templates[0].name == "tpl-b"

    anyio.run(_run)


def test_node_list_vms_filter_name_glob():
    async def _run():
        resource = MagicMock()
        vm_list = [
            {**_VM_DATA, "vmid": 100, "name": "web-01", "template": 0},
            {**_VM_DATA, "vmid": 101, "name": "db-01", "template": 0},
            {**_VM_DATA, "vmid": 102, "name": "web-02", "template": 0},
        ]
        resource.qemu.list = AsyncMock(return_value=_resp(vm_list))
        resource.qemu.side_effect = lambda vmid: _make_vm_resource()
        node = _make_node(resource=resource)
        webs = await node.list_vms(name="web-*")
        assert len(webs) == 2
        assert all(vm.name.startswith("web-") for vm in webs)

    anyio.run(_run)


def test_node_get_vm_by_vmid():
    async def _run():
        resource = MagicMock()
        vm_list = [{**_VM_DATA, "vmid": 100, "name": "test-vm", "template": 0}]
        resource.qemu.list = AsyncMock(return_value=_resp(vm_list))
        resource.qemu.side_effect = lambda vmid: _make_vm_resource()
        node = _make_node(resource=resource)
        vm = await node.get_vm(vmid=100)
        assert vm.vmid == 100

    anyio.run(_run)


def test_node_get_vm_by_name():
    async def _run():
        resource = MagicMock()
        vm_list = [{**_VM_DATA, "vmid": 100, "name": "test-vm", "template": 0}]
        resource.qemu.list = AsyncMock(return_value=_resp(vm_list))
        resource.qemu.side_effect = lambda vmid: _make_vm_resource()
        node = _make_node(resource=resource)
        vm = await node.get_vm(name="test-vm")
        assert vm.name == "test-vm"

    anyio.run(_run)


def test_node_get_vm_no_args_raises():
    async def _run():
        node = _make_node()
        with pytest.raises(ValueError, match="At least one"):
            await node.get_vm()

    anyio.run(_run)


def test_node_get_vm_vmid_not_found_raises():
    async def _run():
        resource = MagicMock()
        resource.qemu.list = AsyncMock(return_value=_resp([]))
        resource.qemu.side_effect = lambda vmid: _make_vm_resource()
        node = _make_node(resource=resource)
        with pytest.raises(LookupError):
            await node.get_vm(vmid=999)

    anyio.run(_run)


def test_node_get_vm_name_not_found_raises():
    async def _run():
        resource = MagicMock()
        resource.qemu.list = AsyncMock(return_value=_resp([]))
        resource.qemu.side_effect = lambda vmid: _make_vm_resource()
        node = _make_node(resource=resource)
        with pytest.raises(LookupError):
            await node.get_vm(name="nonexistent")

    anyio.run(_run)


def test_node_get_vm_multiple_name_matches_raises():
    async def _run():
        resource = MagicMock()
        vm_list = [
            {**_VM_DATA, "vmid": 100, "name": "web-01", "template": 0},
            {**_VM_DATA, "vmid": 101, "name": "web-01", "template": 0},
        ]
        resource.qemu.list = AsyncMock(return_value=_resp(vm_list))
        resource.qemu.side_effect = lambda vmid: _make_vm_resource()
        node = _make_node(resource=resource)
        with pytest.raises(LookupError, match="Multiple"):
            await node.get_vm(name="web-01")

    anyio.run(_run)


def test_node_get_vm_vmid_name_mismatch_raises():
    async def _run():
        resource = MagicMock()
        vm_list = [{**_VM_DATA, "vmid": 100, "name": "actual-name", "template": 0}]
        resource.qemu.list = AsyncMock(return_value=_resp(vm_list))
        resource.qemu.side_effect = lambda vmid: _make_vm_resource()
        node = _make_node(resource=resource)
        with pytest.raises(LookupError, match="does not match"):
            await node.get_vm(vmid=100, name="wrong-name")

    anyio.run(_run)


# ---------------------------------------------------------------------------
# proxio/client.py — ProxmoxClient
# ---------------------------------------------------------------------------


def test_proxmox_client_init():
    client = ProxmoxClient("pve.local", "user@pam!token=secret", verify=False, trust_env=False)
    assert "pve.local" in str(client.base_url)
    assert "PVEAPIToken=user@pam!token=secret" in client.headers["Authorization"]
    assert isinstance(client.nodes, Nodes)


def test_proxmox_client_next_vmid():
    async def _run():
        client = ProxmoxClient("pve.local", "user@pam!tok=x", verify=False, trust_env=False)
        client.get = AsyncMock(return_value=_resp(200))
        vmid = await client.next_vmid()
        assert vmid == 200

    anyio.run(_run)


def test_proxmox_client_get_nodes():
    async def _run():
        client = ProxmoxClient("pve.local", "user@pam!tok=x", verify=False, trust_env=False)
        nodes_data = [
            {**_NODE_DATA, "node": "pve1"},
            {**_NODE_DATA, "node": "pve2"},
        ]
        client.nodes.list = AsyncMock(return_value=_resp(nodes_data))
        collected = [n async for n in client.get_nodes()]
        assert len(collected) == 2
        assert collected[0].node == "pve1"
        assert collected[1].node == "pve2"

    anyio.run(_run)


def test_proxmox_client_get_node_found():
    async def _run():
        client = ProxmoxClient("pve.local", "user@pam!tok=x", verify=False, trust_env=False)
        nodes_data = [{**_NODE_DATA, "node": "pve1"}]
        client.nodes.list = AsyncMock(return_value=_resp(nodes_data))
        node = await client.get_node("pve1")
        assert node.node == "pve1"

    anyio.run(_run)


def test_proxmox_client_get_node_not_found():
    async def _run():
        client = ProxmoxClient("pve.local", "user@pam!tok=x", verify=False, trust_env=False)
        client.nodes.list = AsyncMock(return_value=_resp([]))
        with pytest.raises(LookupError, match="pve99"):
            await client.get_node("pve99")

    anyio.run(_run)
