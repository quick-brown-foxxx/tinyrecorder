# Task 11: IPC (Unix Domain Socket)

**Phase:** 5 (parallel with: Task 9a, Task 9b, Task 9c)
**Dependencies:** Task 3, Task 2b (needs `IpcTransport`/`IpcTransportServer` protocols from platform layer)
**Skills:** `writing-python-code`, `testing-python`
**Files to create:** `src/ipc.py`
**Test files:** `tests/integration/test_ipc.py`
**Estimated complexity:** medium

---

**Goal:** Implement the IPC protocol layer in `src/ipc.py` (platform-agnostic: JSON serialization, command types, command dispatch) and the Unix socket transport in `platform/linux.py` (platform-specific: `UnixSocketIpcTransport`/`UnixSocketIpcTransportServer`).

> **Note (two-layer IPC architecture):** IPC is split into two layers:
> 1. **Transport layer** (platform-specific): how bytes move between processes. Defined by `IpcTransport`/`IpcTransportServer` protocols in `platform/protocols.py`. The Unix socket implementation (`UnixSocketIpcTransport`/`UnixSocketIpcTransportServer`) lives in `platform/linux.py` and carries `for_platform = "Linux"`.
> 2. **Protocol layer** (platform-agnostic): what messages look like. Lives in `ipc.py`. Handles JSON serialization, command types, response types, and command dispatch. Uses the transport layer for sending/receiving bytes.
>
> The `IPCServer` and `IPCClient` classes in `ipc.py` compose with transport instances obtained via platform factory functions. All current functionality is preserved, just restructured to separate platform-specific transport from platform-agnostic protocol logic.

#### Steps

- [ ] Create `tests/integration/test_ipc.py`:

```python
"""Integration tests for IPC server and client."""

from __future__ import annotations

import asyncio
import json
import socket
from pathlib import Path

import pytest

from tinyrecorder.ipc import IPCClient, IPCServer


@pytest.fixture()
def socket_path(tmp_path: Path) -> Path:
    """Provide a temporary socket path."""
    return tmp_path / "test_tinyrecorder.sock"


async def _echo_handler(command: str) -> dict[str, str]:
    """Simple echo handler for testing: returns the command back in a response."""
    return {"status": "ok", "command": command, "state": "idle"}


@pytest.mark.asyncio()
async def test_ipc_round_trip(socket_path: Path) -> None:
    """IPC server and client can exchange a command and response."""
    server = IPCServer()
    await server.start(socket_path, _echo_handler)

    try:
        client = IPCClient()

        # Test status command
        result = client.send_command(socket_path, "status")
        assert result.is_ok
        response = result.unwrap()
        assert response["status"] == "ok"
        assert response["command"] == "status"
        assert response["state"] == "idle"

        # Test record-toggle command
        result = client.send_command(socket_path, "record-toggle")
        assert result.is_ok
        response = result.unwrap()
        assert response["command"] == "record-toggle"

    finally:
        await server.stop()

    # Socket file should be cleaned up
    assert not socket_path.exists()


@pytest.mark.asyncio()
async def test_ipc_stale_socket_cleanup(socket_path: Path) -> None:
    """A stale socket file is cleaned up when a new server starts."""
    # Create a stale socket file (just a regular file pretending to be a socket)
    socket_path.touch()
    assert socket_path.exists()

    server = IPCServer()
    await server.start(socket_path, _echo_handler)

    try:
        # Verify the new server is operational
        client = IPCClient()
        result = client.send_command(socket_path, "status")
        assert result.is_ok
        response = result.unwrap()
        assert response["status"] == "ok"
    finally:
        await server.stop()


@pytest.mark.asyncio()
async def test_ipc_client_no_server(socket_path: Path) -> None:
    """Client returns Err when no server is listening."""
    client = IPCClient()
    result = client.send_command(socket_path, "status")
    assert result.is_err


@pytest.mark.asyncio()
async def test_ipc_is_running_true(socket_path: Path) -> None:
    """is_running returns True when server is listening."""
    server = IPCServer()
    await server.start(socket_path, _echo_handler)

    try:
        client = IPCClient()
        assert client.is_running(socket_path) is True
    finally:
        await server.stop()


@pytest.mark.asyncio()
async def test_ipc_is_running_false_no_socket(socket_path: Path) -> None:
    """is_running returns False when no socket file exists."""
    client = IPCClient()
    assert client.is_running(socket_path) is False


@pytest.mark.asyncio()
async def test_ipc_is_running_false_stale_socket(socket_path: Path) -> None:
    """is_running returns False when socket file exists but no server listening."""
    socket_path.touch()
    client = IPCClient()
    assert client.is_running(socket_path) is False
```

```python


@pytest.mark.asyncio()
async def test_ipc_malformed_json(socket_path: Path) -> None:
    """Server handles malformed JSON without crashing and responds with error."""
    server = IPCServer()
    await server.start(socket_path, _echo_handler)

    try:
        # Send raw malformed JSON directly via socket
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(str(socket_path))
        sock.sendall(b"not json\n")
        sock.settimeout(2.0)
        response_data = sock.recv(4096)
        sock.close()

        response = json.loads(response_data.decode().strip())
        assert response.get("status") == "error"

        # Verify server is still operational after malformed input
        client = IPCClient()
        result = client.send_command(socket_path, "status")
        assert result.is_ok
    finally:
        await server.stop()
```

- [ ] Run tests and confirm they fail:

```bash
uv run pytest tests/integration/test_ipc.py -x -v 2>&1 | head -50
```

- [ ] Create `src/ipc.py` -- same content as in the original plan (IPCServer + IPCClient classes).

- [ ] Run tests and confirm they pass:

```bash
uv run pytest tests/integration/test_ipc.py -x -v 2>&1 | head -50
```

- [ ] Commit: `feat(ipc): add Unix domain socket server and client with newline-delimited JSON`
