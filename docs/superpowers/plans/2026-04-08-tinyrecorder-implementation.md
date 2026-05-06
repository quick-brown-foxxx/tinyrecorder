# TinyRecorder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build TinyRecorder -- a compact PySide6 system tray STT app with CLI, using OpenAI Whisper API for transcription. Crash-safe recording, retry logic, persistent history, IPC for KDE shortcuts.

**Architecture:** Layered multi-file Python project: UI (QWidgets, swappable) -> Domain (state machine, recorder, transcription provider) -> Utilities (config, IPC, history). Dependencies flow downward only. Provider protocol enables future STT backends.

**Tech Stack:** Python 3.14, PySide6 + qasync, sounddevice, noisereduce, OpenAI API (httpx), typer CLI, rusty-results, TOML config, JSONL history, Unix domain socket IPC. Platform abstraction layer (`platform/` package) with Protocol + factory pattern for future Windows/macOS support.

> **IMPORTANT: Package layout is `src/tinyrecorder/`, not `src/`.** All imports use `from tinyrecorder.module import ...` (e.g., `from tinyrecorder.config import AppConfig`). The older `from src.module` pattern in some task files should be read as `from tinyrecorder.module`.

**Spec:** `docs/superpowers/specs/2026-04-08-tinyrecorder-design.md`
**Test Cases:** `docs/plans/test-cases-tinyrecorder.md`

---

## File Structure

```
tinyrecorder/
├── pyproject.toml
├── src/
│   ├── __main__.py             # Entry point: CLI dispatch or GUI launch
│   ├── cli.py                  # typer CLI: transcribe, record-toggle, record-cancel, status
│   ├── ipc.py                  # IPC protocol layer: JSON serialization, command types, dispatch (platform-agnostic)
│   ├── config.py               # TOML config load/save, typed config dataclass
│   ├── constants.py            # App name, default config values, audio defaults, supported models/languages
│   ├── state.py                # Recording state machine (enum + transitions)
│   ├── history.py              # JSONL history read/write, entry dataclass, HistoryManager class
│   │
│   ├── platform/
│   │   ├── __init__.py         # PlatformSpecific marker, factory functions: get_user_directories(), get_ipc_server(), etc.
│   │   ├── protocols.py        # UserDirectories, IpcTransport, IpcTransportServer, InstanceLock, PlatformEnv, FfmpegProvider protocols
│   │   └── linux.py            # All Linux implementations: LinuxUserDirectories, UnixSocketIpcTransport, SocketInstanceLock, etc.
│   │
│   ├── audio/
│   │   ├── recorder.py         # sounddevice wrapper + async recording via callback+Queue + recover_orphaned_pcm
│   │   ├── processor.py        # AudioProcessor class: noise reduction, format conversion, compression
│   │   ├── devices.py          # Mic enumeration, device selection
│   │   └── device_wrapper.py   # AudioDeviceWrapper around sounddevice (library abstraction, not platform-specific)
│   │
│   ├── transcription/
│   │   ├── provider.py         # Protocol (abstract interface) for any STT provider
│   │   └── openai_provider.py  # OpenAI API: whisper-1, gpt-4o-transcribe, gpt-4o-mini-transcribe
│   │
│   └── ui/
│       ├── app.py              # QApplication + qasync setup, tray icon, IPC server start, run_gui
│       ├── main_window.py      # Main window: record button, result area, controls
│       ├── widgets.py          # VU meter widget, transcript display, history panel
│       └── styles.py           # Stylesheet / theming constants
│
├── tests/
│   ├── conftest.py             # Shared fixtures: qapp, tmp dirs, sample audio
│   ├── unit/
│   └── integration/
└── docs/
    └── superpowers/specs/
```

---

## Execution Phases

### Phase 1: Foundation (sequential)
| Task | File | Skills | Est. |
|------|------|--------|------|
| [Task 1: Project Scaffold](tasks/task-01-scaffold.md) | `pyproject.toml`, `src/constants.py`, `tests/conftest.py` | `setting-up-python-projects`, `writing-python-code` | small |

### Phase 2: Core Domain (after Phase 1)
| Task | File | Skills | Est. |
|------|------|--------|------|
| [Task 2b: Platform Layer](tasks/task-02b-platform.md) | `src/platform/__init__.py`, `src/platform/protocols.py`, `src/platform/linux.py` | `writing-python-code`, `building-multi-ui-apps` | medium |
| [Task 2: Config](tasks/task-02-config.md) | `src/config.py` | `writing-python-code`, `testing-python` | medium |
| [Task 3: State Machine](tasks/task-03-state.md) | `src/state.py` | `writing-python-code`, `testing-python` | small |

> **Note:** Task 2b (Platform Layer) should be completed before Task 2 (Config), since Config depends on `UserDirectories` from the platform layer. Task 3 can run in parallel with either.

### Phase 3: Domain Services (parallel after Phase 2)
| Task | File | Skills | Est. |
|------|------|--------|------|
| [Task 4: History](tasks/task-04-history.md) | `src/history.py` | `writing-python-code`, `testing-python` | small |
| [Task 5: Audio Devices](tasks/task-05-devices.md) | `src/audio/devices.py`, `src/audio/device_wrapper.py` | `writing-python-code`, `testing-python` | small |
| [Task 7: Audio Processor](tasks/task-07-processor.md) | `src/audio/processor.py` | `writing-python-code`, `testing-python` | medium |
| [Task 8: Transcription Provider](tasks/task-08-transcription.md) | `src/transcription/provider.py`, `src/transcription/openai_provider.py` | `writing-python-code`, `testing-python` | medium |

### Phase 4: Audio Recorder (after Task 5)
| Task | File | Skills | Est. |
|------|------|--------|------|
| [Task 6: Audio Recorder](tasks/task-06-recorder.md) | `src/audio/recorder.py` | `writing-python-code`, `building-qt-apps`, `testing-python` | large |

### Phase 5: Presentation (parallel, after Phase 3+4)
| Task | File | Skills | Est. |
|------|------|--------|------|
| [Task 9a: App Shell + Tray](tasks/task-09a-app-shell.md) | `src/ui/app.py`, `src/ui/styles.py` | `building-qt-apps`, `writing-python-code` | small |
| [Task 9b: Main Window](tasks/task-09b-main-window.md) | `src/ui/main_window.py`, `src/ui/widgets.py` | `building-qt-apps`, `writing-python-code` | large |
| [Task 9c: Settings Dialog](tasks/task-09c-settings.md) | `src/ui/settings_dialog.py` | `building-qt-apps`, `writing-python-code` | small |
| [Task 11: IPC](tasks/task-11-ipc.md) | `src/ipc.py`, `src/platform/linux.py` (transport) | `writing-python-code`, `testing-python` | medium |

### Phase 6: CLI (after Tasks 8 + 11)
| Task | File | Skills | Est. |
|------|------|--------|------|
| [Task 10: CLI](tasks/task-10-cli.md) | `src/cli.py`, `src/__main__.py` | `writing-python-code`, `building-multi-ui-apps`, `testing-python` | medium |

### Phase 7: Integration (after ALL previous)
| Task | File | Skills | Est. |
|------|------|--------|------|
| [Task 12: Startup Integration](tasks/task-12-startup.md) | `src/ui/app.py` (update), `src/__main__.py` (update) | `building-qt-apps`, `building-multi-ui-apps`, `setting-up-logging`, `writing-python-code`, `testing-python` | large |

### Phase 8: E2E Testing (after ALL previous, requires VM)
| Task | File | Skills | Est. |
|------|------|--------|------|
| [Task 13: E2E Tests](tasks/task-13-e2e-tests.md) | `tests/e2e/` | `qt-app-interaction`, `qt-desktop-integration`, `qt-dev-tools-setup`, `testing-python` | large |

---

## Technical Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| qasync untested on Python 3.14 | HIGH | Test early; have fallback plan (asyncslot/qtinter). qasync last release Aug 2024. VALIDATED on system -- qasync 0.28.0 + PySide6 6.10.1 + Python 3.13 works. Python 3.14 untested. |
| noisereduce + NumPy 2.x | LOW | VALIDATED -- works with numpy 2.4.1, 0.4s for 60s audio. |
| sounddevice + PipeWire | MEDIUM | VALIDATED on Fedora 43 / PipeWire 1.4.11, 16kHz recording works perfectly. Handle empty device list gracefully. |
| XDG_RUNTIME_DIR missing | MEDIUM | Fixed -- falls back to `tempfile.gettempdir()` in constants.py. |
| Python 3.14 ecosystem | MEDIUM | Target 3.13 primarily. Test 3.14 in CI. Pin `requires-python = ">=3.12"`. |
| IPC sockets | LOW | VALIDATED -- XDG_RUNTIME_DIR exists, concurrent clients work, stale socket detection works. |

## Prototype Validation Results

All critical integrations were prototyped and validated on the target system (Fedora 43, Python 3.13, PipeWire 1.4.11):

| Component | Status | Key Learning |
|-----------|--------|-------------|
| sounddevice + qasync + PySide6 | Validated | callback+Queue pattern works. 16kHz through PipeWire is fine. soundcard is broken -- use sounddevice. |
| OpenAI SDK + base_url mocking | Validated | `create()` returns wide union -- needs isinstance narrowing. `json` format lacks duration/language. |
| noisereduce + numpy 2.4.1 | Validated | 0.4s for 60s audio. No numpy 2.x issues. |
| Unix domain socket IPC | Validated | Concurrent clients work. Socket auto-cleans on close. XDG_RUNTIME_DIR exists at /run/user/1000. |

## Deferred to Post-v1 (YAGNI)

- Silence/short recording warnings (warn <1s or silent audio)
- Window position persistence (save/restore geometry via QSettings)
- Recovered PCM → history entry + toast notification
- `show-window` IPC command for single-instance bring-to-front
- Mic disconnect mid-recording (PortAudioError handling in write loop)
- Concurrent IPC client connections test
- API timeout CLI test
- Chunk at silence boundaries (current: chunk by size)
- Serial chunk transcription + concatenation pipeline
