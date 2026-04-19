# proxio

An async Python wrapper for the Proxmox API, built on [httpx](https://www.python-httpx.org/) and [pydantic](https://docs.pydantic.dev/).

## Installation

```bash
pip install proxio
```

Requires Python 3.8+.

## Authentication

proxio uses Proxmox API tokens. Create one in the Proxmox web UI under **Datacenter → Permissions → API Tokens → Add**.

The token string must be in the format:

```
user@realm!tokenid=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

## Quick Start

```python
import asyncio
from proxio.client import ProxmoxClient

async def main():
    async with ProxmoxClient(
        host="192.168.1.10",
        token="root@pam!mytoken=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
        verify=False,  # set True to verify TLS certificate
    ) as client:
        async for node in client.get_nodes():
            print(node)

asyncio.run(main())
```

## ProxmoxClient

`ProxmoxClient(host, token, verify=True, trust_env=True)`

| Parameter | Description |
|---|---|
| `host` | Hostname or IP of the Proxmox server (without scheme or port) |
| `token` | API token string in `user@realm!tokenid=secret` format |
| `verify` | Verify TLS certificate (default `True`) |
| `trust_env` | Respect proxy environment variables (default `True`) |

### Client methods

| Method | Description |
|---|---|
| `get_nodes()` | Async generator yielding all `Node` objects in the cluster |
| `get_node(name)` | Return a single `Node` by name, raises `LookupError` if not found |
| `next_vmid()` | Return the next free VMID in the cluster |

## Node

Represents a Proxmox node. Returned by `client.get_nodes()` / `client.get_node()`.

### Static fields

| Field | Type | Description |
|---|---|---|
| `name` | `str` | Node name |
| `node_type` | `str` | Node type |
| `maxcpu` | `int` | Number of CPUs |
| `maxmem` | `int` | Maximum memory in bytes |
| `maxdisk` | `int` | Maximum disk in bytes |

### Node methods

| Method | Description |
|---|---|
| `get_status()` | Returns status string (e.g. `"online"`, `"offline"`) |
| `get_cpu()` | Current CPU usage (float) |
| `get_mem()` | Current memory usage in bytes |
| `get_disk()` | Current disk usage in bytes |
| `get_uptime()` | Uptime in seconds |
| `get_runtime()` | Raw runtime dict from the API |
| `list_vms(template=None, name=None)` | List VMs; filter by template flag or name (supports glob patterns) |
| `get_vm(vmid=None, name=None)` | Get a single VM by VMID and/or name (glob supported), raises `LookupError` |

## VirtualMachine

Represents a QEMU virtual machine on a node.

### Static fields

| Field | Type | Description |
|---|---|---|
| `vmid` | `int` | VM ID |
| `name` | `str` | VM name |
| `node` | `str` | Node the VM lives on |
| `cpus` | `int` | Number of CPUs |
| `maxmem` | `int` | Allocated memory in bytes |
| `maxdisk` | `int` | Allocated disk in bytes |
| `tags` | `str` | Comma-separated tags |
| `template` | `bool` | Whether the VM is a template |
| `agent` | `VmAgent` | Guest agent interface |

### Power state methods

| Method | Description |
|---|---|
| `start(timeout=300)` | Start VM and block until running |
| `stop(timeout=300)` | Stop VM and block until stopped |
| `shutdown(timeout=300)` | Graceful shutdown, block until stopped |
| `reset(timeout=300)` | Reset VM |
| `suspend(timeout=300)` | Suspend VM |
| `resume(timeout=300)` | Resume VM |

### Runtime methods

| Method | Description |
|---|---|
| `get_status()` | Returns status string (e.g. `"running"`, `"stopped"`) |
| `get_cpu()` | Current CPU usage (float) |
| `get_mem()` | Current memory usage in bytes |
| `get_uptime()` | Uptime in seconds |
| `get_runtime()` | Raw runtime dict from the API |
| `get_config()` | Raw config response from the API |

### Lifecycle methods

| Method | Description |
|---|---|
| `clone(name, *, newid, description, snapname, target, pool, full, storage, bwlimit, timeout)` | Clone VM, returns new `VirtualMachine` |
| `migrate(data, timeout=600)` | Migrate VM to another node |
| `delete(timeout=300)` | Delete VM |
| `snapshot(snapname, description, timeout)` | Create a snapshot |
| `rollback(snapname, timeout)` | Rollback to a snapshot |
| `list_snapshots()` | List snapshots (raw response) |

## VmAgent

Accessed via `vm.agent`. Provides access to the QEMU guest agent.

| Method | Description |
|---|---|
| `ping()` | Verify the guest agent is responsive |
| `exec(command, args, input_data, timeout, poll_interval)` | Execute a command in the guest, returns dict with `exitcode`, `out-data`, `err-data` |
| `get_osinfo()` | OS information from the guest |
| `get_hostname()` | Hostname from the guest, or `None` if not running |
| `get_network_interfaces()` | Network interface list from the guest |
| `get_fsinfo()` | Filesystem information from the guest |
| `get_users()` | Logged-in users from the guest |
| `set_user_password(username, password, crypted)` | Set a guest user password |
| `file_read(path)` | Read a file from the guest, returns `bytes` |
| `file_write(path, content)` | Write `bytes` to a file in the guest |

## Examples

### List all nodes

```python
import asyncio
from proxio.client import ProxmoxClient

async def main():
    async with ProxmoxClient(host="192.168.1.10", token="root@pam!mytoken=...", verify=False) as client:
        async for node in client.get_nodes():
            print(node.name, await node.get_status())

asyncio.run(main())
```

### List VMs on a node

```python
node = await client.get_node("pve")
vms = await node.list_vms()
for vm in vms:
    print(vm.vmid, vm.name, await vm.get_status())
```

### Filter VMs by name (glob)

```python
vms = await node.list_vms(name="web-*")
```

### Clone a VM from a template

```python
template = await node.get_vm(name="ubuntu-template")
new_vm = await template.clone("my-new-vm", full=True, storage="local-lvm")
await new_vm.start()
```

### Run a command in a guest

```python
result = await vm.agent.exec("hostname")
print(result["out-data"])
```

### Using a `.env` file (examples)

Copy `examples/.env.example` to `examples/.env` and fill in your credentials:

```
PROX_API_TOKEN=root@pam!mytokenid=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
PROX_HOST=192.168.1.10
```

Then run:

```bash
uv run examples/list_nodes.py
```

## Development

### Run tests

```bash
pytest --cov=proxio --cov-report=term
```

### Build

```bash
hatch build
```

### Publish

```bash
hatch publish
```

## GitHub Flow & Publishing to PyPI

### How it works

Publishing is fully automated via GitHub Actions using [PyPI Trusted Publishing (OIDC)](https://docs.pypi.org/trusted-publishers/) — no API tokens or passwords are needed.

The workflow (`.github/workflows/publish.yml`) triggers automatically when a **GitHub Release is published**:

1. **Tests run** — the full test suite must pass on Ubuntu before anything is published.
2. **Build** — `hatch build` produces an sdist and a wheel.
3. **Publish** — the package is uploaded to PyPI using a short-lived OIDC token issued by GitHub. This requires the `release` environment to be configured on PyPI.

### One-time PyPI setup (Trusted Publishing)

1. Go to [pypi.org](https://pypi.org) → your project → **Manage → Publishing**.
2. Add a new Trusted Publisher with these values:
   - **Owner**: `rogerbrinkmann`
   - **Repository**: `proxio`
   - **Workflow filename**: `publish.yml`
   - **Environment**: `release`
3. Create a `release` environment in your GitHub repo under **Settings → Environments**.

### Releasing a new version

1. Bump the version in `proxio/__init__.py`:
   ```python
   __version__ = "0.1.0"
   ```
2. Commit and push to `main`.
3. On GitHub, go to **Releases → Draft a new release**.
4. Create a new tag matching the version (e.g. `v0.1.0`), fill in the release notes, and click **Publish release**.
5. The workflow starts automatically — tests run, then the package is built and uploaded to PyPI.

