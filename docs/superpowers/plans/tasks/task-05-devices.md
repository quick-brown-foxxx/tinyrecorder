# Task 5: Audio Devices (mic enumeration)

**Phase:** 3 (parallel with: Task 4, Task 7, Task 8)
**Dependencies:** Task 1
**Skills:** `writing-python-code`, `testing-python`
**Files to create:** `src/audio/__init__.py`, `src/audio/devices.py`, `src/audio/device_wrapper.py`
**Test files:** `tests/unit/test_devices.py`
**Estimated complexity:** small

---

**Goal:** Create `src/audio/devices.py` with a typed wrapper around `sounddevice.query_devices()` for enumerating microphones and resolving device names to indices. Also create `src/audio/device_wrapper.py` with `AudioDeviceWrapper` — a typed wrapper around `sounddevice.InputStream`/`sounddevice.OutputStream` for recording flexibility (distinct from device enumeration in `devices.py`). This task owns both files.

> **Note (device_wrapper.py):** `AudioDeviceWrapper` wraps the sounddevice library for flexibility and swappability. This is NOT platform-specific — it is a library abstraction wrapper that isolates the rest of the codebase from the untyped sounddevice API. The wrapper should follow the typed wrapper pattern from the `writing-python-code` skill (sole point of contact with the library, typed inputs/outputs, monkeypatchable boundary functions).

#### Steps

- [ ] **5.1** Create `tests/unit/test_devices.py` with all tests (failing):

```python
# tests/unit/test_devices.py
"""Tests for audio device enumeration and resolution."""

from typing import Any

import pytest
from rusty_results import Err, Ok

from tinyrecorder.audio.devices import AudioDeviceInfo, get_default_device, list_input_devices, resolve_device


def _make_fake_devices() -> list[dict[str, object]]:
    """Return a fake device list mimicking sounddevice.query_devices() output."""
    return [
        {
            "name": "Built-in Microphone",
            "index": 0,
            "max_input_channels": 2,
            "max_output_channels": 0,
            "default_samplerate": 44100.0,
            "hostapi": 0,
        },
        {
            "name": "USB Headset",
            "index": 1,
            "max_input_channels": 1,
            "max_output_channels": 2,
            "default_samplerate": 48000.0,
            "hostapi": 0,
        },
        {
            "name": "HDMI Output",
            "index": 2,
            "max_input_channels": 0,
            "max_output_channels": 8,
            "default_samplerate": 48000.0,
            "hostapi": 0,
        },
        {
            "name": "Virtual Mic",
            "index": 3,
            "max_input_channels": 1,
            "max_output_channels": 0,
            "default_samplerate": 16000.0,
            "hostapi": 0,
        },
    ]


def _make_fake_default_input() -> dict[str, object]:
    """Return a fake default input device dict."""
    return {
        "name": "Built-in Microphone",
        "index": 0,
        "max_input_channels": 2,
        "max_output_channels": 0,
        "default_samplerate": 44100.0,
        "hostapi": 0,
    }


class TestListInputDevices:
    """Tests for list_input_devices()."""

    def test_returns_only_input_devices(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Only devices with max_input_channels > 0 are returned."""
        fake_devices = _make_fake_devices()
        monkeypatch.setattr("tinyrecorder.audio.devices._query_devices", lambda: fake_devices)
        result = list_input_devices()
        assert len(result) == 3
        names = [d.name for d in result]
        assert "Built-in Microphone" in names
        assert "USB Headset" in names
        assert "Virtual Mic" in names
        assert "HDMI Output" not in names

    def test_device_info_fields(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """AudioDeviceInfo fields are populated correctly from raw device dict."""
        fake_devices = _make_fake_devices()
        monkeypatch.setattr("tinyrecorder.audio.devices._query_devices", lambda: fake_devices)
        result = list_input_devices()
        mic = next(d for d in result if d.name == "Built-in Microphone")
        assert mic.index == 0
        assert mic.max_input_channels == 2
        assert mic.default_samplerate == 44100.0

    def test_empty_device_list(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns empty list when no devices are available."""
        monkeypatch.setattr("tinyrecorder.audio.devices._query_devices", lambda: [])
        result = list_input_devices()
        assert result == []

    def test_handles_query_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns empty list when sounddevice raises an exception."""

        def _raise() -> list[dict[str, object]]:
            raise OSError("PortAudio not initialized")

        monkeypatch.setattr("tinyrecorder.audio.devices._query_devices", _raise)
        result = list_input_devices()
        assert result == []


class TestResolveDevice:
    """Tests for resolve_device()."""

    def test_resolve_exact_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Exact device name returns Ok with the device index."""
        fake_devices = _make_fake_devices()
        monkeypatch.setattr("tinyrecorder.audio.devices._query_devices", lambda: fake_devices)
        result = resolve_device("USB Headset")
        assert result == Ok(1)

    def test_resolve_partial_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Substring match on device name returns Ok with the device index."""
        fake_devices = _make_fake_devices()
        monkeypatch.setattr("tinyrecorder.audio.devices._query_devices", lambda: fake_devices)
        result = resolve_device("Virtual")
        assert result == Ok(3)

    def test_resolve_case_insensitive(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Device name matching is case-insensitive."""
        fake_devices = _make_fake_devices()
        monkeypatch.setattr("tinyrecorder.audio.devices._query_devices", lambda: fake_devices)
        result = resolve_device("built-in microphone")
        assert result == Ok(0)

    def test_resolve_nonexistent_device(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Non-existent device name returns Err."""
        fake_devices = _make_fake_devices()
        monkeypatch.setattr("tinyrecorder.audio.devices._query_devices", lambda: fake_devices)
        result = resolve_device("Nonexistent Device")
        assert isinstance(result, Err)
        assert "not found" in result.unwrap_err().lower()

    def test_resolve_output_only_device(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Output-only device is not resolvable as input."""
        fake_devices = _make_fake_devices()
        monkeypatch.setattr("tinyrecorder.audio.devices._query_devices", lambda: fake_devices)
        result = resolve_device("HDMI Output")
        assert isinstance(result, Err)


class TestGetDefaultDevice:
    """Tests for get_default_device()."""

    def test_returns_default_input_device(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns Ok with the system default input device."""
        fake_default = _make_fake_default_input()
        monkeypatch.setattr("tinyrecorder.audio.devices._query_default_input_device", lambda: fake_default)
        result = get_default_device()
        assert isinstance(result, Ok)
        device = result.unwrap()
        assert device.name == "Built-in Microphone"
        assert device.index == 0

    def test_no_default_device(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns Err when no default input device is available."""

        def _raise() -> dict[str, object]:
            raise OSError("No default input device")

        monkeypatch.setattr("tinyrecorder.audio.devices._query_default_input_device", _raise)
        result = get_default_device()
        assert isinstance(result, Err)
        assert "no default" in result.unwrap_err().lower()
```

- [ ] **5.2** Run tests to confirm they fail:

```bash
python -m pytest tests/unit/test_devices.py -v 2>&1 | head -40
```

- [ ] **5.3** Create `src/audio/__init__.py`:

```python
# src/audio/__init__.py
"""Audio recording, processing, and device management."""
```

- [ ] **5.4** Create `src/audio/devices.py`:

```python
# src/audio/devices.py
"""Typed wrapper around sounddevice for audio device enumeration.

Isolates the untyped sounddevice API behind typed functions and dataclasses.
"""

from dataclasses import dataclass

from rusty_results import Err, Ok, Result


@dataclass(frozen=True)
class AudioDeviceInfo:
    """Information about an audio input device."""

    name: str
    index: int
    max_input_channels: int
    default_samplerate: float


def _query_devices() -> list[dict[str, object]]:
    """Query all audio devices via sounddevice.

    This is the sole point of contact with the sounddevice library for device listing.
    Monkeypatch this function in tests to avoid hardware dependency.
    """
    import sounddevice as sd  # pyright: ignore[reportMissingModuleSource]

    raw: object = sd.query_devices()
    if not isinstance(raw, list):
        return []
    devices: list[dict[str, object]] = []
    for item in raw:
        if isinstance(item, dict):
            devices.append(item)
    return devices


def _query_default_input_device() -> dict[str, object]:
    """Query the default input device via sounddevice.

    This is the sole point of contact with the sounddevice library for default device.
    Monkeypatch this function in tests to avoid hardware dependency.

    Raises:
        OSError: If no default input device is available.
    """
    import sounddevice as sd  # pyright: ignore[reportMissingModuleSource]

    raw: object = sd.query_devices(kind="input")
    if not isinstance(raw, dict):
        msg = "No default input device available"
        raise OSError(msg)
    return raw


def _parse_device_info(raw: dict[str, object]) -> AudioDeviceInfo | None:
    """Parse a raw device dict into AudioDeviceInfo. Returns None if invalid."""
    name = raw.get("name")
    index = raw.get("index")
    max_input_channels = raw.get("max_input_channels")
    default_samplerate = raw.get("default_samplerate")
    if not isinstance(name, str):
        return None
    if not isinstance(index, int):
        return None
    if not isinstance(max_input_channels, int):
        return None
    if not isinstance(default_samplerate, float | int):
        return None
    return AudioDeviceInfo(
        name=name,
        index=index,
        max_input_channels=max_input_channels,
        default_samplerate=float(default_samplerate),
    )


def list_input_devices() -> list[AudioDeviceInfo]:
    """List all available audio input devices.

    Returns:
        List of input devices (max_input_channels > 0). Empty list on error.
    """
    try:
        raw_devices = _query_devices()
    except Exception:
        return []
    devices: list[AudioDeviceInfo] = []
    for raw in raw_devices:
        info = _parse_device_info(raw)
        if info is not None and info.max_input_channels > 0:
            devices.append(info)
    return devices


def resolve_device(name: str) -> Result[int, str]:
    """Resolve a device name (or substring) to a device index.

    Matching is case-insensitive and supports partial (substring) matches.
    Only input devices (max_input_channels > 0) are considered.

    Args:
        name: Full or partial device name to search for.

    Returns:
        Ok(device_index) if found, Err(message) if not found.
    """
    input_devices = list_input_devices()
    name_lower = name.lower()
    for device in input_devices:
        if name_lower in device.name.lower():
            return Ok(device.index)
    return Err(f"Input device not found: '{name}'")


def get_default_device() -> Result[AudioDeviceInfo, str]:
    """Get the system default audio input device.

    Returns:
        Ok(AudioDeviceInfo) if available, Err(message) if no default device.
    """
    try:
        raw = _query_default_input_device()
    except Exception as exc:
        return Err(f"No default input device: {exc}")
    info = _parse_device_info(raw)
    if info is None:
        return Err("No default input device: could not parse device info")
    return Ok(info)
```

- [ ] **5.5** Create `src/audio/device_wrapper.py`:

```python
# src/tinyrecorder/audio/device_wrapper.py
"""Typed wrapper around sounddevice for audio I/O flexibility."""

from collections.abc import Callable
from typing import Protocol

import numpy as np
from numpy.typing import NDArray


class AudioInputStream(Protocol):
    """Protocol for audio input streams — abstracts sounddevice.InputStream."""

    def start(self) -> None: ...
    def stop(self) -> None: ...
    def close(self) -> None: ...

    @property
    def active(self) -> bool: ...


class SounddeviceInputStream:
    """Typed wrapper around sounddevice.InputStream.

    This is the sole point of contact with sounddevice for streaming input.
    Monkeypatch or substitute via the AudioInputStream protocol in tests.
    """

    def __init__(
        self,
        samplerate: int,
        channels: int,
        dtype: str,
        blocksize: int,
        device: int | None,
        callback: Callable[[NDArray[np.int16], object], None],
    ) -> None:
        import sounddevice as sd  # pyright: ignore[reportMissingModuleSource]

        self._stream = sd.InputStream(
            samplerate=samplerate,
            channels=channels,
            dtype=dtype,
            blocksize=blocksize,
            device=device,
            callback=callback,
        )

    def start(self) -> None:
        self._stream.start()

    def stop(self) -> None:
        self._stream.stop()

    def close(self) -> None:
        self._stream.close()

    @property
    def active(self) -> bool:
        return bool(self._stream.active)
```

- [ ] **5.6** Add device_wrapper tests to `tests/unit/test_devices.py` (append to existing file):

```python
# --- device_wrapper tests (append to tests/unit/test_devices.py) ---

from tinyrecorder.audio.device_wrapper import AudioInputStream, SounddeviceInputStream


class _FakeStream:
    """Minimal fake satisfying AudioInputStream protocol."""

    def __init__(self) -> None:
        self._active = False

    def start(self) -> None:
        self._active = True

    def stop(self) -> None:
        self._active = False

    def close(self) -> None:
        self._active = False

    @property
    def active(self) -> bool:
        return self._active


class TestAudioInputStreamProtocol:
    """Tests for AudioInputStream protocol compliance."""

    def test_fake_stream_satisfies_protocol(self) -> None:
        """A simple fake stream satisfies the AudioInputStream protocol."""
        stream: AudioInputStream = _FakeStream()
        stream.start()
        assert stream.active is True
        stream.stop()
        assert stream.active is False
        stream.close()
```

- [ ] **5.7** Run tests to confirm they pass:

```bash
python -m pytest tests/unit/test_devices.py -v
```

- [ ] **5.8** Commit: `feat(audio): add typed device enumeration and input stream wrapper`
