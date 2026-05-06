# Task 12: Startup Integration + Crash Recovery Wiring

**Phase:** 7 (sequential, after ALL previous tasks)
**Dependencies:** All tasks (1-11, including 2b)
**Skills:** `building-qt-apps`, `building-multi-ui-apps`, `setting-up-logging`, `writing-python-code`, `testing-python`
**Files to create:** `src/ui/app.py` (update), `src/__main__.py` (update)
**Test files:** `tests/integration/test_startup.py`
**Estimated complexity:** large

---

**Goal:** Wire all components together: startup sequence, single-instance check, crash recovery, IPC server, recording-processing-transcription pipeline, and IPC command dispatch. This is the integration task that connects the GUI event loop + async operations + IPC server in the qasync loop.

> **Note (platform layer):** Startup uses factory functions from `tinyrecorder.platform` to get the correct platform implementations:
> - `get_user_directories()` — for config, cache, data, and download paths
> - `get_platform_env()` — for platform-specific environment setup (e.g., `QT_QPA_PLATFORMTHEME` on Linux)
> - `get_instance_lock()` — for single-instance enforcement
> - `get_ipc_server()` / `get_ipc_client()` — for IPC transport
> - `get_ffmpeg_provider()` — for ffmpeg detection/invocation
>
> These are wired at startup before any other component initialization.

> **Note (recover_orphaned_pcm):** Import from `tinyrecorder.audio.recorder`, NOT `tinyrecorder.audio.processor`. The function uses constants for sample_rate (no extra parameter). Correct import: `from tinyrecorder.audio.recorder import recover_orphaned_pcm`.

> **Note (AudioProcessor):** Import the class from `tinyrecorder.audio.processor`. It wraps free functions with methods: `process_audio()`, `compress_audio()`, `chunk_audio()`, `is_ffmpeg_available()`.

> **Note (HistoryManager):** Import the class from `tinyrecorder.history`. It wraps `write_entry()`/`read_entries()` with methods: `add_entry(...)`, `get_recent(limit)`, `get_entry(index)`.

> **Note (run_gui):** This task replaces the `NotImplementedError` stub from Task 9a with the real implementation.

#### Steps

- [ ] Create `tests/integration/test_startup.py`:

```python
"""Integration tests for startup sequence and crash recovery."""

from __future__ import annotations

import struct
import wave
from pathlib import Path

import numpy as np
import pytest

from tinyrecorder.config import AppConfig, load_config, save_config
from tinyrecorder.constants import APP_NAME


@pytest.fixture()
def config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a tmp config dir and point XDG_CONFIG_HOME there."""
    config_home = tmp_path / "config"
    config_home.mkdir()
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))
    return config_home


@pytest.fixture()
def cache_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a tmp cache dir and point XDG_CACHE_HOME there."""
    cache_home = tmp_path / "cache"
    cache_home.mkdir()
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache_home))
    return cache_home


@pytest.fixture()
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a tmp data dir and point XDG_DATA_HOME there."""
    data_home = tmp_path / "data"
    data_home.mkdir()
    monkeypatch.setenv("XDG_DATA_HOME", str(data_home))
    return data_home


def test_startup_missing_config_creates_defaults(
    config_dir: Path,
    cache_dir: Path,
    data_dir: Path,
) -> None:
    """When no config file exists, startup creates one with default values."""
    config_path = config_dir / APP_NAME / "config.toml"
    result = load_config(config_path)
    assert result.is_ok

    assert config_path.exists()
    config = result.unwrap()
    assert config.model == "gpt-4o-mini-transcribe"
    assert config.language == "auto"
    assert config.auto_copy is True
    assert config.noise_reduction is False


def test_startup_orphaned_pcm_recovery(
    config_dir: Path,
    cache_dir: Path,
    data_dir: Path,
) -> None:
    """Orphaned .pcm files in cache are recovered to .wav with correct headers."""
    from tinyrecorder.audio.recorder import recover_orphaned_pcm

    # Create the audio cache subdir
    audio_cache = cache_dir / APP_NAME / "audio"
    audio_cache.mkdir(parents=True)

    # Write a valid PCM file: 1 second of silence at 16kHz mono int16
    pcm_path = audio_cache / "rec_20260408_120000.pcm"
    sample_rate = 16000
    num_samples = sample_rate  # 1 second
    silence = np.zeros(num_samples, dtype=np.int16)
    pcm_path.write_bytes(silence.tobytes())

    # No matching .wav should exist
    wav_path = audio_cache / "rec_20260408_120000.wav"
    assert not wav_path.exists()

    # Run recovery (uses constants, no sample_rate parameter)
    recovered = recover_orphaned_pcm(audio_cache)

    assert len(recovered) == 1
    assert recovered[0].exists()
    assert recovered[0].suffix == ".wav"

    # Verify the WAV is valid
    with wave.open(str(recovered[0]), "rb") as wf:
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2
        assert wf.getframerate() == sample_rate
        assert wf.getnframes() == num_samples


def test_startup_orphaned_pcm_skips_existing_wav(
    config_dir: Path,
    cache_dir: Path,
    data_dir: Path,
) -> None:
    """Recovery skips .pcm files that already have a matching .wav."""
    from tinyrecorder.audio.recorder import recover_orphaned_pcm

    audio_cache = cache_dir / APP_NAME / "audio"
    audio_cache.mkdir(parents=True)

    # Write a PCM and its matching WAV
    pcm_path = audio_cache / "rec_20260408_130000.pcm"
    wav_path = audio_cache / "rec_20260408_130000.wav"

    sample_rate = 16000
    silence = np.zeros(sample_rate, dtype=np.int16)
    pcm_path.write_bytes(silence.tobytes())

    # Create a matching WAV (even if empty, just needs to exist)
    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(silence.tobytes())

    recovered = recover_orphaned_pcm(audio_cache)
    assert len(recovered) == 0


def test_startup_empty_pcm_skipped(
    config_dir: Path,
    cache_dir: Path,
    data_dir: Path,
) -> None:
    """Empty .pcm files are skipped during recovery (nothing to recover)."""
    from tinyrecorder.audio.recorder import recover_orphaned_pcm

    audio_cache = cache_dir / APP_NAME / "audio"
    audio_cache.mkdir(parents=True)

    pcm_path = audio_cache / "rec_20260408_140000.pcm"
    pcm_path.write_bytes(b"")

    recovered = recover_orphaned_pcm(audio_cache)
    assert len(recovered) == 0
```

- [ ] Run tests and confirm they fail:

```bash
uv run pytest tests/integration/test_startup.py -x -v 2>&1 | head -50
```

- [ ] In `ApplicationController._on_transcription_success`, after displaying the transcription, auto-copy to clipboard if configured:

```python
if self._config.auto_copy:
    clipboard = QApplication.clipboard()
    if clipboard is not None:
        clipboard.setText(transcription.text)
```

- [ ] In the recording loop, update the timer label on each tick so the user sees elapsed MM:SS:

```python
elapsed = time.monotonic() - self._recording_start_time
minutes, seconds = divmod(int(elapsed), 60)
self._main_window.set_timer_text(f"{minutes:02d}:{seconds:02d}")
```

- [ ] Accumulate API cost from transcription responses and update the status bar:

```python
self._session_cost_usd += transcription.cost_usd
self._main_window.set_cost_display(self._session_cost_usd)
```

- [ ] In `run_gui()`, BEFORE creating QApplication, initialize platform layer and set up logging:

```python
import logging
from tinyrecorder.platform import get_user_directories, get_platform_env, get_instance_lock, get_ipc_server, get_ffmpeg_provider
from tinyrecorder.shared.logging import setup_file_logging, setup_stdout_logging, configure_logger_level

# Initialize platform layer
user_dirs = get_user_directories()
platform_env = get_platform_env()
platform_env.apply()  # Set platform-specific env vars (e.g., QT_QPA_PLATFORMTHEME on Linux)

setup_file_logging(log_dir=user_dirs.data_dir / "logs", app_name="tinyrecorder")
setup_stdout_logging(level=logging.INFO)
configure_logger_level("httpx", logging.WARNING)
configure_logger_level("openai", logging.WARNING)

# Single-instance check
instance_lock = get_instance_lock()
# ... check and acquire lock ...
```

- [ ] Update `src/ui/app.py` -- replace the `run_gui` stub with the real implementation, add `ApplicationController` class that wires all components together. Key imports:

```python
from tinyrecorder.platform import get_user_directories, get_platform_env, get_instance_lock, get_ipc_server, get_ffmpeg_provider
from tinyrecorder.audio.recorder import recover_orphaned_pcm  # NOT from processor
from tinyrecorder.audio.processor import AudioProcessor  # class, not free functions
from tinyrecorder.history import HistoryManager  # class wrapping free functions
```

- [ ] Update `src/__main__.py` (no changes needed, already delegates to `tinyrecorder.cli`).

- [ ] Run startup integration tests:

```bash
uv run pytest tests/integration/test_startup.py -x -v 2>&1 | head -50
```

- [ ] Run the full test suite to verify nothing is broken:

```bash
uv run pytest tests/ -x -v 2>&1 | tail -40
```

- [ ] Commit: `feat(startup): wire all components together with crash recovery, IPC, and full pipeline`
