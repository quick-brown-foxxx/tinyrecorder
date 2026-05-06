# TinyRecorder Test Cases

Philosophy: Trustworthiness > coverage. Real over mocked. 5 good e2e tests > 100 unit tests with mocking.

**No unittest.mock.patch for OpenAI SDK.** Use `pytest-httpserver` to create a real HTTP server that mimics the OpenAI API. The provider accepts a `base_url` parameter for testing.

## Test Layers

| Layer | Tool | Where | Runs by default |
|-------|------|-------|----------------|
| Unit | pytest | `tests/unit/` | Yes |
| Integration | pytest + httpserver | `tests/integration/` | Yes |
| UI Smoke | pytest-qt | `tests/unit/test_*.py` | Yes |
| **E2E** | **qt-ai-dev-tools VM** | **`tests/e2e/`** | **No** (`-m e2e`) |

E2E tests require `uvx qt-ai-dev-tools vm up`. Run explicitly: `uv run pytest -m e2e -n0`

---

## 1. CLI / E2E Tests (highest priority)

### test_cli_transcribe_file_success

- **Verifies:** `tinyrecorder transcribe FILE` sends audio to the API and prints transcript to stdout.
- **Priority:** critical
- **Category:** e2e
- **Key assertions:**
  - Exit code 0
  - stdout contains the transcript text returned by the mock server
  - Mock server received exactly one POST request to `/v1/audio/transcriptions`
  - Request contained the audio file as multipart form data
- **Fixtures:** pytest-httpserver mimicking OpenAI `/v1/audio/transcriptions`, tmp dir with config.toml (API key set, base_url pointing to mock), sample WAV file (real, short silence or tone)

### test_cli_transcribe_missing_api_key

- **Verifies:** `tinyrecorder transcribe FILE` fails gracefully when no API key is configured.
- **Priority:** critical
- **Category:** e2e
- **Key assertions:**
  - Exit code non-zero
  - stderr contains a message about missing API key
  - No HTTP request sent to any server
- **Fixtures:** tmp dir with config.toml (empty API key), sample WAV file

### test_cli_transcribe_invalid_file

- **Verifies:** `tinyrecorder transcribe nonexistent.wav` fails with a clear error.
- **Priority:** medium
- **Category:** e2e
- **Key assertions:**
  - Exit code non-zero
  - stderr mentions file not found or unreadable
- **Fixtures:** tmp dir with config.toml

### test_cli_transcribe_corrupt_file

- **Verifies:** `tinyrecorder transcribe FILE` rejects a file that is not valid audio.
- **Priority:** medium
- **Category:** e2e
- **Key assertions:**
  - Exit code non-zero
  - stderr mentions unsupported format or corrupt file
- **Fixtures:** tmp dir with config.toml, a file containing random bytes (not valid audio)

### test_cli_transcribe_api_error_401

- **Verifies:** `tinyrecorder transcribe FILE` reports invalid API key when server returns 401.
- **Priority:** critical
- **Category:** e2e
- **Key assertions:**
  - Exit code non-zero
  - stderr contains message about invalid API key
  - No retry attempted (only one request to mock server)
- **Fixtures:** pytest-httpserver returning 401, tmp config, sample WAV

### test_cli_transcribe_api_error_429_retry

- **Verifies:** `tinyrecorder transcribe FILE` retries on 429, succeeds on subsequent attempt.
- **Priority:** critical
- **Category:** e2e
- **Key assertions:**
  - Exit code 0
  - stdout contains the transcript
  - Mock server received exactly 2 requests (first 429, second 200)
- **Fixtures:** pytest-httpserver returning 429 on first request then 200 with transcript on second, tmp config, sample WAV

### test_cli_transcribe_language_and_model_flags

- **Verifies:** `--lang` and `--model` flags are forwarded to the API request.
- **Priority:** medium
- **Category:** e2e
- **Key assertions:**
  - Mock server request form data includes `language=en` and `model=whisper-1`
- **Fixtures:** pytest-httpserver, tmp config, sample WAV

### test_cli_status_no_running_instance

- **Verifies:** `tinyrecorder status` fails gracefully when no GUI instance is running.
- **Priority:** medium
- **Category:** e2e
- **Key assertions:**
  - Exit code non-zero
  - stderr mentions no running instance or connection refused
- **Fixtures:** None (ensure no socket exists at expected path)

### test_cli_record_toggle_no_running_instance

- **Verifies:** `tinyrecorder record-toggle` fails gracefully when no GUI instance is running.
- **Priority:** medium
- **Category:** e2e
- **Key assertions:**
  - Exit code non-zero
  - stderr mentions no running instance
- **Fixtures:** None

---

## 2. Integration Tests

### test_state_machine_valid_transitions

- **Verifies:** All valid state transitions from the spec are accepted.
- **Priority:** critical
- **Category:** integration
- **Key assertions:**
  - IDLE -> RECORDING succeeds
  - RECORDING -> PROCESSING succeeds
  - RECORDING -> IDLE succeeds
  - PROCESSING -> SUCCESS succeeds
  - PROCESSING -> ERROR succeeds
  - SUCCESS -> IDLE succeeds
  - SUCCESS -> PROCESSING succeeds
  - ERROR -> IDLE succeeds
  - ERROR -> PROCESSING succeeds
  - State is updated after each transition
- **Fixtures:** None

### test_state_machine_invalid_transitions

- **Verifies:** Invalid state transitions are rejected.
- **Priority:** critical
- **Category:** integration
- **Key assertions:**
  - IDLE -> SUCCESS raises error / returns Err
  - IDLE -> ERROR raises error / returns Err
  - RECORDING -> SUCCESS raises error / returns Err
  - RECORDING -> ERROR raises error / returns Err
  - PROCESSING -> RECORDING raises error / returns Err
  - SUCCESS -> RECORDING raises error / returns Err
  - SUCCESS -> ERROR raises error / returns Err
  - ERROR -> RECORDING raises error / returns Err
  - ERROR -> SUCCESS raises error / returns Err
  - State remains unchanged after rejected transition
- **Fixtures:** None

### test_recording_pipeline_pcm_to_wav

- **Verifies:** Raw PCM data is correctly converted to a valid WAV file with correct header.
- **Priority:** critical
- **Category:** integration
- **Key assertions:**
  - Output file has .wav extension
  - WAV header specifies: 16000 Hz, mono, 16-bit PCM
  - File is readable by soundfile/wave module
  - Audio data matches the original PCM bytes
- **Fixtures:** tmp dir, synthetic PCM data (known sine wave or silence as int16 bytes)

### test_transcription_provider_success

- **Verifies:** OpenAI provider sends correct request and parses successful response.
- **Priority:** critical
- **Category:** integration
- **Key assertions:**
  - Provider returns Ok(TranscriptionResult)
  - Result contains transcript text, model, duration
  - Cost estimate is a positive number
  - HTTP request was POST to `/v1/audio/transcriptions` with correct multipart fields
- **Fixtures:** pytest-httpserver mimicking OpenAI API, sample WAV file, tmp dir

### test_transcription_provider_retry_on_server_error

- **Verifies:** Provider retries on 500/503 with exponential backoff, up to 3 attempts.
- **Priority:** critical
- **Category:** integration
- **Key assertions:**
  - After 3 consecutive 500s, provider returns Err with retry-exhausted message
  - Mock server received exactly 3 requests
- **Fixtures:** pytest-httpserver returning 500 on all requests, sample WAV

### test_transcription_provider_no_retry_on_400

- **Verifies:** Provider does NOT retry on 400 (bad request) errors.
- **Priority:** medium
- **Category:** integration
- **Key assertions:**
  - Provider returns Err immediately
  - Mock server received exactly 1 request
- **Fixtures:** pytest-httpserver returning 400, sample WAV

### test_history_write_and_read_back

- **Verifies:** A history entry written to JSONL can be read back with all fields intact.
- **Priority:** critical
- **Category:** integration
- **Key assertions:**
  - Written file is valid JSONL (one JSON object per line)
  - Read-back entry matches original: timestamp, audio_file, transcript, language, model, duration_sec, noise_reduction
  - Multiple entries append correctly (file has N lines after N writes)
- **Fixtures:** tmp dir for history file

### test_history_handles_corrupt_lines

- **Verifies:** History reader skips malformed JSONL lines without crashing.
- **Priority:** medium
- **Category:** integration
- **Key assertions:**
  - File with mix of valid and invalid JSON lines returns only valid entries
  - No exception raised
- **Fixtures:** tmp dir with pre-written JSONL containing corrupt lines

### test_ipc_round_trip

- **Verifies:** IPC server and client can exchange a command and response over Unix socket.
- **Priority:** critical
- **Category:** integration
- **Key assertions:**
  - Client sends `{"command": "status"}`, server receives it
  - Server responds with `{"status": "ok", "state": "idle"}`, client receives it
  - Communication is newline-delimited JSON
- **Fixtures:** tmp dir for socket file

### test_ipc_stale_socket_cleanup

- **Verifies:** A stale socket file (no server listening) is cleaned up on new server start.
- **Priority:** medium
- **Category:** integration
- **Key assertions:**
  - Create a socket file with no listener
  - New server start succeeds (removes stale, binds new)
  - Client can connect to the new server
- **Fixtures:** tmp dir for socket file

### test_config_create_defaults

- **Verifies:** Config module creates a default config file when none exists.
- **Priority:** critical
- **Category:** integration
- **Key assertions:**
  - Config file is created at expected path
  - File is valid TOML
  - Contains all expected sections: api, recording, app
  - Default values match spec: model = "gpt-4o-mini-transcribe", language = "auto", auto_copy = true, noise_reduction = false
- **Fixtures:** tmp dir (empty, no config file)

### test_config_load_modify_save_reload

- **Verifies:** Config can be loaded, modified, saved, and reloaded with changes preserved.
- **Priority:** medium
- **Category:** integration
- **Key assertions:**
  - Load config, change model to "whisper-1", save
  - Reload from disk, model is "whisper-1"
  - Other fields unchanged
- **Fixtures:** tmp dir with default config

### test_config_corrupt_resets_to_defaults

- **Verifies:** A corrupt config file is replaced with defaults and a warning is produced.
- **Priority:** medium
- **Category:** integration
- **Key assertions:**
  - Write invalid TOML to config path
  - Load config succeeds (returns defaults)
  - Config file on disk is now valid
- **Fixtures:** tmp dir with garbage in config file

### test_crash_recovery_orphaned_pcm

- **Verifies:** Orphaned .pcm files in cache are recovered to .wav on startup scan.
- **Priority:** critical
- **Category:** integration
- **Key assertions:**
  - Place a .pcm file (valid raw PCM: 16kHz mono int16) in cache dir with no matching .wav
  - Run recovery scan
  - A .wav file now exists with correct WAV header
  - WAV is readable by soundfile/wave
  - History contains a "recovered recording" entry
- **Fixtures:** tmp dir with orphaned .pcm file containing valid PCM data

---

## 3. Unit Tests (pure logic only)

### test_rms_calculation

- **Verifies:** RMS is correctly computed from a known audio buffer.
- **Priority:** medium
- **Category:** unit
- **Key assertions:**
  - Silence (all zeros) -> RMS = 0
  - Full-scale sine wave -> RMS approximately 0.707 * amplitude
  - Known fixed buffer -> exact expected RMS value
- **Fixtures:** None (numpy arrays)

### test_rms_to_db_conversion

- **Verifies:** RMS-to-dB conversion produces correct values.
- **Priority:** medium
- **Category:** unit
- **Key assertions:**
  - RMS = 1.0 -> 0 dB
  - RMS = 0.0 -> -inf or clamped minimum
  - RMS = 0.5 -> approximately -6.02 dB
- **Fixtures:** None

### test_wav_header_construction

- **Verifies:** WAV header bytes are correct for 16kHz mono int16 format.
- **Priority:** critical
- **Category:** unit
- **Key assertions:**
  - Header starts with b"RIFF"
  - Contains b"WAVE" and b"fmt " chunks
  - Sample rate field = 16000
  - Bits per sample = 16
  - Num channels = 1
  - Data chunk size matches payload length
  - Total file size in header = data size + 36
- **Fixtures:** None

### test_cost_estimation_whisper

- **Verifies:** Cost estimation for whisper-1 is duration-based at $0.006/min.
- **Priority:** medium
- **Category:** unit
- **Key assertions:**
  - 60 seconds -> $0.006
  - 30 seconds -> $0.003
  - 0 seconds -> $0.0
- **Fixtures:** None

### test_cost_estimation_gpt4o_models

- **Verifies:** Cost estimation for gpt-4o models uses token-based calculation.
- **Priority:** medium
- **Category:** unit
- **Key assertions:**
  - Known token count -> expected cost
  - gpt-4o-mini-transcribe costs half of gpt-4o-transcribe for same tokens
- **Fixtures:** None

### test_config_dataclass_validation

- **Verifies:** Config dataclass rejects invalid values.
- **Priority:** medium
- **Category:** unit
- **Key assertions:**
  - Invalid model name is rejected or normalized
  - Invalid language code is rejected
  - Sample rate must be positive integer
- **Fixtures:** None

### test_history_entry_serialization

- **Verifies:** History entry serializes to JSON and deserializes back identically.
- **Priority:** medium
- **Category:** unit
- **Key assertions:**
  - Round-trip: entry -> JSON string -> entry produces equal object
  - Timestamp format is ISO 8601
  - All fields present in JSON output
- **Fixtures:** None

### test_state_transition_validation_function

- **Verifies:** The transition validator correctly identifies valid and invalid transitions.
- **Priority:** medium
- **Category:** unit
- **Key assertions:**
  - is_valid_transition(IDLE, RECORDING) -> True
  - is_valid_transition(IDLE, SUCCESS) -> False
  - Covers all 25 combinations (5x5 matrix)
- **Fixtures:** None

---

## 5. Platform Layer Tests

### test_user_directories_xdg_defaults
- **Verifies:** LinuxUserDirectories returns correct XDG-based paths when env vars are not set.
- **Priority:** critical
- **Category:** unit
- **Key assertions:**
  - config_dir ends with `.config/tinyrecorder`
  - cache_dir ends with `.cache/tinyrecorder`
  - data_dir ends with `.local/share/tinyrecorder`
- **Fixtures:** Clean environment (XDG vars unset)

### test_user_directories_xdg_env_override
- **Verifies:** LinuxUserDirectories respects XDG environment variables.
- **Priority:** medium
- **Category:** unit
- **Key assertions:**
  - Setting XDG_CONFIG_HOME changes config_dir
  - Setting XDG_CACHE_HOME changes cache_dir
  - Setting XDG_DATA_HOME changes data_dir
- **Fixtures:** monkeypatched environment variables

### test_ffmpeg_provider_detection
- **Verifies:** LinuxFfmpegProvider correctly detects ffmpeg availability.
- **Priority:** medium
- **Category:** unit
- **Key assertions:**
  - Returns True when ffmpeg is in PATH
  - Returns False when ffmpeg is not in PATH
- **Fixtures:** monkeypatched shutil.which

### test_platform_env_sets_theme
- **Verifies:** LinuxPlatformEnv sets QT_QPA_PLATFORMTHEME if not already set.
- **Priority:** medium
- **Category:** unit
- **Key assertions:**
  - Sets xdgdesktopportal when env var is unset
  - Does NOT override when env var is already set
- **Fixtures:** monkeypatched environment

### test_factory_functions_return_linux
- **Verifies:** All platform factory functions return Linux implementations on Linux.
- **Priority:** medium
- **Category:** unit
- **Key assertions:**
  - get_user_directories() returns LinuxUserDirectories
  - get_ffmpeg_provider() returns LinuxFfmpegProvider
  - get_platform_env() returns LinuxPlatformEnv
- **Fixtures:** None (runs on Linux)

---

## 4. What NOT to test

- UI layout and widget rendering (QWidget, QLabel, etc.)
- Stylesheet constants and theming values
- Trivial getters/setters
- sounddevice hardware interaction (requires real mic)
- System tray icon behavior
- Window position save/restore
- noisereduce output quality (third-party algorithm)

---

## Shared Fixtures Summary

| Fixture | Used by | Description |
|---|---|---|
| `mock_openai_server` | e2e transcribe tests, integration provider tests | pytest-httpserver configured with `/v1/audio/transcriptions` endpoint. Returns configurable responses. Provider `base_url` points here. |
| `sample_wav_file` | e2e and integration tests needing audio | Real WAV file: 1 second of 440Hz sine wave, 16kHz mono int16. Created via numpy + wave module in fixture. |
| `sample_pcm_data` | PCM-to-WAV, crash recovery tests | Raw PCM bytes: 1 second of 16kHz mono int16 silence or sine. |
| `corrupt_audio_file` | e2e corrupt file test | File with random bytes, not valid audio. |
| `tmp_config_dir` | All tests needing config | tmp_path with config.toml. Parametrized: with/without API key. `XDG_CONFIG_HOME` pointed here. |
| `tmp_cache_dir` | Recording, crash recovery tests | tmp_path for audio cache. `XDG_CACHE_HOME` pointed here. |
| `tmp_data_dir` | History tests | tmp_path for history.jsonl. `XDG_DATA_HOME` pointed here. |
| `tmp_socket_path` | IPC tests | tmp_path for Unix domain socket. |
