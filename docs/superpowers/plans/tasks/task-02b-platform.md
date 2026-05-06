# Task 2b: Platform Abstraction Layer

**Phase:** 2 (before Task 2, parallel with Task 3)
**Dependencies:** Task 1
**Skills:** `writing-python-code`, `building-multi-ui-apps`
**Files to create:** `src/tinyrecorder/platform/__init__.py`, `src/tinyrecorder/platform/protocols.py`, `src/tinyrecorder/platform/linux.py`
**Test files:** `tests/unit/test_platform.py`
**Estimated complexity:** medium

---

**Goal:** Create the platform abstraction layer with protocols and Linux implementations. This enables the app to run on Linux now while keeping the door open for Windows/macOS support via additional implementation files.

> **Note:** Task 2 (Config) depends on this task because it needs `UserDirectories` to resolve config file paths. Task 7 (Audio Processor) depends on `FfmpegProvider`. Task 11 (IPC) depends on `IpcTransport`/`IpcTransportServer`. Task 12 (Startup) depends on `PlatformEnv` and `InstanceLock`. Complete this task early in Phase 2.

#### Steps

- [ ] **2b.1** Create `tests/unit/test_platform.py` with all tests (failing):

```python
# tests/unit/test_platform.py
"""Tests for platform abstraction layer: protocols, Linux implementations, factory functions."""

import os
import sys
from pathlib import Path

import pytest

from tinyrecorder.platform import (
    get_ffmpeg_provider,
    get_instance_lock,
    get_ipc_client,
    get_ipc_server,
    get_platform_env,
    get_user_directories,
)
from tinyrecorder.platform.linux import (
    LinuxFfmpegProvider,
    LinuxPlatformEnv,
    LinuxUserDirectories,
    SocketInstanceLock,
    UnixSocketIpcTransport,
    UnixSocketIpcTransportServer,
)
from tinyrecorder.platform.protocols import (
    FfmpegProvider,
    InstanceLock,
    IpcTransport,
    IpcTransportServer,
    PlatformEnv,
    UserDirectories,
)


class TestUserDirectories:
    """Tests for LinuxUserDirectories."""

    def test_config_dir_uses_xdg(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """config_dir uses XDG_CONFIG_HOME when set."""
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
        dirs = LinuxUserDirectories()
        assert dirs.config_dir == tmp_path / "config" / "tinyrecorder"

    def test_cache_dir_uses_xdg(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """cache_dir uses XDG_CACHE_HOME when set."""
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
        dirs = LinuxUserDirectories()
        assert dirs.cache_dir == tmp_path / "cache" / "tinyrecorder"

    def test_data_dir_uses_xdg(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """data_dir uses XDG_DATA_HOME when set."""
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
        dirs = LinuxUserDirectories()
        assert dirs.data_dir == tmp_path / "data" / "tinyrecorder"

    def test_config_dir_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """config_dir falls back to ~/.config when XDG_CONFIG_HOME is not set."""
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        dirs = LinuxUserDirectories()
        assert dirs.config_dir == Path.home() / ".config" / "tinyrecorder"

    def test_cache_dir_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """cache_dir falls back to ~/.cache when XDG_CACHE_HOME is not set."""
        monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
        dirs = LinuxUserDirectories()
        assert dirs.cache_dir == Path.home() / ".cache" / "tinyrecorder"

    def test_data_dir_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """data_dir falls back to ~/.local/share when XDG_DATA_HOME is not set."""
        monkeypatch.delenv("XDG_DATA_HOME", raising=False)
        dirs = LinuxUserDirectories()
        assert dirs.data_dir == Path.home() / ".local" / "share" / "tinyrecorder"

    def test_downloads_dir(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """downloads_dir returns ~/Downloads."""
        dirs = LinuxUserDirectories()
        assert dirs.downloads_dir == Path.home() / "Downloads"

    def test_returns_path_objects(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """All directory properties return Path objects."""
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        dirs = LinuxUserDirectories()
        assert isinstance(dirs.config_dir, Path)
        assert isinstance(dirs.cache_dir, Path)
        assert isinstance(dirs.data_dir, Path)
        assert isinstance(dirs.downloads_dir, Path)


class TestPlatformEnv:
    """Tests for LinuxPlatformEnv."""

    def test_sets_qt_platform_theme(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """apply() sets QT_QPA_PLATFORMTHEME if not already set."""
        monkeypatch.delenv("QT_QPA_PLATFORMTHEME", raising=False)
        env = LinuxPlatformEnv()
        env.apply()
        assert os.environ.get("QT_QPA_PLATFORMTHEME") == "xdgdesktopportal"

    def test_does_not_override_existing_theme(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """apply() does not override an existing QT_QPA_PLATFORMTHEME."""
        monkeypatch.setenv("QT_QPA_PLATFORMTHEME", "kde")
        env = LinuxPlatformEnv()
        env.apply()
        assert os.environ["QT_QPA_PLATFORMTHEME"] == "kde"


class TestFfmpegProvider:
    """Tests for LinuxFfmpegProvider."""

    def test_is_available_returns_bool(self) -> None:
        """is_available() returns a boolean."""
        provider = LinuxFfmpegProvider()
        assert isinstance(provider.is_available(), bool)

    def test_is_available_with_mock(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """is_available() delegates to shutil.which."""
        import shutil

        monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/ffmpeg" if name == "ffmpeg" else None)
        provider = LinuxFfmpegProvider()
        assert provider.is_available() is True

    def test_is_not_available_with_mock(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """is_available() returns False when ffmpeg not found."""
        import shutil

        monkeypatch.setattr(shutil, "which", lambda name: None)
        provider = LinuxFfmpegProvider()
        assert provider.is_available() is False


class TestFactoryFunctions:
    """Tests for platform factory functions."""

    @pytest.mark.skipif(sys.platform != "linux", reason="Linux-only test")
    def test_get_user_directories_returns_linux(self) -> None:
        """get_user_directories() returns LinuxUserDirectories on Linux."""
        dirs = get_user_directories()
        assert isinstance(dirs, LinuxUserDirectories)

    @pytest.mark.skipif(sys.platform != "linux", reason="Linux-only test")
    def test_get_platform_env_returns_linux(self) -> None:
        """get_platform_env() returns LinuxPlatformEnv on Linux."""
        env = get_platform_env()
        assert isinstance(env, LinuxPlatformEnv)

    @pytest.mark.skipif(sys.platform != "linux", reason="Linux-only test")
    def test_get_ffmpeg_provider_returns_linux(self) -> None:
        """get_ffmpeg_provider() returns LinuxFfmpegProvider on Linux."""
        provider = get_ffmpeg_provider()
        assert isinstance(provider, LinuxFfmpegProvider)

    @pytest.mark.skipif(sys.platform != "linux", reason="Linux-only test")
    def test_get_instance_lock_returns_socket(self) -> None:
        """get_instance_lock() returns SocketInstanceLock on Linux."""
        lock = get_instance_lock()
        assert isinstance(lock, SocketInstanceLock)

    @pytest.mark.skipif(sys.platform != "linux", reason="Linux-only test")
    def test_get_ipc_server_returns_unix_socket(self) -> None:
        """get_ipc_server() returns UnixSocketIpcTransportServer on Linux."""
        server = get_ipc_server()
        assert isinstance(server, UnixSocketIpcTransportServer)

    @pytest.mark.skipif(sys.platform != "linux", reason="Linux-only test")
    def test_get_ipc_client_returns_unix_socket(self) -> None:
        """get_ipc_client() returns UnixSocketIpcTransport on Linux."""
        client = get_ipc_client()
        assert isinstance(client, UnixSocketIpcTransport)
```

- [ ] **2b.2** Run tests to confirm they fail:

```bash
uv run pytest tests/unit/test_platform.py -v -n0
```

- [ ] **2b.3** Create `src/tinyrecorder/platform/protocols.py`:

```python
"""Platform abstraction protocols.

Defines the contracts that platform-specific implementations must satisfy.
All protocols use structural subtyping (runtime_checkable for isinstance checks in tests).
"""

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

type IpcRequestHandler = Callable[[bytes], Awaitable[bytes]]


@runtime_checkable
class UserDirectories(Protocol):
    """Protocol for platform-specific user directory resolution."""

    @property
    def config_dir(self) -> Path:
        """App config directory (e.g., ~/.config/tinyrecorder on Linux)."""
        ...

    @property
    def cache_dir(self) -> Path:
        """App cache directory (e.g., ~/.cache/tinyrecorder on Linux)."""
        ...

    @property
    def data_dir(self) -> Path:
        """App data directory (e.g., ~/.local/share/tinyrecorder on Linux)."""
        ...

    @property
    def downloads_dir(self) -> Path:
        """User downloads directory (e.g., ~/Downloads)."""
        ...


@runtime_checkable
class IpcTransport(Protocol):
    """Protocol for IPC transport client (sends commands, receives responses)."""

    def send(self, data: bytes, socket_path: Path) -> bytes:
        """Send data and receive response via platform-specific transport.

        Args:
            data: Raw bytes to send.
            socket_path: Path to the IPC endpoint.

        Returns:
            Response bytes from the server.
        """
        ...

    def is_server_running(self, socket_path: Path) -> bool:
        """Check if a server is listening at the given path."""
        ...


@runtime_checkable
class IpcTransportServer(Protocol):
    """Protocol for IPC transport server (listens for connections, dispatches to handler)."""

    async def start(self, socket_path: Path, handler: IpcRequestHandler) -> None:
        """Start listening for connections.

        Args:
            socket_path: Path to bind the IPC endpoint.
            handler: Callback invoked with received data; returns response data.
        """
        ...

    async def stop(self) -> None:
        """Stop the server and clean up resources."""
        ...


@runtime_checkable
class InstanceLock(Protocol):
    """Protocol for single-instance enforcement."""

    def is_locked(self, socket_path: Path) -> bool:
        """Check if another instance holds the lock.

        Args:
            socket_path: Path to the IPC endpoint used as the lock.

        Returns:
            True if another instance is running.
        """
        ...


@runtime_checkable
class PlatformEnv(Protocol):
    """Protocol for platform-specific environment setup."""

    def apply(self) -> None:
        """Apply platform-specific environment variables and tweaks.

        Called once at startup, before QApplication is created.
        """
        ...


@runtime_checkable
class FfmpegProvider(Protocol):
    """Protocol for ffmpeg detection and invocation."""

    def is_available(self) -> bool:
        """Check whether ffmpeg is available on this platform.

        Returns:
            True if ffmpeg can be invoked.
        """
        ...

    def get_executable_path(self) -> Path | None:
        """Get the path to the ffmpeg executable, or None if not found."""
        ...
```

- [ ] **2b.4** Create `src/tinyrecorder/platform/linux.py`:

```python
"""Linux platform implementations.

All classes carry the PlatformSpecific marker with for_platform = "Linux".
"""

import asyncio
import os
import shutil
import socket
from pathlib import Path
from typing import Literal

from tinyrecorder.constants import APP_NAME
from tinyrecorder.platform.protocols import IpcRequestHandler


class PlatformSpecific:
    """Marker class for platform-specific implementations."""

    for_platform: Literal["Linux", "Windows", "MacOS"]


class LinuxUserDirectories(PlatformSpecific):
    """Linux user directories using XDG Base Directory Specification.

    Uses XDG environment variables with standard fallbacks:
    - XDG_CONFIG_HOME -> ~/.config
    - XDG_CACHE_HOME -> ~/.cache
    - XDG_DATA_HOME -> ~/.local/share
    """

    for_platform: Literal["Linux"] = "Linux"

    @property
    def config_dir(self) -> Path:
        """App config directory: $XDG_CONFIG_HOME/tinyrecorder."""
        base = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
        return Path(base) / APP_NAME

    @property
    def cache_dir(self) -> Path:
        """App cache directory: $XDG_CACHE_HOME/tinyrecorder."""
        base = os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))
        return Path(base) / APP_NAME

    @property
    def data_dir(self) -> Path:
        """App data directory: $XDG_DATA_HOME/tinyrecorder."""
        base = os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))
        return Path(base) / APP_NAME

    @property
    def downloads_dir(self) -> Path:
        """User downloads directory: ~/Downloads."""
        return Path.home() / "Downloads"


class LinuxPlatformEnv(PlatformSpecific):
    """Linux platform environment setup.

    Sets QT_QPA_PLATFORMTHEME to 'xdgdesktopportal' if not already set,
    ensuring native file dialogs and theming on Linux desktops.
    """

    for_platform: Literal["Linux"] = "Linux"

    def apply(self) -> None:
        """Set Linux-specific environment variables."""
        if "QT_QPA_PLATFORMTHEME" not in os.environ:
            os.environ["QT_QPA_PLATFORMTHEME"] = "xdgdesktopportal"


class LinuxFfmpegProvider(PlatformSpecific):
    """Linux ffmpeg detection and invocation.

    Uses shutil.which() for detection (searches PATH).
    Invocation via asyncio.create_subprocess_exec.
    """

    for_platform: Literal["Linux"] = "Linux"

    def is_available(self) -> bool:
        """Check whether ffmpeg is on PATH."""
        return shutil.which("ffmpeg") is not None

    def get_executable_path(self) -> Path | None:
        """Get the path to ffmpeg, or None if not found."""
        result = shutil.which("ffmpeg")
        return Path(result) if result is not None else None


class SocketInstanceLock(PlatformSpecific):
    """Single-instance lock using Unix socket connection test.

    Tries to connect to the IPC socket. If connection succeeds,
    another instance is running. If connection fails, no instance is running.
    """

    for_platform: Literal["Linux"] = "Linux"

    def is_locked(self, socket_path: Path) -> bool:
        """Check if another instance is running by attempting socket connection."""
        if not socket_path.exists():
            return False
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(1.0)
            sock.connect(str(socket_path))
            sock.close()
            return True
        except (ConnectionRefusedError, OSError):
            return False


class UnixSocketIpcTransport(PlatformSpecific):
    """Unix domain socket IPC transport client."""

    for_platform: Literal["Linux"] = "Linux"

    def send(self, data: bytes, socket_path: Path) -> bytes:
        """Send data via Unix socket and receive response."""
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.settimeout(5.0)
            sock.connect(str(socket_path))
            sock.sendall(data)
            response = sock.recv(4096)
            return response
        finally:
            sock.close()

    def is_server_running(self, socket_path: Path) -> bool:
        """Check if a server is listening at the socket path."""
        if not socket_path.exists():
            return False
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(1.0)
            sock.connect(str(socket_path))
            sock.close()
            return True
        except (ConnectionRefusedError, OSError):
            return False


class UnixSocketIpcTransportServer(PlatformSpecific):
    """Unix domain socket IPC transport server.

    Handles the low-level socket lifecycle (bind, listen, accept, cleanup).
    The handler callback processes raw bytes and returns response bytes.
    """

    for_platform: Literal["Linux"] = "Linux"

    def __init__(self) -> None:
        self._handler: IpcRequestHandler | None = None

    async def start(self, socket_path: Path, handler: IpcRequestHandler) -> None:
        """Start the Unix socket server."""
        # Clean up stale socket
        if socket_path.exists():
            socket_path.unlink()

        self._socket_path = socket_path
        self._handler = handler
        self._server = await asyncio.start_unix_server(
            self._client_connected,
            path=str(socket_path),
        )

    async def _client_connected(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle an incoming client connection."""
        # Implementation delegates to the handler callback
        # The actual JSON protocol logic lives in ipc.py, not here
        pass  # Actual implementation wired in Task 11

    async def stop(self) -> None:
        """Stop the server and remove the socket file."""
        if hasattr(self, "_server"):
            self._server.close()
            await self._server.wait_closed()
        if hasattr(self, "_socket_path") and self._socket_path.exists():
            self._socket_path.unlink(missing_ok=True)
```

- [ ] **2b.5** Create `src/tinyrecorder/platform/__init__.py`:

```python
"""Platform abstraction layer.

Provides factory functions that return the correct platform-specific
implementations for the current OS. Currently only Linux is supported.

Factory functions:
    get_user_directories() -> UserDirectories
    get_platform_env() -> PlatformEnv
    get_ffmpeg_provider() -> FfmpegProvider
    get_instance_lock() -> InstanceLock
    get_ipc_server() -> IpcTransportServer
    get_ipc_client() -> IpcTransport
"""

import sys
from typing import Literal

from tinyrecorder.platform.linux import (
    LinuxFfmpegProvider,
    LinuxPlatformEnv,
    LinuxUserDirectories,
    PlatformSpecific,
    SocketInstanceLock,
    UnixSocketIpcTransport,
    UnixSocketIpcTransportServer,
)
from tinyrecorder.platform.protocols import (
    FfmpegProvider,
    InstanceLock,
    IpcTransport,
    IpcTransportServer,
    PlatformEnv,
    UserDirectories,
)

__all__ = [
    "PlatformSpecific",
    "get_ffmpeg_provider",
    "get_instance_lock",
    "get_ipc_client",
    "get_ipc_server",
    "get_platform_env",
    "get_user_directories",
]


def _assert_linux() -> None:
    """Raise RuntimeError if not running on Linux."""
    if sys.platform != "linux":
        msg = f"Unsupported platform: {sys.platform}. Only Linux is currently supported."
        raise RuntimeError(msg)


def get_user_directories() -> UserDirectories:
    """Get platform-specific user directory resolver."""
    _assert_linux()
    return LinuxUserDirectories()


def get_platform_env() -> PlatformEnv:
    """Get platform-specific environment configurator."""
    _assert_linux()
    return LinuxPlatformEnv()


def get_ffmpeg_provider() -> FfmpegProvider:
    """Get platform-specific ffmpeg provider."""
    _assert_linux()
    return LinuxFfmpegProvider()


def get_instance_lock() -> InstanceLock:
    """Get platform-specific instance lock."""
    _assert_linux()
    return SocketInstanceLock()


def get_ipc_server() -> IpcTransportServer:
    """Get platform-specific IPC transport server."""
    _assert_linux()
    return UnixSocketIpcTransportServer()


def get_ipc_client() -> IpcTransport:
    """Get platform-specific IPC transport client."""
    _assert_linux()
    return UnixSocketIpcTransport()
```

- [ ] **2b.6** Run tests to confirm they pass:

```bash
uv run pytest tests/unit/test_platform.py -v -n0
```

- [ ] **2b.7** Run type checker and linter:

```bash
uv run basedpyright src/tinyrecorder/platform/
uv run ruff check src/tinyrecorder/platform/
```

- [ ] **2b.8** Commit: `feat(platform): add platform abstraction layer with protocols and Linux implementations`
