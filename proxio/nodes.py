from typing import Any

import httpx


class VmStatus:
    """Proxmox QEMU VM Status Endpoints — scoped to /nodes/{node}/qemu/{vmid}/status."""

    def __init__(self, client: httpx.AsyncClient, base_url: httpx.URL):
        self._client = client
        self._base_url = base_url

    async def current(self) -> httpx.Response:
        """GET /nodes/{node}/qemu/{vmid}/status/current.

        Returns the current VM status including: status (running/stopped), cpus, maxmem,
        maxdisk, cpu (utilisation 0-1), mem, disk, uptime, pid, qmpstatus, ha, and more.
        """
        return await self._client.get(f"{self._base_url}/current")

    async def start(self) -> httpx.Response:
        """POST /nodes/{node}/qemu/{vmid}/status/start.

        Start the virtual machine. Returns a task UPID.
        Optional body params: skiplock (bool), timeout (int, seconds).
        """
        return await self._client.post(f"{self._base_url}/start")

    async def stop(self) -> httpx.Response:
        """POST /nodes/{node}/qemu/{vmid}/status/stop.

        Stop the virtual machine immediately (hard stop, equivalent to pulling the power).
        Returns a task UPID.
        Optional body params: skiplock (bool), timeout (int, seconds), keepActive (bool).
        """
        return await self._client.post(f"{self._base_url}/stop")

    async def shutdown(self) -> httpx.Response:
        """POST /nodes/{node}/qemu/{vmid}/status/shutdown.

        Gracefully shut down the VM via ACPI. Returns a task UPID.
        The guest OS is expected to handle the ACPI shutdown signal.
        Optional body params: skiplock (bool), timeout (int, seconds), forceStop (bool),
        keepActive (bool).
        """
        return await self._client.post(f"{self._base_url}/shutdown")

    async def reset(self) -> httpx.Response:
        """POST /nodes/{node}/qemu/{vmid}/status/reset.

        Hard-reset the virtual machine (equivalent to pressing the reset button).
        Returns a task UPID.
        Optional body params: skiplock (bool).
        """
        return await self._client.post(f"{self._base_url}/reset")

    async def suspend(self) -> httpx.Response:
        """POST /nodes/{node}/qemu/{vmid}/status/suspend.

        Suspend the virtual machine to RAM (pause). Returns a task UPID.
        Optional body params: skiplock (bool), statestorage (str), todisk (bool).
        When todisk=1 the VM is hibernated to disk (suspend-to-disk).
        """
        return await self._client.post(f"{self._base_url}/suspend")

    async def resume(self) -> httpx.Response:
        """POST /nodes/{node}/qemu/{vmid}/status/resume.

        Resume a suspended virtual machine. Returns a task UPID.
        Optional body params: skiplock (bool), nocheck (bool).
        """
        return await self._client.post(f"{self._base_url}/resume")


class VmSnapshots:
    """Proxmox QEMU VM Snapshots Endpoints — scoped to /nodes/{node}/qemu/{vmid}/snapshots."""

    def __init__(self, client: httpx.AsyncClient, base_url: httpx.URL):
        self._client = client
        self._base_url = base_url

    async def list(self) -> httpx.Response:
        """GET /nodes/{node}/qemu/{vmid}/snapshots.

        List all snapshots for the VM. Each entry contains: name, description, snaptime,
        vmstate (bool, whether RAM state was saved), parent (name of parent snapshot).
        The special snapshot "current" represents the live state.
        """
        return await self._client.get(self._base_url)

    async def create(self, data: dict[str, Any]) -> httpx.Response:
        """POST /nodes/{node}/qemu/{vmid}/snapshots.

        Create a new VM snapshot. Returns a task UPID.
        Required body params:
          snapname (str): Name for the snapshot (alphanumeric, max 40 chars).
        Optional body params:
          description (str): Snapshot description.
          vmstate (bool): Whether to save RAM state (live snapshot). Slower but allows
                          resuming from exact memory state.
        """
        return await self._client.post(self._base_url, json=data)

    async def delete(self, snapname: str) -> httpx.Response:
        """DELETE /nodes/{node}/qemu/{vmid}/snapshots/{snapname}.

        Delete a snapshot. Returns a task UPID.
        Optional query params: force (bool) — delete even if it has children (removes
        child snapshots too).
        """
        return await self._client.delete(f"{self._base_url}/{snapname}")

    async def rollback(self, snapname: str) -> httpx.Response:
        """POST /nodes/{node}/qemu/{vmid}/snapshots/{snapname}/rollback.

        Rollback the VM to the named snapshot. Returns a task UPID.
        The VM must be stopped or the operation will fail unless the snapshot includes
        RAM state.
        Optional body params: start (bool) — start the VM after rollback.
        """
        return await self._client.post(f"{self._base_url}/{snapname}/rollback")


class VmAgent:
    """Proxmox QEMU Guest Agent Endpoints — scoped to /nodes/{node}/qemu/{vmid}/agent.

    All endpoints require the QEMU guest agent (qemu-guest-agent) to be installed and
    running inside the VM. The VM must be powered on. Requests will return HTTP 500 with
    "VM is not running" if the VM is stopped.
    """

    def __init__(self, client: httpx.AsyncClient, base_url: httpx.URL):
        self._client = client
        self._base_url = base_url

    # --- Exec ---

    async def exec(self, data: dict[str, Any]) -> httpx.Response:
        """POST /nodes/{node}/qemu/{vmid}/agent/exec.

        Execute a command inside the guest via the QEMU agent. Returns {"pid": N}.
        The command runs asynchronously inside the guest; poll exec-status with the
        returned PID to retrieve exit code and output.
        Required body params:
          command (str): The executable path.
        Optional body params:
          args (list[str]): Command-line arguments.
          input-data (str): Data to pass to stdin of the command (plain text).
        """
        return await self._client.post(f"{self._base_url}/exec", json=data)

    async def exec_status(self, pid: int) -> httpx.Response:
        """GET /nodes/{node}/qemu/{vmid}/agent/exec-status.

        Poll the exit status of a command started with agent/exec.
        Returns: pid (int), exited (bool), exitcode (int), out-data (str, stdout),
        err-data (str, stderr), out-truncated (bool), err-truncated (bool).
        Must be polled until exited=true; output is buffered until the command exits.
        """
        return await self._client.get(f"{self._base_url}/exec-status", params={"pid": pid})

    # --- File I/O ---

    async def file_read(self, file: str) -> httpx.Response:
        """GET /nodes/{node}/qemu/{vmid}/agent/file-read.

        Read a file from the guest filesystem via the QEMU agent.
        Returns: content (str, base64-encoded), truncated (bool).
        Files larger than ~1 MiB may be truncated; check the truncated flag.
        Required query params:
          file (str): Absolute path to the file inside the guest.
        """
        return await self._client.get(f"{self._base_url}/file-read", params={"file": file})

    async def file_write(self, file: str, content: str, encode: bool = True) -> httpx.Response:
        """POST /nodes/{node}/qemu/{vmid}/agent/file-write.

        Write content to a file inside the guest via the QEMU agent.
        The file is created or overwritten (no append).
        Required body params:
          file (str): Absolute path to the file inside the guest.
          content (str): File content, base64-encoded by default.
        Optional body params:
          encode (int, 0|1): When 1 (default), content is treated as base64-encoded.
                             Pass 0 if content is already raw bytes (not recommended over JSON).
        """
        return await self._client.post(f"{self._base_url}/file-write", json={"file": file, "content": content, "encode": int(encode)})

    # --- Info queries ---

    async def get_osinfo(self) -> httpx.Response:
        """GET /nodes/{node}/qemu/{vmid}/agent/get-osinfo.

        Returns OS information reported by the guest agent, including:
        id (str, e.g. "windows" or "ubuntu"), name, pretty-name, version, version-id,
        machine (architecture), kernel-release, kernel-version.
        """
        return await self._client.get(f"{self._base_url}/get-osinfo")

    async def get_hostname(self) -> httpx.Response:
        """GET /nodes/{node}/qemu/{vmid}/agent/get-host-name.

        Returns the hostname of the guest OS as reported by the QEMU agent.
        Response data: { "result": { "host-name": "..." } }
        """
        return await self._client.get(f"{self._base_url}/get-host-name")

    async def get_network_interfaces(self) -> httpx.Response:
        """GET /nodes/{node}/qemu/{vmid}/agent/network-get-interfaces.

        Returns a list of network interfaces as seen from inside the guest.
        Each entry: name (str), hardware-address (MAC), ip-addresses (list of
        { ip-address, ip-address-type (ipv4/ipv6), prefix }).
        Useful for resolving the guest IP address without relying on DHCP leases.
        """
        return await self._client.get(f"{self._base_url}/network-get-interfaces")

    async def get_fsinfo(self) -> httpx.Response:
        """GET /nodes/{node}/qemu/{vmid}/agent/get-fsinfo.

        Returns filesystem information from the guest, including mount points,
        disk names, type, total-bytes, used-bytes, and disk-bus info.
        """
        return await self._client.get(f"{self._base_url}/get-fsinfo")

    async def get_users(self) -> httpx.Response:
        """GET /nodes/{node}/qemu/{vmid}/agent/get-users.

        Returns a list of users currently logged into the guest OS.
        Each entry: user (str), domain (str, Windows only), login-time (float, epoch).
        """
        return await self._client.get(f"{self._base_url}/get-users")

    async def get_vcpus(self) -> httpx.Response:
        """GET /nodes/{node}/qemu/{vmid}/agent/get-vcpus.

        Returns the list of vCPUs as seen by the guest, including their online state
        and logical ID. Useful for verifying hot-plug vCPU changes.
        """
        return await self._client.get(f"{self._base_url}/get-vcpus")

    async def get_time(self) -> httpx.Response:
        """GET /nodes/{node}/qemu/{vmid}/agent/get-time.

        Returns the current time inside the guest as a Unix timestamp (seconds and
        nanoseconds). Useful for detecting guest clock drift.
        """
        return await self._client.get(f"{self._base_url}/get-time")

    async def get_timezone(self) -> httpx.Response:
        """GET /nodes/{node}/qemu/{vmid}/agent/get-timezone.

        Returns the timezone configured inside the guest OS.
        Response data: { "result": { "zone": "Europe/Berlin", "offset": 3600 } }
        """
        return await self._client.get(f"{self._base_url}/get-timezone")

    # --- Filesystem freeze ---

    async def fsfreeze_status(self) -> httpx.Response:
        """GET /nodes/{node}/qemu/{vmid}/agent/fsfreeze-status.

        Returns the current filesystem freeze state of the guest.
        Response data: { "result": "thawed" | "frozen" }
        """
        return await self._client.get(f"{self._base_url}/fsfreeze-status")

    async def fsfreeze_freeze(self) -> httpx.Response:
        """POST /nodes/{node}/qemu/{vmid}/agent/fsfreeze-freeze.

        Freeze all freezable guest filesystems. Used before taking a consistent
        snapshot to ensure data integrity. Must be followed by fsfreeze-thaw.
        Returns the number of filesystems frozen.
        """
        return await self._client.post(f"{self._base_url}/fsfreeze-freeze")

    async def fsfreeze_thaw(self) -> httpx.Response:
        """POST /nodes/{node}/qemu/{vmid}/agent/fsfreeze-thaw.

        Thaw all frozen guest filesystems. Must be called after fsfreeze-freeze to
        resume normal I/O. Returns the number of filesystems thawed.
        """
        return await self._client.post(f"{self._base_url}/fsfreeze-thaw")

    # --- Power / session ---

    async def ping(self) -> httpx.Response:
        """POST /nodes/{node}/qemu/{vmid}/agent/ping.

        Send a ping to the QEMU guest agent to verify it is alive and responsive.
        Returns an empty result on success; HTTP 500 if the agent is not running.
        """
        return await self._client.post(f"{self._base_url}/ping")

    async def shutdown(self) -> httpx.Response:
        """POST /nodes/{node}/qemu/{vmid}/agent/shutdown.

        Request a graceful shutdown of the guest OS via the QEMU agent.
        Unlike the ACPI-based status/shutdown, this calls the guest agent directly,
        which may be more reliable on VMs without ACPI support.
        """
        return await self._client.post(f"{self._base_url}/shutdown")

    async def suspend_disk(self) -> httpx.Response:
        """POST /nodes/{node}/qemu/{vmid}/agent/suspend-disk.

        Request the guest OS to hibernate (suspend-to-disk / S4 sleep state) via the
        QEMU agent. The guest saves its state to disk and powers off.
        """
        return await self._client.post(f"{self._base_url}/suspend-disk")

    async def suspend_ram(self) -> httpx.Response:
        """POST /nodes/{node}/qemu/{vmid}/agent/suspend-ram.

        Request the guest OS to suspend to RAM (S3 sleep state) via the QEMU agent.
        The guest state is held in memory; the VM remains running at the hypervisor level.
        """
        return await self._client.post(f"{self._base_url}/suspend-ram")

    async def suspend_hybrid(self) -> httpx.Response:
        """POST /nodes/{node}/qemu/{vmid}/agent/suspend-hybrid.

        Request a hybrid suspend (suspend-to-both / S3+S4) via the QEMU agent.
        The guest saves state to disk AND suspends to RAM; if power is lost the disk
        image is used to resume.
        """
        return await self._client.post(f"{self._base_url}/suspend-hybrid")

    async def set_user_password(self, username: str, password: str, crypted: bool = False) -> httpx.Response:
        """POST /nodes/{node}/qemu/{vmid}/agent/set-user-password.

        Set or change the password of a user account inside the guest OS.
        Required body params:
          username (str): The guest OS username.
          password (str): The new password (plaintext, or pre-crypted hash).
        Optional body params:
          crypted (int, 0|1): When 1, treat password as a pre-hashed crypt(3) string.
        """
        return await self._client.post(
            f"{self._base_url}/set-user-password",
            json={"username": username, "password": password, "crypted": int(crypted)},
        )


class VmResource:
    """Proxmox resource scoped to /nodes/{node}/qemu/{vmid}."""

    def __init__(self, client: httpx.AsyncClient, base_url: httpx.URL):
        self._client = client
        self._base_url = base_url
        self.status = VmStatus(client, httpx.URL(f"{base_url}/status"))
        self.snapshots = VmSnapshots(client, httpx.URL(f"{base_url}/snapshots"))
        self.agent = VmAgent(client, httpx.URL(f"{base_url}/agent"))

    async def get_config(self) -> httpx.Response:
        """GET /nodes/{node}/qemu/{vmid}/config.

        Get the current VM configuration. Returns all config options including cpu,
        memory, disk definitions (scsi0, ide0, …), net interfaces, boot order, tags,
        description, name, and more. Use the pending=1 query param to include
        pending changes not yet applied.
        """
        return await self._client.get(f"{self._base_url}/config")

    async def update_config(self, data: dict[str, Any]) -> httpx.Response:
        """PUT /nodes/{node}/qemu/{vmid}/config.

        Update the VM configuration. Changes are applied immediately (or at next boot
        for options that require a restart). Pass delete (str, comma-separated list)
        to remove config keys. Pass digest (str) to guard against concurrent edits.
        """
        return await self._client.put(f"{self._base_url}/config", json=data)

    async def clone(self, data: dict[str, Any]) -> httpx.Response:
        """POST /nodes/{node}/qemu/{vmid}/clone.

        Clone the VM (full or linked clone). Returns a task UPID.
        Required body params:
          newid (int): VMID for the new clone. Must be unused in the cluster.
        Optional body params:
          name (str): Name for the clone.
          description (str): Clone description.
          snapname (str): Snapshot to clone from (required for linked clones).
          target (str): Target node name (defaults to the source node).
          pool (str): Resource pool to add the clone to.
          full (int, 0|1): 1 = full clone (independent disk copy, default for templates);
                           0 = linked clone (shares base image, requires snapname).
          storage (str): Target storage for disk images (required when cloning to a
                         different storage or for full clones across storage).
          format (str): Disk image format override (raw, qcow2, vmdk).
          bwlimit (int): I/O bandwidth limit in KiB/s for the clone operation.
        """
        return await self._client.post(f"{self._base_url}/clone", json=data)

    async def migrate(self, data: dict[str, Any]) -> httpx.Response:
        """POST /nodes/{node}/qemu/{vmid}/migrate.

        Migrate the VM to another node. Returns a task UPID.
        Required body params:
          target (str): Target node name.
        Optional body params:
          online (int, 0|1): 1 = live migration (VM stays running); 0 = offline migration.
          force (int, 0|1): Allow migration even if local resources (e.g. CD-ROM) are used.
          with-local-disks (int, 0|1): Migrate local disks along with the VM.
          targetstorage (str): Target storage for migrated disks.
          bwlimit (int): I/O bandwidth limit in KiB/s.
        """
        return await self._client.post(f"{self._base_url}/migrate", json=data)

    async def delete(self) -> httpx.Response:
        """DELETE /nodes/{node}/qemu/{vmid}.

        Destroy the VM and all its disk images. Returns a task UPID.
        The VM must be stopped before deletion.
        Optional query params:
          purge (int, 0|1): Remove the VM from all related configurations (backups,
                            replication, firewall, HA).
          destroy-unreferenced-disks (int, 0|1): Also delete disks not referenced in
                                                 the current config (e.g. detached disks).
        """
        return await self._client.delete(self._base_url)


class QemuEndpoint:
    """Proxmox QEMU Endpoints — scoped to /nodes/{node}/qemu."""

    def __init__(self, client: httpx.AsyncClient, base_url: httpx.URL):
        self._client = client
        self._base_url = base_url

    def __call__(self, vmid: int | str) -> VmResource:
        """Return a VmResource scoped to /nodes/{node}/qemu/{vmid}."""
        return VmResource(self._client, httpx.URL(f"{self._base_url}/{vmid}"))

    async def list(self, params: httpx.QueryParams | None = None) -> httpx.Response:
        """GET /nodes/{node}/qemu.

        List all VMs on the node. Each entry contains: vmid, name, status, cpus,
        maxmem, maxdisk, mem, disk, uptime, pid, template, tags, and more.
        Optional query params:
          full (int, 0|1): Include extended information (network, snapshot count).
        """
        return await self._client.get(self._base_url, params=params)

    async def create(self, data: dict[str, Any]) -> httpx.Response:
        """POST /nodes/{node}/qemu.

        Create a new virtual machine. Returns a task UPID.
        Required body params:
          vmid (int): VMID for the new VM. Must be unused in the cluster.
        Notable optional body params: name, memory, cores, sockets, cpu (cpu type),
        scsi0 / ide0 / … (disk definitions), net0 / … (network), ostype, boot, bios,
        machine, start (int, 0|1 — start after creation).
        """
        return await self._client.post(self._base_url, json=data)


class TasksEndpoint:
    """Proxmox Tasks Endpoints — scoped to /nodes/{node}/tasks."""

    def __init__(self, client: httpx.AsyncClient, base_url: httpx.URL):
        self._client = client
        self._base_url = base_url

    async def list(self, params: httpx.QueryParams | None = None) -> httpx.Response:
        """GET /nodes/{node}/tasks.

        List recent tasks on the node. Each entry contains: upid, type, id, user,
        starttime, endtime, status (running / stopped), exitstatus (OK / error).
        Optional query params: limit (int), start (int), errors (int, 0|1 — only failed),
        userfilter (str), typefilter (str), vmid (int), source (str).
        """
        return await self._client.get(self._base_url, params=params)

    async def get_status(self, upid: str) -> httpx.Response:
        """GET /nodes/{node}/tasks/{upid}/status.

        Get the current status of a task identified by its UPID (Unique Process ID).
        Returns: upid, type, id, user, starttime, status ("running" | "stopped"),
        exitstatus ("OK" | error message — only present when stopped).
        Poll this until status == "stopped", then check exitstatus == "OK".
        """
        return await self._client.get(f"{self._base_url}/{upid}/status")

    async def get_log(self, upid: str, params: httpx.QueryParams | None = None) -> httpx.Response:
        """GET /nodes/{node}/tasks/{upid}/log.

        Retrieve the log output of a task. Returns a list of { n (line number), t (text) }.
        Optional query params:
          start (int): Starting line number (for pagination).
          limit (int): Maximum number of lines to return.
          download (int, 0|1): Return the whole log as a downloadable file.
        """
        return await self._client.get(f"{self._base_url}/{upid}/log", params=params)

    async def stop(self, upid: str) -> httpx.Response:
        """DELETE /nodes/{node}/tasks/{upid}.

        Stop a running task. The task worker is sent SIGTERM.
        Only tasks owned by the authenticated user (or root) can be stopped.
        """
        return await self._client.delete(f"{self._base_url}/{upid}")


class NodeResource:
    """Proxmox resource scoped to /nodes/{node}."""

    def __init__(self, client: httpx.AsyncClient, base_url: httpx.URL):
        self._client = client
        self._base_url = base_url
        self.qemu = QemuEndpoint(client, httpx.URL(f"{base_url}/qemu"))
        self.tasks = TasksEndpoint(client, httpx.URL(f"{base_url}/tasks"))

    async def get_status(self) -> httpx.Response:
        """GET /nodes/{node}/status.

        Get the current runtime status of the node. Returns: status (online/offline),
        cpu (utilisation 0-1), maxcpu, mem, maxmem, disk, maxdisk, uptime (seconds),
        loadavg (list), kversion (kernel version string), pveversion, ksm, swap,
        netout, netin, rootfs.
        """
        return await self._client.get(f"{self._base_url}/status")

    async def get_network(self) -> httpx.Response:
        """GET /nodes/{node}/network.

        List all network interface configurations on the node. Each entry contains:
        iface (name), type (bridge/bond/eth/vlan/…), active (bool), autostart (bool),
        address, netmask, gateway, bridge_ports, slaves, and more.
        Optional query params: type (str) — filter by interface type.
        """
        return await self._client.get(f"{self._base_url}/network")

    async def get_storage(self) -> httpx.Response:
        """GET /nodes/{node}/storage.

        List all storage configurations accessible from this node. Each entry contains:
        storage (id), type (dir/nfs/zfs/rbd/…), content (allowed content types),
        active (bool), enabled (bool), total, avail, used, used_fraction.
        Optional query params: content (str), enabled (int, 0|1), format (int, 0|1),
        storage (str — filter by storage id), target (str — target node name).
        """
        return await self._client.get(f"{self._base_url}/storage")

    def sibling(self, node: str) -> "NodeResource":
        """Return a NodeResource for another node on the same cluster.

        Derives the /nodes base URL by stripping the current node name, then appends
        the target node name. Useful for cross-node operations such as VM migration
        or cloning.
        """
        base = str(self._base_url).rsplit("/", 1)[0]
        return NodeResource(self._client, httpx.URL(f"{base}/{node}"))

    async def next_vmid(self) -> int:
        """GET /cluster/nextid.

        Return the next free VMID available in the entire cluster.
        Proxmox guarantees the returned ID is not currently in use on any node.
        The API root is derived by stripping two path segments (/nodes/{node}) from
        the current base URL.
        """
        api_root = str(self._base_url).rsplit("/", 2)[0]
        response = await self._client.get(f"{api_root}/cluster/nextid")
        response.raise_for_status()
        return int(response.json()["data"])


class Nodes:
    """Proxmox Nodes Endpoints — /nodes."""

    def __init__(self, client: httpx.AsyncClient, base_url: httpx.URL):
        self._client = client
        self._base_url = base_url

    def __call__(self, node: str) -> NodeResource:
        """Return a NodeResource scoped to /nodes/{node}."""
        return NodeResource(self._client, httpx.URL(f"{self._base_url}/{node}"))

    async def list(self) -> httpx.Response:
        """GET /nodes.

        List all nodes in the cluster. Each entry contains: node (name), status
        (online/offline/unknown), type (node), cpu (utilisation 0-1), maxcpu, mem,
        maxmem, disk, maxdisk, uptime, level (subscription level), id, ssl_fingerprint.
        """
        return await self._client.get(self._base_url)

    async def start(self) -> httpx.Response:
        return await self._client.post(f"{self._base_url}/start")

    async def stop(self) -> httpx.Response:
        return await self._client.post(f"{self._base_url}/stop")

    async def shutdown(self) -> httpx.Response:
        return await self._client.post(f"{self._base_url}/shutdown")

    async def reset(self) -> httpx.Response:
        return await self._client.post(f"{self._base_url}/reset")

    async def suspend(self) -> httpx.Response:
        return await self._client.post(f"{self._base_url}/suspend")

    async def resume(self) -> httpx.Response:
        return await self._client.post(f"{self._base_url}/resume")
