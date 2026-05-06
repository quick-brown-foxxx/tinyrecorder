# TinyRecorder v0.0.1 Test Cases

Philosophy: preserve the app's core DNA with the fewest high-value tests. Favor real files and real serialization over UI-heavy checks.

## Critical

- `test_state_machine_accepts_documented_transitions`
  Verifies the simplified one-file state machine still allows the documented happy-path transitions and preserves the active audio path.

- `test_state_machine_rejects_invalid_transition`
  Verifies invalid jumps are rejected without mutating current state.

- `test_config_create_load_save_round_trip`
  Verifies first-run config creation, TOML persistence, and reload of edited values.

- `test_convert_pcm_to_wav_creates_valid_audio_file`
  Verifies crash-safe PCM recording can be recovered into a valid WAV with the expected audio settings.

- `test_history_append_and_load_round_trip`
  Verifies transcripts are persisted to JSONL history and can be loaded back in reverse-chronological order.

## Medium

- `test_build_wav_header_contains_expected_markers`
  Verifies the manual WAV header builder emits a valid PCM header.

- `test_load_config_repairs_corrupt_file`
  Verifies a broken config file is replaced with defaults instead of crashing startup.

## Skipped For v0.0.1

- UI layout smoke tests
- System tray interaction tests
- Live microphone capture tests
- Real OpenAI API integration tests
- IPC and CLI tests
- Noise reduction and compression tests
