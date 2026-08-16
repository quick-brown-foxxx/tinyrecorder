"""Core behavior tests for the one-file TinyRecorder bootstrap."""

from __future__ import annotations

import os
import sys
import wave
from dataclasses import replace
from pathlib import Path
from typing import cast

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication
from pytest_httpserver import HTTPServer

import tinyrecorder
from tinyrecorder import (
    DEFAULT_LLM_MODEL,
    DEFAULT_LLM_PROMPT,
    AppConfig,
    HistoryEntry,
    LLMPostProcessor,
    MainWindow,
    OpenAITranscriber,
    RecordingState,
    SettingsDialog,
    StateMachine,
    TrayIconState,
    append_history_entry,
    build_cache_audio_name,
    build_llm_url,
    build_transcription_url,
    build_tray_icon_svg,
    build_wav_header,
    can_cancel_current_operation,
    can_postprocess_with_config,
    can_trigger_record_action,
    convert_pcm_to_wav,
    create_application,
    create_default_config,
    guess_audio_content_type,
    list_input_devices,
    load_config,
    load_history,
    render_svg_icon,
    resolve_llm_prompt,
    resolve_tray_icon_state,
    save_config,
)


def test_state_machine_accepts_documented_transitions() -> None:
    state = StateMachine()
    audio_path = Path("sample.wav")
    state.audio_file_path = audio_path

    assert state.transition(RecordingState.RECORDING).is_ok
    assert state.transition(RecordingState.PROCESSING).is_ok
    assert state.transition(RecordingState.SUCCESS).is_ok
    assert state.transition(RecordingState.IDLE).is_ok
    assert state.current_state == RecordingState.IDLE
    assert state.audio_file_path == audio_path


def test_state_machine_rejects_invalid_transition() -> None:
    state = StateMachine()

    result = state.transition(RecordingState.SUCCESS)

    assert result.is_err
    assert state.current_state == RecordingState.IDLE


def test_config_create_load_save_round_trip(tmp_path: Path) -> None:
    config_path = tmp_path / "tinyrecorder" / "config.toml"

    created = create_default_config(config_path)
    assert created.is_ok
    assert config_path.exists()

    loaded = load_config(config_path)
    assert loaded.is_ok
    config = replace(
        loaded.unwrap(),
        api_key="sk-test",
        api_base_url="http://127.0.0.1:11434/v1",
        model="whisper-1",
        auto_copy=False,
        llm_enabled=True,
        llm_api_key="sk-llm",
        llm_api_base_url="http://127.0.0.1:11434/v1",
        llm_model="custom-llm",
        llm_reasoning_effort="medium",
        llm_prompt="Add punctuation only.",
    )

    saved = save_config(config, config_path)
    assert saved.is_ok

    reloaded = load_config(config_path)
    assert reloaded.is_ok
    assert reloaded.unwrap() == config


def test_load_config_repairs_missing_api_base_url(tmp_path: Path) -> None:
    config_path = tmp_path / "tinyrecorder" / "config.toml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        """
[api]
key = "sk-test"
model = "whisper-1"

[recording]
language = "auto"
noise_reduction = false
sample_rate = 16000
device = ""

[app]
auto_copy = true
""".strip(),
        encoding="utf-8",
    )

    loaded = load_config(config_path)

    assert loaded.is_ok
    assert loaded.unwrap().api_base_url == "https://api.openai.com/v1"
    assert 'base_url = "https://api.openai.com/v1"' in config_path.read_text(encoding="utf-8")


def test_build_transcription_url_normalizes_trailing_slash() -> None:
    config = AppConfig(api_base_url="http://localhost:11434/v1/")

    assert build_transcription_url(config) == "http://localhost:11434/v1/audio/transcriptions"


def test_build_wav_header_contains_expected_markers() -> None:
    header = build_wav_header(data_size=3200, sample_rate=16000, channels=1, bits_per_sample=16)

    assert header[:4] == b"RIFF"
    assert header[8:12] == b"WAVE"
    assert header[12:16] == b"fmt "
    assert header[36:40] == b"data"
    assert len(header) == 44


def test_convert_pcm_to_wav_creates_valid_audio_file(tmp_path: Path) -> None:
    pcm_path = tmp_path / "recording.pcm"
    samples = np.zeros(16000, dtype=np.int16)
    pcm_path.write_bytes(samples.tobytes())

    wav_path = convert_pcm_to_wav(pcm_path, sample_rate=16000, channels=1, bits_per_sample=16)

    assert wav_path.exists()
    with wave.open(str(wav_path), "rb") as wav_file:
        assert wav_file.getframerate() == 16000
        assert wav_file.getnchannels() == 1
        assert wav_file.getsampwidth() == 2
        assert wav_file.getnframes() == 16000


def test_build_cache_audio_name_is_unique_per_timestamp() -> None:
    first = build_cache_audio_name("import", ".wav", now_ns=1_700_000_000_000_000_001)
    second = build_cache_audio_name("import", ".wav", now_ns=1_700_000_000_000_000_002)

    assert first != second
    assert first.endswith(".wav")


def test_resolve_app_paths_uses_windows_roaming_and_local_app_data(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    roaming_dir = tmp_path / "Roaming"
    local_dir = tmp_path / "Local"
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(roaming_dir))
    monkeypatch.setenv("LOCALAPPDATA", str(local_dir))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)

    paths = tinyrecorder.resolve_app_paths()

    assert paths.config_dir == roaming_dir / "TinyRecorder"
    assert paths.data_dir == roaming_dir / "TinyRecorder"
    assert paths.cache_dir == local_dir / "TinyRecorder"
    assert paths.audio_dir == local_dir / "TinyRecorder" / "audio"


def test_configure_platform_environment_only_sets_xdg_portal_on_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.delenv("QT_QPA_PLATFORMTHEME", raising=False)

    tinyrecorder.configure_platform_environment()

    assert "QT_QPA_PLATFORMTHEME" not in os.environ

    monkeypatch.setattr(sys, "platform", "linux")

    tinyrecorder.configure_platform_environment()

    assert os.environ["QT_QPA_PLATFORMTHEME"] == "xdgdesktopportal"


def test_guess_audio_content_type_uses_suffix() -> None:
    assert guess_audio_content_type(Path("sample.wav")) == "audio/wav"
    assert guess_audio_content_type(Path("sample.mp3")) == "audio/mpeg"


def test_list_input_devices_accepts_non_list_device_collection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class DeviceListLike:
        def __iter__(self):
            yield {"name": "Mic A", "max_input_channels": 2}
            yield {"name": "Speakers", "max_input_channels": 0}
            yield {"name": "Mic B", "max_input_channels": 1}

    class FakeSoundDevice:
        @staticmethod
        def query_devices() -> DeviceListLike:
            return DeviceListLike()

    monkeypatch.setitem(sys.modules, "sounddevice", FakeSoundDevice())

    result = list_input_devices()

    assert result.is_ok
    assert result.unwrap() == ["Mic A", "Mic B"]


def test_resolve_tray_icon_state_uses_transient_done_feedback() -> None:
    assert resolve_tray_icon_state(RecordingState.IDLE, show_done=False) == TrayIconState.IDLE
    assert resolve_tray_icon_state(RecordingState.RECORDING, show_done=False) == TrayIconState.RECORDING
    assert resolve_tray_icon_state(RecordingState.PROCESSING, show_done=False) == TrayIconState.TRANSCRIBING
    assert resolve_tray_icon_state(RecordingState.ERROR, show_done=False) == TrayIconState.ERROR
    assert resolve_tray_icon_state(RecordingState.SUCCESS, show_done=True) == TrayIconState.DONE
    assert resolve_tray_icon_state(RecordingState.SUCCESS, show_done=False) == TrayIconState.IDLE


def test_can_trigger_record_action_matches_button_policy() -> None:
    assert can_trigger_record_action(RecordingState.IDLE, can_transcribe=True, mic_available=True) is True
    assert can_trigger_record_action(RecordingState.RECORDING, can_transcribe=True, mic_available=True) is True
    assert can_trigger_record_action(RecordingState.SUCCESS, can_transcribe=True, mic_available=True) is True
    assert can_trigger_record_action(RecordingState.ERROR, can_transcribe=True, mic_available=True) is True
    assert can_trigger_record_action(RecordingState.PROCESSING, can_transcribe=True, mic_available=True) is False
    assert can_trigger_record_action(RecordingState.IDLE, can_transcribe=False, mic_available=True) is False
    assert can_trigger_record_action(RecordingState.IDLE, can_transcribe=True, mic_available=False) is False


def test_can_cancel_current_operation_matches_processing_policy() -> None:
    assert can_cancel_current_operation(RecordingState.IDLE) is False
    assert can_cancel_current_operation(RecordingState.RECORDING) is True
    assert can_cancel_current_operation(RecordingState.PROCESSING) is True
    assert can_cancel_current_operation(RecordingState.SUCCESS) is False
    assert can_cancel_current_operation(RecordingState.ERROR) is False


def test_build_tray_icon_svg_varies_by_state() -> None:
    idle_svg = build_tray_icon_svg(state=TrayIconState.IDLE, color="#eff0f1")
    recording_svg = build_tray_icon_svg(state=TrayIconState.RECORDING, color="#eff0f1")
    transcribing_svg = build_tray_icon_svg(state=TrayIconState.TRANSCRIBING, color="#eff0f1")
    error_svg = build_tray_icon_svg(state=TrayIconState.ERROR, color="#da4453")
    done_svg = build_tray_icon_svg(state=TrayIconState.DONE, color="#27ae60")

    assert idle_svg != recording_svg
    assert recording_svg != transcribing_svg
    assert error_svg != done_svg


def test_main_window_shows_cancel_button_while_processing(qapp: QApplication) -> None:
    window = MainWindow()

    window.update_for_state(RecordingState.PROCESSING, can_transcribe=True, mic_available=True)

    assert window.cancel_button.isHidden() is False
    assert window.cancel_button.isEnabled() is True


def test_main_window_has_ctrl_q_quit_shortcut(qapp: QApplication) -> None:
    window = MainWindow()

    shortcuts = {action.shortcut().toString() for action in window.actions()}

    assert "Ctrl+Q" in shortcuts


def test_settings_dialog_saves_api_base_url(qapp: QApplication, tmp_path: Path) -> None:
    config = AppConfig(api_key="sk-test", api_base_url="http://127.0.0.1:11434/v1")
    dialog = SettingsDialog(config, tmp_path)

    assert dialog.api_base_url_edit.text() == "http://127.0.0.1:11434/v1"

    dialog.api_base_url_edit.setText("http://localhost:8080/v1")

    assert dialog.updated_config().api_base_url == "http://localhost:8080/v1"


@pytest.mark.asyncio
async def test_transcriber_uses_configured_api_base_url(httpserver: HTTPServer, tmp_path: Path) -> None:
    httpserver.expect_request("/v1/audio/transcriptions", method="POST").respond_with_json(
        {"text": "hello", "language": "en", "duration": 1.0}
    )
    audio_path = tmp_path / "sample.wav"
    audio_path.write_bytes(b"RIFF")
    config = AppConfig(api_base_url=httpserver.url_for("/v1"))

    assert config.api_key == ""

    result = await OpenAITranscriber().transcribe(
        audio_path,
        config,
    )

    assert result.is_ok


@pytest.mark.asyncio
async def test_transcriber_requires_api_key_for_default_api_base_url(tmp_path: Path) -> None:
    audio_path = tmp_path / "sample.wav"
    audio_path.write_bytes(b"RIFF")

    result = await OpenAITranscriber().transcribe(audio_path, AppConfig())

    assert result.is_err
    assert result.unwrap_err() == "Missing API key. Open Settings and add one."


def test_render_svg_icon_creates_non_null_icon(qapp: QApplication) -> None:
    icon = render_svg_icon(build_tray_icon_svg(state=TrayIconState.DONE, color="#27ae60"))

    assert icon.isNull() is False


def test_application_identity_matches_desktop_entry(qapp: QApplication) -> None:
    app = create_application()

    assert app.applicationName() == "tinyrecorder"
    assert app.applicationDisplayName() == "TinyRecorder"
    assert app.desktopFileName() == "tinyrecorder"


def test_app_icon_svg_is_monochrome_transparent_rectangular(qapp: QApplication) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    icon_text = (repo_root / "resources" / "icons" / "tinyrecorder.svg").read_text(encoding="utf-8")

    assert "#" not in icon_text
    assert 'fill="none"' in icon_text
    assert 'rx="' not in icon_text
    assert 'ry="' not in icon_text
    assert '<rect x="12" y="12" width="104" height="104"' in icon_text
    assert '<rect x="52" y="26" width="24" height="46"' in icon_text

    image = render_svg_icon(icon_text, size=128).pixmap(128, 128).toImage()
    assert any(image.pixelColor(x, y).alpha() > 0 for x in range(image.width()) for y in range(image.height()))


def test_history_append_and_load_round_trip(tmp_path: Path) -> None:
    history_path = tmp_path / "history.jsonl"
    older = HistoryEntry(
        timestamp="2026-05-07T09:00:00Z",
        audio_file="older.wav",
        transcript="older",
        language="en",
        model="gpt-4o-mini-transcribe",
        duration_sec=1.2,
        noise_reduction=False,
    )
    newer = HistoryEntry(
        timestamp="2026-05-07T10:00:00Z",
        audio_file="newer.wav",
        transcript="newer",
        language="en",
        model="gpt-4o-mini-transcribe",
        duration_sec=1.5,
        noise_reduction=False,
    )

    assert append_history_entry(history_path, older).is_ok
    assert append_history_entry(history_path, newer).is_ok

    loaded = load_history(history_path)
    assert loaded.is_ok
    assert loaded.unwrap() == [newer, older]


def test_load_config_repairs_corrupt_file(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text("not valid toml {{", encoding="utf-8")

    result = load_config(config_path)

    assert result.is_ok
    config = result.unwrap()
    assert config == AppConfig()


def test_load_config_repairs_missing_llm_section(tmp_path: Path) -> None:
    config_path = tmp_path / "tinyrecorder" / "config.toml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        """
[api]
key = "sk-test"
base_url = "http://127.0.0.1:11434/v1"
model = "whisper-1"

[recording]
language = "ru"
noise_reduction = false
sample_rate = 16000
device = ""

[app]
auto_copy = false
""".strip(),
        encoding="utf-8",
    )

    loaded = load_config(config_path)

    assert loaded.is_ok
    config = loaded.unwrap()
    assert config.llm_enabled is False
    assert config.llm_api_key == ""
    assert config.llm_api_base_url == "https://api.openai.com/v1"
    assert config.llm_model == DEFAULT_LLM_MODEL
    assert config.llm_reasoning_effort == ""
    assert config.llm_prompt == ""


def test_build_llm_url_normalizes_trailing_slash() -> None:
    config = AppConfig(llm_api_base_url="http://localhost:11434/v1/")

    assert build_llm_url(config) == "http://localhost:11434/v1/chat/completions"


def test_can_postprocess_with_config_matches_credential_policy() -> None:
    assert can_postprocess_with_config(AppConfig()) is False
    assert can_postprocess_with_config(AppConfig(llm_api_key="sk-llm")) is True
    assert can_postprocess_with_config(AppConfig(llm_api_base_url="http://localhost:11434/v1")) is True


def test_resolve_llm_prompt_falls_back_to_default_when_empty() -> None:
    assert resolve_llm_prompt(AppConfig(llm_prompt="")) == DEFAULT_LLM_PROMPT
    assert resolve_llm_prompt(AppConfig(llm_prompt="   ")) == DEFAULT_LLM_PROMPT
    custom = "Add punctuation only."
    assert resolve_llm_prompt(AppConfig(llm_prompt=custom)) == custom


@pytest.mark.asyncio
async def test_llm_postprocessor_sends_expected_chat_request(httpserver: HTTPServer) -> None:
    httpserver.expect_request("/v1/chat/completions", method="POST").respond_with_json(
        {"choices": [{"message": {"content": "Clean text."}}]}
    )
    config = AppConfig(
        llm_api_key="sk-llm",
        llm_api_base_url=httpserver.url_for("/v1"),
        llm_model="custom-llm",
        llm_reasoning_effort="high",
        llm_prompt="Add punctuation only.",
    )

    result = await LLMPostProcessor().postprocess("raw text", config)

    assert result.is_ok
    assert result.unwrap() == "Clean text."
    matcher = httpserver.create_matcher("/v1/chat/completions", method="POST")
    requests = list(httpserver.iter_matching_requests(matcher))
    assert len(requests) == 1
    body = cast(dict[str, object], requests[0][0].get_json())
    assert body["model"] == "custom-llm"
    assert body["temperature"] == 0
    assert body["reasoning_effort"] == "high"
    assert body["messages"] == [
        {"role": "system", "content": "Add punctuation only."},
        {"role": "user", "content": "raw text"},
    ]


@pytest.mark.asyncio
async def test_llm_postprocessor_omits_reasoning_effort_when_unset(httpserver: HTTPServer) -> None:
    httpserver.expect_request("/v1/chat/completions", method="POST").respond_with_json(
        {"choices": [{"message": {"content": "Clean text."}}]}
    )
    config = AppConfig(llm_api_key="sk-llm", llm_api_base_url=httpserver.url_for("/v1"))

    result = await LLMPostProcessor().postprocess("raw text", config)

    assert result.is_ok
    matcher = httpserver.create_matcher("/v1/chat/completions", method="POST")
    requests = list(httpserver.iter_matching_requests(matcher))
    body = cast(dict[str, object], requests[0][0].get_json())
    assert "reasoning_effort" not in body


@pytest.mark.asyncio
async def test_llm_postprocessor_requires_api_key_for_default_base_url() -> None:
    result = await LLMPostProcessor().postprocess("raw text", AppConfig(llm_enabled=True))

    assert result.is_err
    assert result.unwrap_err() == "Missing LLM API key. Open Settings and add one."


@pytest.mark.asyncio
async def test_llm_postprocessor_rejects_missing_choices(httpserver: HTTPServer) -> None:
    httpserver.expect_request("/v1/chat/completions", method="POST").respond_with_json({})
    config = AppConfig(llm_api_base_url=httpserver.url_for("/v1"))

    result = await LLMPostProcessor().postprocess("raw text", config)

    assert result.is_err
    assert result.unwrap_err() == "Invalid LLM response: missing choices"


@pytest.mark.asyncio
async def test_transcriber_runs_llm_postprocessing_when_enabled(
    httpserver: HTTPServer,
    tmp_path: Path,
) -> None:
    httpserver.expect_request("/v1/audio/transcriptions", method="POST").respond_with_json(
        {"text": "raw transcript", "language": "en", "duration": 1.0}
    )
    httpserver.expect_request("/v1/chat/completions", method="POST").respond_with_json(
        {"choices": [{"message": {"content": "Clean transcript."}}]}
    )
    audio_path = tmp_path / "sample.wav"
    audio_path.write_bytes(b"RIFF")
    config = AppConfig(
        api_base_url=httpserver.url_for("/v1"),
        llm_enabled=True,
        llm_api_base_url=httpserver.url_for("/v1"),
    )

    result = await OpenAITranscriber().transcribe(audio_path, config)

    assert result.is_ok
    transcript = result.unwrap()
    assert transcript.text == "Clean transcript."
    assert transcript.warning == ""
    matcher = httpserver.create_matcher("/v1/chat/completions", method="POST")
    assert len(list(httpserver.iter_matching_requests(matcher))) == 1


@pytest.mark.asyncio
async def test_transcriber_keeps_raw_text_and_warns_on_llm_failure(
    httpserver: HTTPServer,
    tmp_path: Path,
) -> None:
    httpserver.expect_request("/v1/audio/transcriptions", method="POST").respond_with_json(
        {"text": "raw transcript", "language": "en", "duration": 1.0}
    )
    httpserver.expect_request("/v1/chat/completions", method="POST").respond_with_json({}, status=401)
    audio_path = tmp_path / "sample.wav"
    audio_path.write_bytes(b"RIFF")
    config = AppConfig(
        api_base_url=httpserver.url_for("/v1"),
        llm_enabled=True,
        llm_api_base_url=httpserver.url_for("/v1"),
    )

    result = await OpenAITranscriber().transcribe(audio_path, config)

    assert result.is_ok
    transcript = result.unwrap()
    assert transcript.text == "raw transcript"
    assert "LLM post-processing failed" in transcript.warning


@pytest.mark.asyncio
async def test_transcriber_skips_llm_postprocessing_when_disabled(
    httpserver: HTTPServer,
    tmp_path: Path,
) -> None:
    httpserver.expect_request("/v1/audio/transcriptions", method="POST").respond_with_json(
        {"text": "raw transcript", "language": "en", "duration": 1.0}
    )
    audio_path = tmp_path / "sample.wav"
    audio_path.write_bytes(b"RIFF")
    config = AppConfig(
        api_base_url=httpserver.url_for("/v1"),
        llm_enabled=False,
        llm_api_base_url=httpserver.url_for("/v1"),
    )

    result = await OpenAITranscriber().transcribe(audio_path, config)

    assert result.is_ok
    assert result.unwrap().text == "raw transcript"


def test_main_window_has_llm_postprocess_checkbox(qapp: QApplication) -> None:
    window = MainWindow()

    assert window.llm_postprocess_checkbox is not None
    assert window.llm_postprocess_checkbox.isChecked() is False


def test_settings_dialog_applies_llm_fields(qapp: QApplication, tmp_path: Path) -> None:
    config = AppConfig(
        llm_api_key="sk-llm",
        llm_api_base_url="http://127.0.0.1:11434/v1",
        llm_model="custom-llm",
        llm_reasoning_effort="low",
        llm_prompt="Add punctuation only.",
    )
    dialog = SettingsDialog(config, tmp_path)

    assert dialog.llm_api_key_edit.text() == "sk-llm"
    assert dialog.llm_api_base_url_edit.text() == "http://127.0.0.1:11434/v1"
    assert dialog.llm_model_edit.text() == "custom-llm"
    assert dialog.llm_reasoning_effort_edit.text() == "low"
    assert dialog.llm_prompt_edit.toPlainText() == "Add punctuation only."

    dialog.llm_api_key_edit.setText("sk-new")
    dialog.llm_model_edit.setText("other-model")
    dialog.llm_reasoning_effort_edit.setText("high")
    dialog.llm_prompt_edit.setPlainText("Custom prompt")

    updated = dialog.updated_config()
    assert updated.llm_api_key == "sk-new"
    assert updated.llm_model == "other-model"
    assert updated.llm_reasoning_effort == "high"
    assert updated.llm_prompt == "Custom prompt"
    assert updated.llm_enabled == config.llm_enabled
