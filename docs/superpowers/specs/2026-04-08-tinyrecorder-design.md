# TinyRecorder — Design Specification

## Overview

Compact PySide6 system tray speech-to-text app for Linux with CLI interface. Uses OpenAI Whisper API (remote) for transcription. Designed for daily-driver reliability: crash-safe recording, automatic retry, persistent history, and clean error recovery.

## Architecture & File Structure

Multi-file Python project. Layered architecture: UI → Domain → Utilities. Dependencies flow downward only. UI is swappable (QWidgets now, QML later).

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
│   ├── history.py              # JSONL history read/write, entry dataclass
│   │
│   ├── platform/
│   │   ├── __init__.py         # PlatformSpecific marker, factory functions: get_user_directories(), get_ipc_server(), etc.
│   │   ├── protocols.py        # UserDirectories, IpcTransport, IpcTransportServer, InstanceLock, PlatformEnv, FfmpegProvider protocols
│   │   └── linux.py            # All Linux implementations: LinuxUserDirectories, UnixSocketIpcTransport, SocketInstanceLock, etc.
│   │
│   ├── audio/
│   │   ├── recorder.py         # sounddevice wrapper + async recording via callback+Queue
│   │   ├── processor.py        # Noise reduction, format conversion, compression
│   │   ├── devices.py          # Mic enumeration, device selection
│   │   └── device_wrapper.py   # AudioDeviceWrapper around sounddevice (library abstraction, not platform-specific)
│   │
│   ├── transcription/
│   │   ├── provider.py         # Protocol (abstract interface) for any STT provider
│   │   └── openai_provider.py  # OpenAI API: whisper-1, gpt-4o-transcribe, gpt-4o-mini-transcribe
│   │
│   └── ui/
│       ├── app.py              # QApplication + qasync setup, tray icon, IPC server start
│       ├── main_window.py      # Main window: record button, result area, controls
│       ├── widgets.py          # VU meter widget, transcript display, history panel
│       └── styles.py           # Stylesheet / theming constants
│
├── tests/
└── docs/
    └── superpowers/specs/
```

Layer rules:

- `ui/` imports from everything else, never imported by anything else
- `cli.py` imports from `transcription/`, `config`, `ipc` (for remote commands)
- `audio/`, `transcription/` import only from `config`, `constants`, each other
- No circular dependencies

## Platform Abstraction

The app targets Linux now but is structured for future Windows/macOS support via a platform abstraction layer.

### PlatformSpecific Marker

Every platform-specific implementation class carries a `PlatformSpecific` marker with a `for_platform: Literal["Linux", "Windows", "MacOS"]` field. This makes it explicit which platform each implementation targets.

### Platform-Specific Subsystems (Protocol + Implementations)

Five subsystems define a Protocol in `platform/protocols.py` with platform-specific implementations in `platform/linux.py`:

- **`UserDirectories` protocol** — provides config_dir, cache_dir, data_dir, downloads_dir paths. `LinuxUserDirectories` uses XDG env vars (`XDG_CONFIG_HOME`, `XDG_CACHE_HOME`, `XDG_DATA_HOME`) with standard fallbacks.
- **`IpcTransport` + `IpcTransportServer` protocols** — the transport layer for IPC (how bytes move between processes). `UnixSocketIpcTransport` / `UnixSocketIpcTransportServer` implement Unix domain socket transport. The protocol-agnostic IPC logic (JSON serialization, command types, dispatch) stays in `ipc.py`.
- **`InstanceLock` protocol** — single-instance enforcement. `SocketInstanceLock` uses the IPC socket connection as the lock mechanism (try connecting to existing socket; if connects, another instance is running).
- **`PlatformEnv` protocol** — platform-specific environment setup at startup. `LinuxPlatformEnv` sets `QT_QPA_PLATFORMTHEME=xdgdesktopportal` if not already set, and any other Linux-specific tweaks.
- **`FfmpegProvider` protocol** — ffmpeg detection and invocation. `LinuxFfmpegProvider` uses `shutil.which("ffmpeg")` for detection and `asyncio.create_subprocess_exec` for invocation. Detection and invocation details differ per platform/distro.

### Non-Platform Abstraction

- **Audio:** `AudioDeviceWrapper` wraps sounddevice for flexibility/swappability. This is a library abstraction wrapper, NOT platform-specific — it exists so the recording layer does not depend directly on the sounddevice API.
- **Clipboard (Qt), signal handling, subprocess** — already cross-platform via Qt/stdlib, no changes needed.

### Factory Functions

`platform/__init__.py` exports factory functions that return the correct implementation for the current platform:

- `get_user_directories() -> UserDirectories`
- `get_ipc_server() -> IpcTransportServer`
- `get_ipc_client() -> IpcTransport`
- `get_instance_lock() -> InstanceLock`
- `get_platform_env() -> PlatformEnv`
- `get_ffmpeg_provider() -> FfmpegProvider`

Currently all return Linux implementations. Future platform support adds implementations + extends the factory functions.

## State Machine

States: IDLE, RECORDING, PROCESSING, SUCCESS, ERROR

Transitions:

- IDLE → RECORDING (user presses record or IPC record-toggle)
- IDLE → PROCESSING (file import — skips recording)
- RECORDING → PROCESSING (user stops recording)
- RECORDING → IDLE (user cancels — audio file preserved in cache)
- PROCESSING → SUCCESS (transcription completes)
- PROCESSING → ERROR (transcription fails)
- PROCESSING → IDLE (user cancels during processing)
- SUCCESS → IDLE (user starts new recording)
- SUCCESS → PROCESSING (user retries with same audio)
- ERROR → IDLE (user dismisses)
- ERROR → PROCESSING (user retries with same audio)

Critical invariant: Once recording starts, the audio file is NEVER deleted by state transitions.

State behavior table:

| State | UI shows | Audio file | Allowed actions |
|---|---|---|---|
| IDLE | Record button, history | — | Start recording, load file, browse history |
| RECORDING | Stop button, cancel, VU meter, timer | Writing raw PCM to cache | Stop → PROCESSING, Cancel → IDLE (keeps file) |
| PROCESSING | Spinner, "Transcribing..." | Complete on disk | Cancel → IDLE |
| SUCCESS | Transcript text, Copy/Retry/New buttons | On disk | Copy, Retry → PROCESSING, New → IDLE |
| ERROR | Error message, Retry/New buttons | On disk | Retry → PROCESSING, New → IDLE |

## Data Flow: Record → Transcribe

1. User clicks Record (or IPC record-toggle)
2. State → RECORDING
3. sounddevice callback fires per chunk (~100ms):
   a. Write raw PCM to cache file (crash-safe)
   b. Compute RMS → emit level signal → VU meter updates
4. User clicks Stop
5. State → PROCESSING
6. Convert raw PCM → WAV (write header)
7. If noise_reduction enabled: load WAV → noisereduce.reduce_noise(stationary=False) → save processed copy (original preserved)
8. If file > 20MB and ffmpeg available: compress to MP3 (mono 16kHz 64kbps via pydub)
9. If file > 24MB after compression (or no ffmpeg): chunk at silence boundaries, transcribe chunks serially, concatenate
10. Send to OpenAI provider → await result
    - On 429/500/503: automatic retry with exponential backoff (1s, 2s, 4s — max 3 attempts)
    - Do NOT retry on 400/401/413
11. On success: State → SUCCESS, store result in JSONL history
12. On failure: State → ERROR, show message + retry option
13. If auto_copy enabled: copy transcript to clipboard on SUCCESS

## Data Flow: File Import

1. User clicks "Import file" or runs `tinyrecorder transcribe file.wav`
2. Validate file (exists, readable, supported format via soundfile)
3. Copy to cache dir (preserve original)
4. State → PROCESSING (skip RECORDING)
5. Same pipeline from step 7 above

## Transcription Provider Interface

Protocol-based. Any STT backend implements:

- `transcribe(audio_path, language, model) -> Result[TranscriptionResult, str]`
- `supported_models() -> list[str]`
- `supported_languages() -> list[str]`

TranscriptionResult contains: text, language, duration_sec, model, cost_estimate (USD).

OpenAI implementation supports three models:

- whisper-1 ($0.006/min, verbose_json with timestamps, no streaming)
- gpt-4o-transcribe ($0.006/min, streaming capable, highest quality)
- gpt-4o-mini-transcribe ($0.003/min, streaming capable, cheapest) — DEFAULT

Language: "auto" omits parameter (API auto-detects), "en" and "ru" pass ISO-639-1 code for better accuracy.

Cost estimation: whisper-1 uses duration-based calculation, gpt-4o models use response usage tokens. Accumulated per-session, shown in status bar.

## Audio Recording

Library: sounddevice (bundles PortAudio, no system packages, good asyncio integration).

Recording parameters: 16000 Hz, mono, int16, block size 1600 (100ms chunks).

Async pattern: sounddevice callback → loop.call_soon_threadsafe(queue.put_nowait, chunk) → asyncio Queue → await queue.get() in qasync event loop → write to file + compute RMS.

### Crash Safety

During recording: raw PCM bytes appended to `cache_dir/rec_YYYYMMDD_HHMMSS.pcm`

On clean stop: WAV header prepended (known constants: 16kHz, mono, int16) → renamed to .wav

On crash: .pcm file survives. Next startup scans for orphaned .pcm without matching .wav → recovers by adding WAV header → adds to history as "recovered recording" → shows toast.

### Device Management

Enumerate via sounddevice.query_devices(). Store selected device by NAME in config (not index). On recording start: resolve name → index, fall back to system default if not found. On mid-recording disconnect: catch PortAudioError → stop, save partial → ERROR state.

## Noise Reduction

Library: noisereduce (hard dependency, pure pip). Toggle in config.

Applied post-recording, pre-upload. Original WAV never modified — processed version is a temp file. Uses `noisereduce.reduce_noise(stationary=False)` with default parameters.

## Compression

Optional ffmpeg dependency via pydub. Detected dynamically at runtime via `FfmpegProvider` protocol (detection and invocation details are platform-specific).

If ffmpeg available and file > 20MB: compress to MP3 (mono 16kHz 64kbps).
If ffmpeg not available: skip compression, chunk large WAVs instead.
One-time info toast if file would benefit: "Install ffmpeg for better audio compression."

## UI Layout

Single window, ~400x550px default, ~350x450px minimum. System tray lifecycle.

Four zones stacked vertically:

### Top Bar

Mic selector dropdown, language selector (Auto/English/Russian), model selector, settings gear icon.

### Recording Zone

VU meter (horizontal bar, RMS-driven). Large record button: "● REC" in IDLE, "■ STOP" in RECORDING. Timer (MM:SS) during recording. Cancel button below during recording.

### Transcript Zone

Read-only scrollable text area. Takes all extra vertical space (only resizable zone). Shows transcript on SUCCESS, error message on ERROR, placeholder in IDLE.

### Action Bar

Copy button, Retry button, Import button, History dropdown. Buttons enabled/disabled based on state.

### Status Bar

Current state indicator. Session usage estimate ($).

### Settings Dialog

Separate small dialog: API key (masked), auto-copy toggle, noise reduction toggle, cache dir path, usage stats.

### History Panel

Dropdown from action bar. Scrollable list of recent transcriptions: timestamp, first ~50 chars, duration. Click loads transcript + enables retry from cached audio.

### Window Behavior

System tray app. Tray icon click toggles window visibility. Close button hides to tray. Quit via tray menu or CLI. Window position remembered between sessions.

## IPC

Two-layer architecture:

1. **Transport layer** (platform-specific): how bytes move between processes. Defined by `IpcTransport`/`IpcTransportServer` protocols in `platform/protocols.py`. Linux implementation uses a Unix domain socket at `/run/user/$UID/tinyrecorder.sock` (`UnixSocketIpcTransport`/`UnixSocketIpcTransportServer` in `platform/linux.py`).
2. **Protocol layer** (platform-agnostic): what messages look like. Lives in `ipc.py`. Newline-delimited JSON serialization, command types, response types, command dispatch.

Message format (handled by `ipc.py`):

- CLI → GUI: `{"command": "record-toggle"}` / `{"command": "record-cancel"}` / `{"command": "status"}` / `{"command": "show-window"}`
- GUI → CLI: `{"status": "ok", "state": "recording"}` etc.

Single-instance lock: handled by `InstanceLock` protocol (see Platform Abstraction). `SocketInstanceLock` uses the IPC transport connection as the lock mechanism — try connecting to existing socket; if connects → send show-window → exit. If no socket → start server.

Stale socket: if socket file exists but connection refused → remove and start fresh (handled by the transport layer).

## CLI

Entry point: `tinyrecorder`

```
tinyrecorder                              # Default: launch GUI
tinyrecorder transcribe FILE              # Standalone: transcribe file, print to stdout
    --lang auto|en|ru
    --model gpt-4o-mini-transcribe|gpt-4o-transcribe|whisper-1
    --no-noise-reduction
tinyrecorder record-toggle                # IPC → running GUI: toggle recording
tinyrecorder record-cancel                # IPC → running GUI: cancel recording
tinyrecorder status                       # IPC → print current state JSON
tinyrecorder --help / -h                  # CLI help
```

`transcribe` is fully standalone — loads config for API key, sends to provider, prints result to stdout, exits. Composable: `tinyrecorder transcribe meeting.wav | xclip`

## Config

TOML config file. Path provided by `UserDirectories.config_dir / "config.toml"` (on Linux: `~/.config/tinyrecorder/config.toml` via XDG).

```toml
[api]
key = "sk-..."
model = "gpt-4o-mini-transcribe"

[recording]
language = "auto"
noise_reduction = false
sample_rate = 16000
device = ""  # empty = system default

[app]
auto_copy = true
```

Created with defaults on first launch (API key empty → settings dialog opens).

## History

JSONL file. Path provided by `UserDirectories.data_dir / "history.jsonl"` (on Linux: `~/.local/share/tinyrecorder/history.jsonl` via XDG).

Each line:

```json
{"timestamp": "2026-04-08T12:30:00Z", "audio_file": "rec_20260408_123000.wav", "transcript": "Hello world", "language": "en", "model": "gpt-4o-mini-transcribe", "duration_sec": 12.5, "noise_reduction": false}
```

Audio files stored in cache dir: `UserDirectories.cache_dir / "audio/"` (on Linux: `~/.cache/tinyrecorder/audio/` via XDG).
Audio file paths in JSONL are relative to the cache audio dir.

## Startup Sequence

1. Parse CLI args (typer)
2. If subcommand (transcribe/record-toggle/cancel/status): handle and exit
3. Otherwise: launch GUI
4. Initialize platform layer via factory functions: `get_user_directories()`, `get_platform_env()`, `get_instance_lock()`, `get_ipc_server()`, `get_ffmpeg_provider()`
5. Apply platform environment (`PlatformEnv.apply()` — e.g., set QT_QPA_PLATFORMTHEME on Linux)
6. Check for existing instance via `InstanceLock` → if running instance found, send show-window, exit
7. Load config from `UserDirectories.config_dir` (create default if missing, validate)
8. If no API key: open settings dialog immediately
9. Scan `UserDirectories.cache_dir` for orphaned .pcm files → recover to .wav, add to history, show toast
10. Start IPC server via platform transport layer (async)
11. Create QApplication + qasync loop
12. Set up signal handling (Ctrl+C → QApplication.quit with cleanup)
13. Create system tray icon + main window (hidden)
14. Show tray icon
15. Run event loop

Quick startup: no heavy imports at module level. openai, sounddevice, noisereduce imported lazily on first use.

## Error Handling

Three-layer boundary pattern:

- Layer 1 (Library): every third-party call wrapped in try/except → Result[T, str]
- Layer 2 (Component): each module returns Result to caller with context
- Layer 3 (Top-level): GUI catches everything → toast/status bar. CLI → stderr + exit 1. Async tasks → try/except safety net → ERROR state.

### Edge Cases

| Scenario | Handling |
|---|---|
| No API key | Settings dialog opens on first launch. Record/Transcribe disabled. |
| Invalid API key (401) | ERROR state: "Invalid API key. Check Settings." |
| No microphone | Record button disabled, tooltip: "No microphone detected" |
| Mic disconnects mid-recording | Catch PortAudioError → save partial → ERROR: "Mic disconnected. Partial recording saved." |
| Network down | Retry 3x → ERROR: "Network error. Recording saved — retry when online." |
| Rate limited (429) | Auto retry with backoff. After 3 fails → ERROR: "Rate limited. Try again in a minute." |
| File too large | Compress (if ffmpeg) → chunk → if still fails → ERROR: "File too large." |
| Corrupt imported file | Validate with soundfile → ERROR: "Cannot read file: unsupported format" |
| Cache dir not writable | Fatal error dialog on startup |
| Config corrupt | Reset to defaults, show toast |
| Orphaned .pcm on startup | Recover silently, show toast |
| Empty/silent recording | RMS check after stop → warn: "Recording appears silent. Transcribe anyway?" |
| Very short recording (<1s) | Warn: "Recording very short. Transcribe anyway?" |

### Not in Scope (YAGNI)

- Streaming/live transcription (architecture supports later)
- Multiple simultaneous recordings
- Audio playback
- Transcript editing
- Multi-provider simultaneous comparison
- Offline mode / queuing
- Cache cleanup (deferred feature)

## Dependencies

Core:

- PySide6 — Qt GUI
- qasync — Qt + asyncio bridge
- sounddevice — audio recording (bundles PortAudio)
- soundfile — audio file reading/validation/format info
- numpy — audio processing
- scipy — signal processing (noisereduce dependency, also useful for resampling)
- noisereduce — noise reduction
- openai — API client
- httpx — HTTP (openai dep, also useful standalone)
- typer — CLI
- rusty-results — Result[T, E] pattern
- tomli / tomli-w — TOML config

Optional (pip):

- pydub — audio compression/chunking (requires ffmpeg at runtime)

Optional system:

- ffmpeg — audio compression backend for pydub (graceful degradation if missing)

Dev:

- basedpyright (strict, no Any)
- ruff
- pytest, pytest-qt, pytest-asyncio

## Coding Standards

Per project skills:

- basedpyright strict mode, reportAny = error
- Result-based error handling (rusty-results), not exceptions for expected failures
- Typed wrappers around third-party libraries
- Google-style docstrings on public APIs
- 120 char line length, double quotes
- Commit format: type(scope): subject
