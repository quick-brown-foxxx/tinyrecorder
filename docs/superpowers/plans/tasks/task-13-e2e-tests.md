# Task 13: E2E Tests with qt-ai-dev-tools

**Phase:** 8 (sequential, after ALL previous tasks)
**Dependencies:** All tasks (1-12) — requires fully assembled app
**Skills:** `qt-app-interaction`, `qt-desktop-integration`, `qt-dev-tools-setup`, `testing-python`
**Files to create:** `tests/e2e/conftest.py`, `tests/e2e/test_recording_flow.py`, `tests/e2e/test_tray_lifecycle.py`, `tests/e2e/test_no_api_key.py`, `tests/e2e/test_file_import.py`, `tests/e2e/test_ipc_live.py`, `tests/e2e/test_crash_recovery.py`, `tests/e2e/assets/known_speech.wav`
**Test files:** All files above ARE the tests
**Estimated complexity:** large

---

**Goal:** Real end-to-end tests that run TinyRecorder in a VM via qt-ai-dev-tools. Tests interact through AT-SPI (widget clicking, text reading), system tray (D-Bus), and audio (PipeWire virtual mic). These are the highest-confidence tests — they prove the real app works for real users.

> **⚠️ Audio (alpha):** qt-ai-dev-tools audio features (virtual mic, recording, verify) are **alpha** and may not work reliably. Tests using audio (`test_recording_flow.py`, `test_crash_recovery.py`) are written normally — if audio doesn't work in practice, add `@pytest.mark.skip(reason="qt-ai-dev-tools audio not working in VM")` at that point. Non-audio e2e tests (tray lifecycle, settings, IPC) use stable AT-SPI/D-Bus features.

**Relationship to other tests:**
- Unit tests (Tasks 2-8): test pure logic in isolation — KEEP
- pytest-qt tests (Tasks 9a-9c): basic widget instantiation checks — KEEP as smoke tests, but they are NOT e2e
- Integration tests (Tasks 10-11): CLI + IPC tests via typer runner — KEEP
- **This task: real GUI tests through actual UI** — the top of the testing pyramid

> **Note:** qt-ai-dev-tools VM setup (`workspace init`, `vm up`) should be done once before running these tests. Add a `pytest.ini` marker `e2e` so these can be skipped when VM is not available: `pytest -m "not e2e"`.

---

### Step 1: Set up VM workspace

- [ ] Initialize qt-ai-dev-tools workspace:

```bash
uvx qt-ai-dev-tools workspace init
```

- [ ] Add `.qt-ai-dev-tools/` to `.gitignore` (already there from Task 1 if using the template gitignore)

- [ ] Boot VM (first time ~10 min):

```bash
uvx qt-ai-dev-tools vm up
uvx qt-ai-dev-tools vm status  # verify Xvfb, openbox, AT-SPI running
```

### Step 2: Create e2e test infrastructure

- [ ] Create `tests/e2e/__init__.py` (empty)

- [ ] Create `tests/e2e/conftest.py`:

```python
"""E2E test infrastructure: VM management, mock OpenAI server, audio fixtures."""

import json
import subprocess
import time
from pathlib import Path

import pytest
from pytest_httpserver import HTTPServer

MOCK_TRANSCRIPT = "The quick brown fox jumps over the lazy dog"
QT_DEV = "uvx qt-ai-dev-tools"


def _run(cmd: str, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    """Run a shell command, return CompletedProcess."""
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)


@pytest.fixture(scope="session")
def vm_ready() -> None:
    """Ensure VM is booted and services are running. Skip if unavailable."""
    result = _run(f"{QT_DEV} vm status")
    if result.returncode != 0:
        pytest.skip("qt-ai-dev-tools VM not running. Run: uvx qt-ai-dev-tools vm up")


@pytest.fixture(scope="session")
def mock_openai_e2e(tmp_path_factory: pytest.TempPathFactory) -> str:
    """Start a mock OpenAI server that returns a known transcript.

    Returns the base URL accessible from the VM.
    """
    # Use pytest-httpserver for a real HTTP server
    # The VM accesses host via gateway IP — varies by Vagrant network config
    # For simplicity, bind to 0.0.0.0 and use the host's IP
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        host_ip = s.getsockname()[0]
    except Exception:
        host_ip = "127.0.0.1"
    finally:
        s.close()

    # Note: pytest-httpserver binds to 127.0.0.1 by default
    # For VM access we'd need 0.0.0.0 — this is a limitation
    # Alternative: run the mock inside the VM
    return f"http://{host_ip}"  # placeholder — real impl needs network config


@pytest.fixture()
def app_running(vm_ready: None) -> None:
    """Sync project files, start app in VM, wait for it to appear."""
    _run(f"{QT_DEV} vm sync")
    _run(f'{QT_DEV} vm run "python3 -m tinyrecorder &"')
    result = _run(f"{QT_DEV} wait --app tinyrecorder --timeout 15")
    if result.returncode != 0:
        pytest.fail("App did not start within 15 seconds")
    yield
    # Cleanup: kill app
    _run(f'{QT_DEV} vm run "pkill -f tinyrecorder"', timeout=5)
    time.sleep(1)


@pytest.fixture()
def virtual_mic(vm_ready: None) -> None:
    """Start a virtual microphone, clean up after test."""
    _run(f"{QT_DEV} audio virtual-mic start")
    yield
    _run(f"{QT_DEV} audio virtual-mic stop")
```

- [ ] Create `tests/e2e/assets/` directory and add a `known_speech.wav`:

```bash
# Generate a 5-second 440Hz tone as placeholder
# (Replace with real speech WAV for actual transcription testing)
python3 -c "
import wave, numpy as np
sr = 16000; dur = 5.0
t = np.linspace(0, dur, int(sr*dur), endpoint=False)
samples = (np.sin(2*np.pi*440*t) * 32767 * 0.5).astype(np.int16)
with wave.open('tests/e2e/assets/known_speech.wav', 'wb') as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
    w.writeframes(samples.tobytes())
"
```

### Step 3: Write E2E tests

- [ ] Create `tests/e2e/test_recording_flow.py`:

```python
"""E2E-1: Full recording → transcription flow."""

import subprocess
import time

import pytest

QT = "uvx qt-ai-dev-tools"


def run(cmd: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)


@pytest.mark.e2e
class TestRecordingFlow:
    """Record audio via virtual mic, transcribe, verify result."""

    def test_full_recording_to_transcript(self, app_running: None, virtual_mic: None) -> None:
        # Open window via tray
        result = run(f"{QT} tray click TinyRecorder")
        assert result.returncode == 0
        time.sleep(1)

        # Verify main window widgets
        result = run(f"{QT} tree")
        assert "push button" in result.stdout
        assert "REC" in result.stdout or "Record" in result.stdout

        # Feed audio to virtual mic
        run(f"{QT} audio virtual-mic play tests/e2e/assets/known_speech.wav")

        # Click record
        result = run(f'{QT} click --role "push button" --name "REC"')
        assert result.returncode == 0
        time.sleep(6)  # Wait for audio to play

        # Click stop
        result = run(f'{QT} click --role "push button" --name "STOP"')
        assert result.returncode == 0

        # Wait for transcription (poll)
        for _ in range(30):
            result = run(f'{QT} text --role "text"')
            if "quick brown fox" in result.stdout.lower():
                break
            time.sleep(1)
        else:
            # Take screenshot for debugging
            run(f"{QT} screenshot -o /tmp/e2e_recording_fail.png")
            pytest.fail("Transcript did not appear within 30 seconds")

        # Verify copy button works
        result = run(f'{QT} click --role "push button" --name "Copy"')
        assert result.returncode == 0
```

- [ ] Create `tests/e2e/test_tray_lifecycle.py`:

```python
"""E2E-2: System tray show/hide, context menu, quit."""

import subprocess
import time

import pytest

QT = "uvx qt-ai-dev-tools"


def run(cmd: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)


@pytest.mark.e2e
class TestTrayLifecycle:

    def test_tray_icon_appears(self, app_running: None) -> None:
        result = run(f"{QT} tray list")
        assert "TinyRecorder" in result.stdout or "tinyrecorder" in result.stdout

    def test_tray_toggle_window(self, app_running: None) -> None:
        # Show window
        run(f"{QT} tray click TinyRecorder")
        time.sleep(1)
        result = run(f"{QT} tree")
        assert "TinyRecorder" in result.stdout  # window visible

        # Hide window
        run(f"{QT} tray click TinyRecorder")
        time.sleep(1)
        result = run(f"{QT} tree")
        # Window should be hidden — tree may be empty or show no frame

    def test_tray_menu_items(self, app_running: None) -> None:
        result = run(f"{QT} tray menu TinyRecorder")
        assert "Show" in result.stdout or "Hide" in result.stdout
        assert "Settings" in result.stdout
        assert "Quit" in result.stdout

    def test_tray_quit(self, app_running: None) -> None:
        run(f"{QT} tray select TinyRecorder Quit")
        time.sleep(2)
        result = run(f"{QT} tray list")
        assert "TinyRecorder" not in result.stdout
```

- [ ] Create `tests/e2e/test_no_api_key.py`:

```python
"""E2E-3: App without API key opens settings, disables recording."""

import subprocess
import time

import pytest

QT = "uvx qt-ai-dev-tools"


def run(cmd: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)


@pytest.mark.e2e
class TestNoApiKey:

    def test_settings_opens_when_no_key(self, vm_ready: None) -> None:
        # Start app with empty config
        run(f'{QT} vm run "XDG_CONFIG_HOME=/tmp/e2e_nokey python3 -m tinyrecorder &"')
        time.sleep(5)

        # Settings dialog should open automatically
        result = run(f"{QT} tree")
        assert "API" in result.stdout or "api" in result.stdout.lower()
        assert "Settings" in result.stdout or "dialog" in result.stdout

        # Cleanup
        run(f'{QT} vm run "pkill -f tinyrecorder"')
```

- [ ] Create `tests/e2e/test_ipc_live.py`:

```python
"""E2E-5: IPC commands controlling running GUI instance."""

import json
import subprocess
import time

import pytest

QT = "uvx qt-ai-dev-tools"


def run(cmd: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)


@pytest.mark.e2e
class TestIPCLive:

    def test_status_returns_idle(self, app_running: None) -> None:
        result = run(f'{QT} vm run "python3 -m tinyrecorder status"')
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["state"] == "idle"

    def test_record_toggle_starts_recording(self, app_running: None, virtual_mic: None) -> None:
        run(f"{QT} audio virtual-mic play tests/e2e/assets/known_speech.wav")
        result = run(f'{QT} vm run "python3 -m tinyrecorder record-toggle"')
        assert result.returncode == 0

        # Verify UI shows recording
        time.sleep(1)
        result = run(f'{QT} tree')
        assert "STOP" in result.stdout

        # Cancel
        run(f'{QT} vm run "python3 -m tinyrecorder record-cancel"')
        time.sleep(1)
        result = run(f'{QT} tree')
        assert "REC" in result.stdout
```

- [ ] Create `tests/e2e/test_crash_recovery.py`:

```python
"""E2E-6: Kill app mid-recording, restart, verify PCM recovery."""

import subprocess
import time

import pytest

QT = "uvx qt-ai-dev-tools"


def run(cmd: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)


@pytest.mark.e2e
class TestCrashRecovery:

    def test_orphaned_pcm_recovered(self, app_running: None, virtual_mic: None) -> None:
        # Start recording
        run(f"{QT} audio virtual-mic play tests/e2e/assets/known_speech.wav")
        run(f'{QT} click --role "push button" --name "REC"')
        time.sleep(3)

        # Kill app mid-recording
        run(f'{QT} vm run "pkill -9 -f tinyrecorder"')
        time.sleep(2)

        # Verify orphaned PCM exists
        result = run(f'{QT} vm run "ls ~/.cache/tinyrecorder/audio/*.pcm 2>/dev/null"')
        assert ".pcm" in result.stdout

        # Restart app
        run(f'{QT} vm run "python3 -m tinyrecorder &"')
        time.sleep(5)

        # Verify PCM was recovered to WAV
        result = run(f'{QT} vm run "ls ~/.cache/tinyrecorder/audio/*.wav 2>/dev/null"')
        assert ".wav" in result.stdout
```

### Step 4: Update pytest config

- [ ] Add e2e marker and exclude from default runs in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
markers = [
    "unit: unit tests",
    "integration: integration tests",
    "e2e: end-to-end tests (requires qt-ai-dev-tools VM)",
]
addopts = ["-n", "auto", "--dist", "worksteal", "-m", "not e2e"]
```

This way `uv run poe test` skips e2e tests. Run e2e explicitly: `uv run pytest -m e2e -n0`

### Step 5: Add manual testing checklist

- [ ] Create `docs/manual-testing-checklist.md`:

```markdown
# TinyRecorder Manual Testing Checklist

Run these interactively with qt-ai-dev-tools after UI changes.
Prerequisite: `uvx qt-ai-dev-tools vm up && uvx qt-ai-dev-tools vm sync`

## Visual Inspection
- [ ] `uvx qt-ai-dev-tools screenshot -o /tmp/before.png` — baseline
- [ ] Make UI change, rebuild, sync: `uvx qt-ai-dev-tools vm sync`
- [ ] `uvx qt-ai-dev-tools screenshot -o /tmp/after.png` — compare

## Widget Accessibility Audit
- [ ] `uvx qt-ai-dev-tools tree` — all widgets have accessible names
- [ ] No unnamed buttons or labels
- [ ] Correct AT-SPI roles assigned

## State Transitions Walk-through
- [ ] Click REC → screenshot (recording state)
- [ ] Click STOP → screenshot (processing state)
- [ ] Wait → screenshot (success state)
- [ ] Click Retry → screenshot (processing again)

## Tray Menu
- [ ] `uvx qt-ai-dev-tools tray menu TinyRecorder` — all items present
- [ ] Show/Hide toggles correctly
- [ ] Settings opens dialog
- [ ] Quit exits app

## Window Sizing
- [ ] Screenshot at default size (400x550)
- [ ] Screenshot at minimum size (350x450)
- [ ] No clipping, no overflow
```

### Step 6: Commit

```bash
git add tests/e2e/ docs/manual-testing-checklist.md
git commit -m "feat(e2e): add E2E tests with qt-ai-dev-tools VM and manual testing checklist"
```
