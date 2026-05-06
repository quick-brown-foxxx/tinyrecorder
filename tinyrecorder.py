#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "rusty-results>=1.1.1",
#   "PySide6>=6.9.0",
#   "qasync>=0.27.1",
#   "sounddevice>=0.5.1",
#   "soundfile>=0.13.1",
#   "numpy>=2.2.4",
#   "httpx>=0.28.1",
#   "tomli-w>=1.2.0",
# ]
# ///

"""TinyRecorder v0.0.1.

Single-file Linux-first Qt speech-to-text app preserving the project's core DNA:
tray-first UI, state machine, crash-safe PCM recording, OpenAI transcription,
TOML config, and JSONL history.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import shutil
import signal
import struct
import sys
import time
import tomllib
from array import array
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, replace
from enum import StrEnum
from io import BufferedWriter
from pathlib import Path
from typing import Final, Protocol, TypeGuard, runtime_checkable

import httpx
import numpy as np
import qasync  # pyright: ignore[reportMissingTypeStubs]  # rationale: library ships no stubs
import tomli_w
from PySide6.QtCore import QByteArray, QObject, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QCloseEvent, QGuiApplication, QIcon, QKeySequence, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QStatusBar,
    QSystemTrayIcon,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from rusty_results.prelude import Err, Ok, Result

APP_ID: Final = "tinyrecorder"
APP_NAME: Final = "TinyRecorder"
APP_VERSION: Final = "0.0.1"
DEFAULT_API_BASE_URL: Final = "https://api.openai.com/v1"
DEFAULT_MODEL: Final = "gpt-4o-mini-transcribe"
DEFAULT_LANGUAGE: Final = "auto"
SUPPORTED_MODELS: Final[tuple[str, ...]] = (
    "gpt-4o-mini-transcribe",
    "gpt-4o-transcribe",
    "whisper-1",
)
SUPPORTED_LANGUAGES: Final[tuple[str, ...]] = ("auto", "en", "ru")
SAMPLE_RATE: Final = 16000
CHANNELS: Final = 1
BITS_PER_SAMPLE: Final = 16
BLOCK_SIZE: Final = 1600
MAX_TRANSCRIPTION_SIZE: Final = 24 * 1024 * 1024
RETRYABLE_STATUS_CODES: Final[frozenset[int]] = frozenset({429, 500, 503})
CONTENT_TYPES: Final[dict[str, str]] = {
    ".flac": "audio/flac",
    ".m4a": "audio/mp4",
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".wav": "audio/wav",
}
TRAY_NEUTRAL_COLOR: Final = "#eff0f1"
TRAY_ERROR_COLOR: Final = "#da4453"
TRAY_DONE_COLOR: Final = "#27ae60"
TRAY_DONE_MSEC: Final = 1000
MODEL_PRICES_PER_MINUTE: Final[dict[str, float]] = {
    "gpt-4o-mini-transcribe": 0.003,
    "gpt-4o-transcribe": 0.006,
    "whisper-1": 0.006,
}

type AppResult[T] = Result[T, str]


@runtime_checkable
class SupportsStopClose(Protocol):
    def start(self) -> None: ...

    def stop(self) -> None: ...

    def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class AppPaths:
    """Filesystem layout for config, cache, and history."""

    config_dir: Path
    cache_dir: Path
    data_dir: Path
    audio_dir: Path
    config_path: Path
    history_path: Path


@dataclass(frozen=True, slots=True)
class AppConfig:
    """User-editable configuration stored in TOML."""

    api_key: str = ""
    api_base_url: str = DEFAULT_API_BASE_URL
    model: str = DEFAULT_MODEL
    language: str = DEFAULT_LANGUAGE
    noise_reduction: bool = False
    sample_rate: int = SAMPLE_RATE
    device: str = ""
    auto_copy: bool = True


@dataclass(frozen=True, slots=True)
class HistoryEntry:
    """Persisted transcription record."""

    timestamp: str
    audio_file: str
    transcript: str
    language: str
    model: str
    duration_sec: float
    noise_reduction: bool

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> AppResult[HistoryEntry]:
        try:
            timestamp = str(payload["timestamp"])
            audio_file = str(payload["audio_file"])
            transcript = str(payload["transcript"])
            language = str(payload["language"])
            model = str(payload["model"])
            duration_raw = _coerce_float(payload["duration_sec"])
            if duration_raw is None:
                return Err("Invalid history entry: duration_sec is not numeric")
            duration_sec = duration_raw
            noise_reduction = bool(payload["noise_reduction"])
        except (KeyError, TypeError, ValueError) as exc:
            return Err(f"Invalid history entry: {exc}")
        return Ok(
            cls(
                timestamp=timestamp,
                audio_file=audio_file,
                transcript=transcript,
                language=language,
                model=model,
                duration_sec=duration_sec,
                noise_reduction=noise_reduction,
            )
        )


@dataclass(frozen=True, slots=True)
class TranscriptionResult:
    """Successful OpenAI transcription response."""

    text: str
    language: str
    duration_sec: float
    model: str
    cost_estimate: float


class RecordingState(StrEnum):
    """UI-visible lifecycle state."""

    IDLE = "idle"
    RECORDING = "recording"
    PROCESSING = "processing"
    SUCCESS = "success"
    ERROR = "error"


class TrayIconState(StrEnum):
    """Small visual state machine for the tray icon only."""

    IDLE = "idle"
    RECORDING = "recording"
    TRANSCRIBING = "transcribing"
    ERROR = "error"
    DONE = "done"


VALID_TRANSITIONS: Final[dict[RecordingState, frozenset[RecordingState]]] = {
    RecordingState.IDLE: frozenset({RecordingState.RECORDING, RecordingState.PROCESSING}),
    RecordingState.RECORDING: frozenset({RecordingState.IDLE, RecordingState.PROCESSING}),
    RecordingState.PROCESSING: frozenset({RecordingState.IDLE, RecordingState.SUCCESS, RecordingState.ERROR}),
    RecordingState.SUCCESS: frozenset({RecordingState.IDLE, RecordingState.PROCESSING}),
    RecordingState.ERROR: frozenset({RecordingState.IDLE, RecordingState.PROCESSING}),
}


def can_trigger_record_action(state: RecordingState, *, can_transcribe: bool, mic_available: bool) -> bool:
    """Mirror the record button enablement policy for tray interactions."""

    return (
        mic_available
        and can_transcribe
        and state
        in {
            RecordingState.IDLE,
            RecordingState.RECORDING,
            RecordingState.SUCCESS,
            RecordingState.ERROR,
        }
    )


def can_cancel_current_operation(state: RecordingState) -> bool:
    """Return whether the cancel control should be available."""

    return state in {RecordingState.RECORDING, RecordingState.PROCESSING}


def resolve_tray_icon_state(state: RecordingState, *, show_done: bool) -> TrayIconState:
    """Map app state to a tray-specific visual state."""

    if state == RecordingState.RECORDING:
        return TrayIconState.RECORDING
    if state == RecordingState.PROCESSING:
        return TrayIconState.TRANSCRIBING
    if state == RecordingState.ERROR:
        return TrayIconState.ERROR
    if state == RecordingState.SUCCESS and show_done:
        return TrayIconState.DONE
    return TrayIconState.IDLE


def _xdg_path(env_name: str, fallback: str) -> Path:
    raw = os.environ.get(env_name)
    if raw:
        return Path(raw).expanduser()
    return Path.home() / fallback


def _windows_app_path(env_name: str, fallback_parts: tuple[str, ...]) -> Path:
    raw = os.environ.get(env_name)
    if raw:
        return Path(raw).expanduser()
    return Path.home().joinpath(*fallback_parts)


def resolve_app_paths() -> AppPaths:
    """Resolve per-platform app paths."""

    if sys.platform == "win32":
        roaming_dir = _windows_app_path("APPDATA", ("AppData", "Roaming")) / APP_NAME
        local_dir = _windows_app_path("LOCALAPPDATA", ("AppData", "Local")) / APP_NAME
        audio_dir = local_dir / "audio"
        return AppPaths(
            config_dir=roaming_dir,
            cache_dir=local_dir,
            data_dir=roaming_dir,
            audio_dir=audio_dir,
            config_path=roaming_dir / "config.toml",
            history_path=roaming_dir / "history.jsonl",
        )

    config_dir = _xdg_path("XDG_CONFIG_HOME", ".config") / APP_NAME.lower()
    cache_dir = _xdg_path("XDG_CACHE_HOME", ".cache") / APP_NAME.lower()
    data_dir = _xdg_path("XDG_DATA_HOME", ".local/share") / APP_NAME.lower()
    audio_dir = cache_dir / "audio"
    return AppPaths(
        config_dir=config_dir,
        cache_dir=cache_dir,
        data_dir=data_dir,
        audio_dir=audio_dir,
        config_path=config_dir / "config.toml",
        history_path=data_dir / "history.jsonl",
    )


def ensure_parent_dir(path: Path) -> AppResult[None]:
    """Create the parent directory for a file path."""

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return Err(f"Cannot create directory for {path}: {exc}")
    return Ok(None)


def ensure_app_dirs(paths: AppPaths) -> AppResult[None]:
    """Create the expected application directories."""

    for directory in (
        paths.config_dir,
        paths.cache_dir,
        paths.data_dir,
        paths.audio_dir,
    ):
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return Err(f"Cannot create directory {directory}: {exc}")
    return Ok(None)


def _is_object_mapping(value: object) -> TypeGuard[Mapping[object, object]]:
    return isinstance(value, Mapping)


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _is_object_iterable(value: object) -> TypeGuard[Iterable[object]]:
    return isinstance(value, Iterable)


def _coerce_object_sequence(value: object) -> list[object] | None:
    if _is_object_list(value):
        return value
    if isinstance(value, str | bytes) or _is_object_mapping(value):
        return None
    if not _is_object_iterable(value):
        return None
    return list(value)


def _coerce_table(value: object) -> dict[str, object] | None:
    if not _is_object_mapping(value):
        return None

    result: dict[str, object] = {}
    for raw_key, raw_item in value.items():
        result[str(raw_key)] = raw_item
    return result


def _load_toml_object(text: str) -> object:
    return tomllib.loads(text)


def _load_json_object(text: str) -> object:
    return json.loads(text)  # pyright: ignore[reportAny]  # rationale: stdlib returns Any; validated by _coerce_table


def _load_response_json(response: httpx.Response) -> object:
    return response.json()  # pyright: ignore[reportAny]  # rationale: httpx returns Any; validated by _coerce_table


def _coerce_int(value: object) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else None
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _coerce_float(value: object) -> float | None:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _normalize_model(value: object) -> str:
    text = str(value) if value is not None else DEFAULT_MODEL
    return text if text in SUPPORTED_MODELS else DEFAULT_MODEL


def _normalize_language(value: object) -> str:
    text = str(value) if value is not None else DEFAULT_LANGUAGE
    return text if text in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE


def _normalize_sample_rate(value: object) -> int:
    sample_rate = _coerce_int(value)
    if sample_rate is None:
        return SAMPLE_RATE
    return sample_rate if sample_rate > 0 else SAMPLE_RATE


def _normalize_api_base_url(value: object) -> str:
    text = str(value).strip() if value is not None else ""
    return text.rstrip("/") if text else DEFAULT_API_BASE_URL


def build_transcription_url(config: AppConfig) -> str:
    """Return the OpenAI-compatible transcription endpoint for this config."""

    return f"{_normalize_api_base_url(config.api_base_url)}/audio/transcriptions"


def can_transcribe_with_config(config: AppConfig) -> bool:
    """Return whether config has enough provider details to attempt transcription."""

    return bool(config.api_key.strip()) or _normalize_api_base_url(config.api_base_url) != DEFAULT_API_BASE_URL


def _config_to_toml_payload(
    config: AppConfig,
) -> dict[str, dict[str, str | int | bool]]:
    return {
        "api": {"key": config.api_key, "base_url": _normalize_api_base_url(config.api_base_url), "model": config.model},
        "recording": {
            "language": config.language,
            "noise_reduction": config.noise_reduction,
            "sample_rate": config.sample_rate,
            "device": config.device,
        },
        "app": {"auto_copy": config.auto_copy},
    }


def create_default_config(config_path: Path) -> AppResult[AppConfig]:
    """Write the default config if it does not exist yet."""

    config = AppConfig()
    saved = save_config(config, config_path)
    if saved.is_err:
        return Err(saved.unwrap_err())
    return Ok(config)


def load_config(config_path: Path) -> AppResult[AppConfig]:
    """Load config, recreating defaults for missing or corrupt files."""

    if not config_path.exists():
        return create_default_config(config_path)

    try:
        payload_obj = _load_toml_object(config_path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError):
        return create_default_config(config_path)

    payload = _coerce_table(payload_obj)
    if payload is None:
        return create_default_config(config_path)

    api = _coerce_table(payload.get("api", {}))
    recording = _coerce_table(payload.get("recording", {}))
    app = _coerce_table(payload.get("app", {}))
    if api is None or recording is None or app is None:
        return create_default_config(config_path)

    config = AppConfig(
        api_key=str(api.get("key", "")),
        api_base_url=_normalize_api_base_url(api.get("base_url")),
        model=_normalize_model(api.get("model")),
        language=_normalize_language(recording.get("language")),
        noise_reduction=bool(recording.get("noise_reduction", False)),
        sample_rate=_normalize_sample_rate(recording.get("sample_rate")),
        device=str(recording.get("device", "")),
        auto_copy=bool(app.get("auto_copy", True)),
    )
    repaired = save_config(config, config_path)
    if repaired.is_err:
        return Err(repaired.unwrap_err())
    return Ok(config)


def save_config(config: AppConfig, config_path: Path) -> AppResult[None]:
    """Persist config to TOML."""

    prepared = ensure_parent_dir(config_path)
    if prepared.is_err:
        return Err(prepared.unwrap_err())

    try:
        config_path.write_text(tomli_w.dumps(_config_to_toml_payload(config)), encoding="utf-8")
    except OSError as exc:
        return Err(f"Cannot write config: {exc}")
    return Ok(None)


def load_history(history_path: Path) -> AppResult[list[HistoryEntry]]:
    """Load history entries from JSONL, skipping corrupt lines."""

    if not history_path.exists():
        return Ok([])

    entries: list[HistoryEntry] = []
    try:
        lines = history_path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return Err(f"Cannot read history: {exc}")

    for line in lines:
        if not line.strip():
            continue
        try:
            payload_obj = _load_json_object(line)
        except json.JSONDecodeError:
            continue
        payload = _coerce_table(payload_obj)
        if payload is None:
            continue
        item = HistoryEntry.from_dict(payload)
        if item.is_ok:
            entries.append(item.unwrap())

    entries.sort(key=lambda entry: entry.timestamp, reverse=True)
    return Ok(entries)


def append_history_entry(history_path: Path, entry: HistoryEntry) -> AppResult[None]:
    """Append a new history item to JSONL storage."""

    prepared = ensure_parent_dir(history_path)
    if prepared.is_err:
        return Err(prepared.unwrap_err())

    try:
        with history_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(entry), ensure_ascii=True) + "\n")
    except OSError as exc:
        return Err(f"Cannot append history: {exc}")
    return Ok(None)


def build_wav_header(data_size: int, sample_rate: int, channels: int, bits_per_sample: int) -> bytes:
    """Construct a PCM WAV header for raw recorded bytes."""

    byte_rate = sample_rate * channels * bits_per_sample // 8
    block_align = channels * bits_per_sample // 8
    riff_size = data_size + 36
    return struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        riff_size,
        b"WAVE",
        b"fmt ",
        16,
        1,
        channels,
        sample_rate,
        byte_rate,
        block_align,
        bits_per_sample,
        b"data",
        data_size,
    )


def convert_pcm_to_wav(pcm_path: Path, sample_rate: int, channels: int, bits_per_sample: int) -> Path:
    """Recover a crash-safe PCM file into a readable WAV file."""

    raw = pcm_path.read_bytes()
    sample_width = bits_per_sample // 8
    even_size = len(raw) - (len(raw) % sample_width)
    body = raw[:even_size]
    wav_path = pcm_path.with_suffix(".wav")
    header = build_wav_header(len(body), sample_rate, channels, bits_per_sample)
    wav_path.write_bytes(header + body)
    return wav_path


def compute_rms(chunk: np.ndarray) -> float:
    """Compute RMS for an int16 audio chunk."""

    if chunk.size == 0:
        return 0.0
    samples = array("h")
    samples.frombytes(chunk.tobytes())
    sum_squares = 0.0
    for sample in samples:
        normalized_sample = sample / 32768.0
        sum_squares += normalized_sample * normalized_sample
    mean_square = sum_squares / float(chunk.size)
    return math.sqrt(mean_square)


def estimate_cost(duration_sec: float, model: str) -> float:
    """Estimate cost based on model and audio duration."""

    price_per_minute = MODEL_PRICES_PER_MINUTE.get(model, MODEL_PRICES_PER_MINUTE[DEFAULT_MODEL])
    return price_per_minute * max(duration_sec, 0.0) / 60.0


def copy_into_cache(source_path: Path, audio_dir: Path) -> AppResult[Path]:
    """Copy imported audio into the managed cache directory."""

    try:
        audio_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return Err(f"Cannot prepare audio cache: {exc}")

    target_name = build_cache_audio_name("import", source_path.suffix.lower())
    target = audio_dir / target_name
    try:
        shutil.copy2(source_path, target)
    except OSError as exc:
        return Err(f"Cannot import audio file: {exc}")
    return Ok(target)


def is_supported_audio_path(path: Path) -> AppResult[None]:
    """Basic audio file validation for imported files."""

    if not path.exists():
        return Err(f"Audio file not found: {path}")
    if not path.is_file():
        return Err(f"Audio path is not a file: {path}")
    if path.stat().st_size == 0:
        return Err("Audio file is empty")
    return Ok(None)


def build_cache_audio_name(prefix: str, suffix: str, *, now_ns: int | None = None) -> str:
    """Create a stable-but-unique cache filename."""

    stamp_ns = time.time_ns() if now_ns is None else now_ns
    seconds = stamp_ns // 1_000_000_000
    fractional = stamp_ns % 1_000_000_000
    timestamp = time.strftime("%Y%m%d_%H%M%S", time.localtime(seconds))
    return f"{prefix}_{timestamp}_{fractional:09d}{suffix}"


def guess_audio_content_type(path: Path) -> str:
    """Infer multipart content type from the file suffix."""

    return CONTENT_TYPES.get(path.suffix.lower(), "application/octet-stream")


def build_tray_icon_svg(*, state: TrayIconState, color: str) -> str:
    """Build a Breeze-like monochrome microphone tray icon as SVG text."""

    accent = ""
    if state == TrayIconState.RECORDING:
        accent = f'<circle cx="17" cy="17" r="2.3" fill="{color}" stroke="none"/>'
    elif state == TrayIconState.TRANSCRIBING:
        accent = (
            f'<circle cx="17" cy="17" r="3" fill="none" stroke="{color}" stroke-width="1.3"/>'
            f'<path d="M17 17V15.5" stroke="{color}" stroke-width="1.3" stroke-linecap="round"/>'
            f'<path d="M17 17L18.2 17.9" stroke="{color}" stroke-width="1.3" stroke-linecap="round"/>'
        )
    elif state == TrayIconState.ERROR:
        accent = (
            f'<path d="M15.3 15.3l3.4 3.4M18.7 15.3l-3.4 3.4" '
            f'stroke="{color}" stroke-width="1.8" stroke-linecap="round"/>'
        )
    elif state == TrayIconState.DONE:
        accent = (
            f'<path d="M14.7 17.2l1.6 1.6 3-3.2" '
            f'stroke="{color}" stroke-width="1.8" stroke-linecap="round" '
            'stroke-linejoin="round" fill="none"/>'
        )

    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 22 22">'
        f'<rect x="2.5" y="2.5" width="17" height="17" fill="none" stroke="{color}" stroke-width="1.2"/>'
        f'<g fill="none" stroke="{color}" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M8 4.5h6v6.8q0 2.5-3 2.5t-3-2.5z"/>'
        '<path d="M11 14.7v2.1"/>'
        '<path d="M8.8 17.4h4.4"/>'
        "</g>"
        f"{accent}"
        "</svg>"
    )


def render_svg_icon(svg_text: str, *, size: int = 22) -> QIcon:
    """Render embedded SVG text into a QIcon for the tray."""

    renderer = QSvgRenderer(QByteArray(svg_text.encode("utf-8")))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return QIcon(pixmap)


def _query_sounddevice_devices() -> list[object]:
    import sounddevice as sounddevice_module  # pyright: ignore[reportMissingTypeStubs]  # rationale: library ships no stubs

    raw_devices: object = sounddevice_module.query_devices()  # pyright: ignore[reportUnknownMemberType, reportAny]  # rationale: validated below
    devices = _coerce_object_sequence(raw_devices)
    if devices is not None:
        return devices
    return [raw_devices]


def _create_sounddevice_input_stream(device_name: str, callback: object) -> SupportsStopClose:
    import sounddevice as sounddevice_module  # pyright: ignore[reportMissingTypeStubs]  # rationale: library ships no stubs

    raw_stream: object = sounddevice_module.InputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype="int16",
        blocksize=BLOCK_SIZE,
        device=device_name or None,
        callback=callback,
    )
    if not isinstance(raw_stream, SupportsStopClose):
        raise TypeError("sounddevice InputStream does not expose start/stop/close")
    return raw_stream


class StateMachine:
    """Small state machine preserving the main spec transitions."""

    def __init__(self) -> None:
        self.current_state = RecordingState.IDLE
        self.audio_file_path: Path | None = None

    def transition(self, new_state: RecordingState) -> AppResult[RecordingState]:
        allowed = VALID_TRANSITIONS[self.current_state]
        if new_state not in allowed:
            return Err(f"Invalid transition: {self.current_state} -> {new_state}")
        self.current_state = new_state
        return Ok(new_state)


def recover_orphaned_pcm(audio_dir: Path) -> AppResult[list[Path]]:
    """Recover .pcm files left behind by prior crashes."""

    recovered: list[Path] = []
    try:
        pcm_files = sorted(audio_dir.glob("*.pcm"))
    except OSError as exc:
        return Err(f"Cannot scan cache directory: {exc}")
    for pcm_path in pcm_files:
        wav_path = pcm_path.with_suffix(".wav")
        if wav_path.exists():
            continue
        recovered.append(convert_pcm_to_wav(pcm_path, SAMPLE_RATE, CHANNELS, BITS_PER_SAMPLE))
    return Ok(recovered)


def list_input_devices() -> AppResult[list[str]]:
    """Return capture-capable input device names."""

    try:
        devices_raw = _query_sounddevice_devices()
    except ImportError as exc:
        return Err(f"sounddevice unavailable: {exc}")
    except Exception as exc:
        return Err(f"Cannot query audio devices: {exc}")

    names: list[str] = []
    for device in devices_raw:
        table = _coerce_table(device)
        if table is None:
            continue
        max_input_channels_raw = table.get("max_input_channels", 0)
        name_raw = table.get("name", "")
        max_input_channels = _coerce_int(max_input_channels_raw)
        if max_input_channels is None:
            continue
        if max_input_channels > 0:
            names.append(str(name_raw))
    return Ok(names)


class RecorderSession(QObject):
    """Crash-safe recording session writing PCM to disk as audio arrives."""

    level_changed = Signal(float)

    def __init__(self, audio_dir: Path) -> None:
        super().__init__()
        self._audio_dir = audio_dir
        self._stream: SupportsStopClose | None = None
        self._pcm_path: Path | None = None
        self._handle: BufferedWriter | None = None
        self._started_at = 0.0
        self._had_callback_error = False

    @property
    def started_at(self) -> float:
        return self._started_at

    def start(self, device_name: str) -> AppResult[Path]:
        """Begin writing microphone samples to a PCM cache file."""

        try:
            self._audio_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return Err(f"Cannot prepare audio cache: {exc}")

        pcm_path = self._audio_dir / build_cache_audio_name("rec", ".pcm")
        try:
            handle = pcm_path.open("wb")
        except OSError as exc:
            return Err(f"Cannot create recording file: {exc}")

        try:

            def callback(indata: np.ndarray, _frames: int, _time_info: object, status: object) -> None:
                if status:
                    self._had_callback_error = True
                mono = np.asarray(indata[:, 0], dtype=np.int16)
                handle.write(mono.tobytes())
                self.level_changed.emit(compute_rms(mono))

            stream = _create_sounddevice_input_stream(device_name, callback)
            stream.start()
        except Exception as exc:
            handle.close()
            return Err(f"Cannot start recording: {exc}")

        self._handle = handle
        self._stream = stream
        self._pcm_path = pcm_path
        self._started_at = time.monotonic()
        self._had_callback_error = False
        return Ok(pcm_path)

    def stop(self) -> AppResult[Path]:
        """Stop recording and recover the PCM file into a WAV."""

        if self._stream is None or self._handle is None or self._pcm_path is None:
            return Err("No recording in progress")

        try:
            self._stream.stop()
            self._stream.close()
            self._handle.close()
        except Exception as exc:
            return Err(f"Cannot stop recording cleanly: {exc}")

        pcm_path = self._pcm_path
        self._stream = None
        self._handle = None
        self._pcm_path = None
        self.level_changed.emit(0.0)
        if self._had_callback_error:
            return Err("Recording ended with an audio callback error")
        return Ok(convert_pcm_to_wav(pcm_path, SAMPLE_RATE, CHANNELS, BITS_PER_SAMPLE))

    def cancel(self) -> AppResult[Path]:
        """Stop recording but keep the captured audio for later retry or inspection."""

        stopped = self.stop()
        if stopped.is_err:
            return Err(stopped.unwrap_err())
        return Ok(stopped.unwrap())


class OpenAITranscriber:
    """Small OpenAI HTTP client with retry logic."""

    async def transcribe(self, audio_path: Path, config: AppConfig) -> AppResult[TranscriptionResult]:
        if not can_transcribe_with_config(config):
            return Err("Missing API key. Open Settings and add one.")
        prepared_audio = self._prepare_audio_request(audio_path)
        if prepared_audio.is_err:
            return Err(prepared_audio.unwrap_err())
        file_bytes = prepared_audio.unwrap()

        attempt = 0
        while attempt < 3:
            attempt += 1
            result = await self._attempt_transcription(audio_path.name, file_bytes, config)
            if result.is_ok:
                return result
            error_text = result.unwrap_err()
            if not error_text.startswith("retry:"):
                return Err(error_text)
            if attempt >= 3:
                return Err(error_text.removeprefix("retry:"))
            await asyncio.sleep(2.0 ** (attempt - 1))
        return Err("Transcription failed after retries")

    def _prepare_audio_request(self, audio_path: Path) -> AppResult[bytes]:
        try:
            if not audio_path.exists():
                return Err(f"Audio file not found: {audio_path}")
            if audio_path.stat().st_size > MAX_TRANSCRIPTION_SIZE:
                return Err("Audio file is too large for v0.0.1. Compression and chunking are deferred.")
            return Ok(audio_path.read_bytes())
        except OSError as exc:
            return Err(f"Cannot read audio file: {exc}")

    async def _attempt_transcription(
        self,
        audio_name: str,
        file_bytes: bytes,
        config: AppConfig,
    ) -> AppResult[TranscriptionResult]:

        data: dict[str, str] = {
            "model": config.model,
            "response_format": "verbose_json",
        }
        if config.language != "auto":
            data["language"] = config.language

        headers: dict[str, str] = {}
        if config.api_key.strip():
            headers["Authorization"] = f"Bearer {config.api_key}"
        files = {"file": (audio_name, file_bytes, guess_audio_content_type(Path(audio_name)))}

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    build_transcription_url(config),
                    headers=headers,
                    data=data,
                    files=files,
                )
        except httpx.HTTPError as exc:
            return Err(f"retry:Network error: {exc}")

        if response.status_code == 401:
            return Err("Invalid API key. Check Settings.")
        if response.status_code in RETRYABLE_STATUS_CODES:
            return Err(f"retry:OpenAI returned {response.status_code}. Retrying.")
        if response.status_code >= 400:
            return Err(f"Transcription failed: HTTP {response.status_code} {response.text[:200]}")

        try:
            payload_obj = _load_response_json(response)
        except json.JSONDecodeError as exc:
            return Err(f"Invalid OpenAI response: {exc}")
        payload = _coerce_table(payload_obj)
        if payload is None:
            return Err("Invalid OpenAI response shape")

        text = str(payload.get("text", "")).strip()
        if not text:
            return Err("OpenAI returned an empty transcript")
        language = str(payload.get("language", config.language if config.language != "auto" else "auto"))
        duration_value = _coerce_float(payload.get("duration", 0.0))
        duration_sec = duration_value if duration_value is not None else 0.0
        return Ok(
            TranscriptionResult(
                text=text,
                language=language,
                duration_sec=duration_sec,
                model=config.model,
                cost_estimate=estimate_cost(duration_sec, config.model),
            )
        )


class SettingsDialog(QDialog):
    """Modal editor for the minimal config surface."""

    def __init__(self, config: AppConfig, cache_dir: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(420)
        self._config = config

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.api_key_edit = QLineEdit(config.api_key)
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_edit.setPlaceholderText("sk-...")
        form.addRow("API key", self.api_key_edit)

        self.api_base_url_edit = QLineEdit(config.api_base_url)
        self.api_base_url_edit.setPlaceholderText(DEFAULT_API_BASE_URL)
        form.addRow("API base URL", self.api_base_url_edit)

        self.auto_copy_checkbox = QCheckBox("Copy transcript to clipboard automatically")
        self.auto_copy_checkbox.setChecked(config.auto_copy)
        form.addRow("", self.auto_copy_checkbox)

        self.noise_checkbox = QCheckBox("Noise reduction (deferred in v0.0.1)")
        self.noise_checkbox.setChecked(config.noise_reduction)
        self.noise_checkbox.setEnabled(False)
        form.addRow("", self.noise_checkbox)

        cache_label = QLabel(str(cache_dir))
        cache_label.setWordWrap(True)
        form.addRow("Audio cache", cache_label)
        layout.addLayout(form)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        cancel_button = QPushButton("Cancel")
        save_button = QPushButton("Save")
        cancel_button.clicked.connect(self.reject)
        save_button.clicked.connect(self.accept)
        button_row.addWidget(cancel_button)
        button_row.addWidget(save_button)
        layout.addLayout(button_row)

    def updated_config(self) -> AppConfig:
        """Return config with current dialog values applied."""

        return replace(
            self._config,
            api_key=self.api_key_edit.text().strip(),
            api_base_url=_normalize_api_base_url(self.api_base_url_edit.text()),
            auto_copy=self.auto_copy_checkbox.isChecked(),
        )


class HistoryDialog(QDialog):
    """Simple recent transcript picker."""

    def __init__(self, entries: list[HistoryEntry], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("History")
        self.resize(520, 420)
        self._entries = entries
        self.selected_entry: HistoryEntry | None = None

        layout = QVBoxLayout(self)
        self.list_widget = QListWidget()
        for entry in entries:
            preview = entry.transcript.replace("\n", " ")[:60]
            item = QListWidgetItem(f"{entry.timestamp}  {preview}")
            self.list_widget.addItem(item)
        layout.addWidget(self.list_widget)

        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        layout.addWidget(self.preview, 1)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        load_button = QPushButton("Load")
        close_button = QPushButton("Close")
        button_row.addWidget(load_button)
        button_row.addWidget(close_button)
        layout.addLayout(button_row)

        self.list_widget.currentRowChanged.connect(self._on_row_changed)
        load_button.clicked.connect(self._accept_selection)
        close_button.clicked.connect(self.reject)

        if entries:
            self.list_widget.setCurrentRow(0)

    def _on_row_changed(self, row: int) -> None:
        if row < 0 or row >= len(self._entries):
            self.preview.clear()
            return
        entry = self._entries[row]
        self.preview.setPlainText(entry.transcript)

    def _accept_selection(self) -> None:
        row = self.list_widget.currentRow()
        if row < 0 or row >= len(self._entries):
            self.reject()
            return
        self.selected_entry = self._entries[row]
        self.accept()


class MainWindow(QMainWindow):
    """Primary TinyRecorder window."""

    quit_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._hide_to_tray = True
        self.setWindowTitle(APP_NAME)
        self.resize(420, 560)
        self.setMinimumSize(360, 460)

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        top_row = QHBoxLayout()
        self.device_combo = QComboBox()
        self.language_combo = QComboBox()
        self.model_combo = QComboBox()
        self.settings_button = QToolButton()
        self.settings_button.setText("Settings")
        top_row.addWidget(self.device_combo, 2)
        top_row.addWidget(self.language_combo, 1)
        top_row.addWidget(self.model_combo, 2)
        top_row.addWidget(self.settings_button)
        layout.addLayout(top_row)

        self.level_bar = QProgressBar()
        self.level_bar.setRange(0, 100)
        self.level_bar.setValue(0)
        self.level_bar.setFormat("Input level")
        layout.addWidget(self.level_bar)

        recording_row = QHBoxLayout()
        self.record_button = QPushButton("● REC")
        self.record_button.setObjectName("recordButton")
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.hide()
        self.timer_label = QLabel("00:00")
        self.timer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        recording_row.addWidget(self.record_button, 2)
        recording_row.addWidget(self.timer_label, 1)
        recording_row.addWidget(self.cancel_button, 1)
        layout.addLayout(recording_row)

        self.transcript_area = QPlainTextEdit()
        self.transcript_area.setReadOnly(True)
        self.transcript_area.setPlaceholderText("Ready to record or import audio.")
        layout.addWidget(self.transcript_area, 1)

        actions_row = QHBoxLayout()
        self.copy_button = QPushButton("Copy")
        self.retry_button = QPushButton("Retry")
        self.import_button = QPushButton("Import")
        self.history_button = QPushButton("History")
        for button in (
            self.copy_button,
            self.retry_button,
            self.import_button,
            self.history_button,
        ):
            actions_row.addWidget(button)
        layout.addLayout(actions_row)

        self.setCentralWidget(root)

        status = QStatusBar()
        self.setStatusBar(status)
        self.state_label = QLabel("Idle")
        self.cost_label = QLabel("$0.0000")
        status.addWidget(self.state_label)
        status.addPermanentWidget(self.cost_label)

        quit_action = QAction("Quit", self)
        quit_action.setShortcut(QKeySequence("Ctrl+Q"))
        quit_action.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        quit_action.triggered.connect(self.quit_requested.emit)
        self.addAction(quit_action)

        self.update_for_state(RecordingState.IDLE, can_transcribe=False, mic_available=False)

    def closeEvent(self, event: QCloseEvent) -> None:
        """Hide to tray instead of quitting."""

        if not self._hide_to_tray:
            event.accept()
            return
        event.ignore()
        self.hide()

    def set_hide_to_tray(self, enabled: bool) -> None:
        self._hide_to_tray = enabled

    def update_for_state(self, state: RecordingState, can_transcribe: bool, mic_available: bool) -> None:
        """Keep controls aligned with the controller state."""

        self.state_label.setText(state.value.title())
        can_cancel = can_cancel_current_operation(state)
        self.cancel_button.setVisible(can_cancel)
        self.cancel_button.setEnabled(can_cancel)
        self.record_button.setText("■ STOP" if state == RecordingState.RECORDING else "● REC")

        record_enabled = can_trigger_record_action(state, can_transcribe=can_transcribe, mic_available=mic_available)
        self.record_button.setEnabled(record_enabled)
        self.import_button.setEnabled(can_transcribe and state != RecordingState.RECORDING)
        self.copy_button.setEnabled(state == RecordingState.SUCCESS)
        self.retry_button.setEnabled(state in {RecordingState.SUCCESS, RecordingState.ERROR})
        self.history_button.setEnabled(state != RecordingState.RECORDING)
        if not mic_available:
            self.record_button.setToolTip("No microphone detected")
        elif not can_transcribe:
            self.record_button.setToolTip("Add an API key or custom API base URL in Settings")
        else:
            self.record_button.setToolTip("")

    def set_level(self, rms: float) -> None:
        """Update the VU meter from normalized RMS."""

        clamped = max(0.0, min(rms, 1.0))
        self.level_bar.setValue(int(clamped * 100.0))

    def set_timer_text(self, text: str) -> None:
        """Show elapsed recording time."""

        self.timer_label.setText(text)

    def set_cost_display(self, cost_usd: float) -> None:
        """Update the cost label."""

        self.cost_label.setText(f"${cost_usd:.4f}")


class TinyRecorderController(QObject):
    """Glue between the one-file domain logic and Qt widgets."""

    def __init__(self, app: QApplication, paths: AppPaths, config: AppConfig) -> None:
        super().__init__()
        self._app = app
        self._paths = paths
        self._config = config
        self._state = StateMachine()
        self._recorder = RecorderSession(paths.audio_dir)
        self._transcriber = OpenAITranscriber()
        self._history: list[HistoryEntry] = []
        self._session_cost = 0.0
        self._current_transcript = ""
        self._timer = QTimer(self)
        self._timer.setInterval(200)
        self._timer.timeout.connect(self._update_timer)
        self._done_icon_timer = QTimer(self)
        self._done_icon_timer.setSingleShot(True)
        self._done_icon_timer.timeout.connect(self._clear_done_tray_feedback)
        self._tray_record_action: QAction | None = None
        self._active_task: asyncio.Task[None] | None = None
        self._tray_available = QSystemTrayIcon.isSystemTrayAvailable()
        self._show_done_tray_feedback_active = False

        self.window = MainWindow()
        self.window.language_combo.addItems(list(SUPPORTED_LANGUAGES))
        self.window.model_combo.addItems(list(SUPPORTED_MODELS))

        self._recorder.level_changed.connect(self.window.set_level)
        self.window.record_button.clicked.connect(self.on_record_clicked)
        self.window.cancel_button.clicked.connect(self.on_cancel_clicked)
        self.window.import_button.clicked.connect(self.import_audio)
        self.window.copy_button.clicked.connect(self.copy_transcript)
        self.window.retry_button.clicked.connect(self.on_retry_clicked)
        self.window.history_button.clicked.connect(self.show_history)
        self.window.settings_button.clicked.connect(self.show_settings)
        self.window.quit_requested.connect(self.quit)
        self.window.language_combo.currentTextChanged.connect(self._on_language_changed)
        self.window.model_combo.currentTextChanged.connect(self._on_model_changed)
        self.window.device_combo.currentTextChanged.connect(self._on_device_changed)

        self.tray_icon = QSystemTrayIcon(self._create_app_icon(TrayIconState.IDLE), self)
        self.tray_icon.setToolTip(f"{APP_NAME} {APP_VERSION}")
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.setContextMenu(self._build_tray_menu())
        self.window.set_hide_to_tray(self._tray_available)

        history_result = load_history(paths.history_path)
        if history_result.is_ok:
            self._history = history_result.unwrap()
        self._apply_config_to_ui()
        self.refresh_devices()
        self.refresh_ui()

        recovered = recover_orphaned_pcm(paths.audio_dir)
        if recovered.is_ok and recovered.unwrap():
            recovered_files = recovered.unwrap()
            self.window.transcript_area.setPlainText(
                f"Recovered {len(recovered_files)} orphaned recording(s) from the cache directory."
            )
        elif recovered.is_err:
            self.window.transcript_area.setPlainText(recovered.unwrap_err())

    def _create_app_icon(self, state: TrayIconState) -> QIcon:
        color = TRAY_NEUTRAL_COLOR
        if state == TrayIconState.ERROR:
            color = TRAY_ERROR_COLOR
        elif state == TrayIconState.DONE:
            color = TRAY_DONE_COLOR
        return render_svg_icon(build_tray_icon_svg(state=state, color=color))

    def _build_tray_menu(self) -> QMenu:
        menu = QMenu()
        show_action = menu.addAction("Show/Hide")
        self._tray_record_action = menu.addAction("Record")
        settings_action = menu.addAction("Settings")
        menu.addSeparator()
        quit_action = menu.addAction("Quit")

        show_action.triggered.connect(self.toggle_window_visibility)
        self._tray_record_action.triggered.connect(self.on_record_clicked)
        settings_action.triggered.connect(self.show_settings)
        quit_action.triggered.connect(self.quit)
        return menu

    def _apply_config_to_ui(self) -> None:
        self.window.language_combo.setCurrentText(self._config.language)
        self.window.model_combo.setCurrentText(self._config.model)

    def _on_language_changed(self, language: str) -> None:
        self._config = replace(self._config, language=language)
        save_config(self._config, self._paths.config_path)

    def _on_model_changed(self, model: str) -> None:
        self._config = replace(self._config, model=model)
        save_config(self._config, self._paths.config_path)

    def _on_device_changed(self, device_name: str) -> None:
        self._config = replace(self._config, device=device_name)
        save_config(self._config, self._paths.config_path)

    def _can_transcribe(self) -> bool:
        return can_transcribe_with_config(self._config)

    def can_transcribe(self) -> bool:
        return self._can_transcribe()

    def _has_microphone(self) -> bool:
        return self.window.device_combo.count() > 0

    def refresh_devices(self) -> None:
        result = list_input_devices()
        self.window.device_combo.blockSignals(True)
        self.window.device_combo.clear()
        if result.is_ok:
            devices = result.unwrap()
            self.window.device_combo.addItems(devices)
            if self._config.device and self._config.device in devices:
                self.window.device_combo.setCurrentText(self._config.device)
        self.window.device_combo.blockSignals(False)

    def refresh_ui(self) -> None:
        self.window.update_for_state(self._state.current_state, self._can_transcribe(), self._has_microphone())
        self.window.set_cost_display(self._session_cost)
        tray_state = resolve_tray_icon_state(
            self._state.current_state,
            show_done=self._show_done_tray_feedback_active,
        )
        self.tray_icon.setIcon(self._create_app_icon(tray_state))
        if self._tray_record_action is not None:
            label = "Stop" if self._state.current_state == RecordingState.RECORDING else "Record"
            self._tray_record_action.setText(label)
            self._tray_record_action.setEnabled(
                can_trigger_record_action(
                    self._state.current_state,
                    can_transcribe=self._can_transcribe(),
                    mic_available=self._has_microphone(),
                )
            )

    def toggle_window_visibility(self) -> None:
        if self.window.isVisible():
            self.window.hide()
        else:
            self.window.show()
            self.window.raise_()
            self.window.activateWindow()

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if not self._tray_available:
            return
        if reason == QSystemTrayIcon.ActivationReason.MiddleClick:
            if can_trigger_record_action(
                self._state.current_state,
                can_transcribe=self._can_transcribe(),
                mic_available=self._has_microphone(),
            ):
                self.on_record_clicked()
            return
        if reason in {
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        }:
            self.toggle_window_visibility()

    def _clear_done_tray_feedback(self) -> None:
        self._show_done_tray_feedback_active = False
        self.refresh_ui()

    def _cancel_done_tray_feedback(self) -> None:
        self._done_icon_timer.stop()
        self._show_done_tray_feedback_active = False

    def _show_done_tray_feedback(self) -> None:
        self._show_done_tray_feedback_active = True
        self._done_icon_timer.start(TRAY_DONE_MSEC)

    def on_retry_clicked(self) -> None:
        self._active_task = asyncio.create_task(self.retry_last_audio())

    def on_cancel_clicked(self) -> None:
        if self._state.current_state == RecordingState.RECORDING:
            self.cancel_recording()
            return
        if self._state.current_state != RecordingState.PROCESSING:
            return

        self._cancel_done_tray_feedback()
        if self._active_task is not None and not self._active_task.done():
            self._active_task.cancel()
        self._active_task = None
        self._state.current_state = RecordingState.IDLE
        self.window.transcript_area.setPlainText("Transcription cancelled. Audio file preserved in cache.")
        self.refresh_ui()

    def on_record_clicked(self) -> None:
        if self._state.current_state == RecordingState.RECORDING:
            self._active_task = asyncio.create_task(self.stop_recording())
            return
        if self._state.current_state in {RecordingState.SUCCESS, RecordingState.ERROR}:
            reset = self._state.transition(RecordingState.IDLE)
            if reset.is_err:
                self._show_error(reset.unwrap_err())
                return
        self.start_recording()

    def start_recording(self) -> None:
        self._cancel_done_tray_feedback()
        if not self._can_transcribe():
            self.show_settings()
            return
        transition = self._state.transition(RecordingState.RECORDING)
        if transition.is_err:
            self._show_error(transition.unwrap_err())
            return

        current_device = self.window.device_combo.currentText()
        started = self._recorder.start(current_device)
        if started.is_err:
            self._state.current_state = RecordingState.IDLE
            self._show_error(started.unwrap_err())
            return

        self._state.audio_file_path = started.unwrap().with_suffix(".wav")
        self.window.transcript_area.setPlainText("Recording in progress...")
        self._timer.start()
        self.refresh_ui()

    async def stop_recording(self) -> None:
        transition = self._state.transition(RecordingState.PROCESSING)
        if transition.is_err:
            self._show_error(transition.unwrap_err())
            return
        self._timer.stop()
        self.window.set_timer_text("00:00")
        self.refresh_ui()

        stopped = self._recorder.stop()
        if stopped.is_err:
            self._state.current_state = RecordingState.ERROR
            self.refresh_ui()
            self._show_error(stopped.unwrap_err())
            return

        wav_path = stopped.unwrap()
        self._state.audio_file_path = wav_path
        await self._transcribe_current_audio(wav_path)

    def cancel_recording(self) -> None:
        if self._state.current_state != RecordingState.RECORDING:
            return
        self._cancel_done_tray_feedback()
        self._timer.stop()
        cancelled = self._recorder.cancel()
        self._state.current_state = RecordingState.IDLE
        if cancelled.is_ok:
            self._state.audio_file_path = cancelled.unwrap()
            self.window.transcript_area.setPlainText("Recording cancelled. Audio file preserved in cache.")
        else:
            self.window.transcript_area.setPlainText(cancelled.unwrap_err())
        self.window.set_timer_text("00:00")
        self.window.set_level(0.0)
        self.refresh_ui()

    def import_audio(self) -> None:
        self._cancel_done_tray_feedback()
        if not self._can_transcribe():
            self.show_settings()
            return
        selected, _ = QFileDialog.getOpenFileName(
            self.window,
            "Import audio",
            str(Path.home()),
            "Audio Files (*.wav *.mp3 *.m4a *.flac *.ogg);;All Files (*)",
        )
        if not selected:
            return
        source_path = Path(selected)
        valid = is_supported_audio_path(source_path)
        if valid.is_err:
            self._show_error(valid.unwrap_err())
            return
        copied = copy_into_cache(source_path, self._paths.audio_dir)
        if copied.is_err:
            self._show_error(copied.unwrap_err())
            return
        transition = self._state.transition(RecordingState.PROCESSING)
        if transition.is_err:
            self._show_error(transition.unwrap_err())
            return
        self._state.audio_file_path = copied.unwrap()
        self.refresh_ui()
        self._active_task = asyncio.create_task(self._transcribe_current_audio(copied.unwrap()))

    async def retry_last_audio(self) -> None:
        self._cancel_done_tray_feedback()
        if self._state.audio_file_path is None:
            self._show_error("No audio file available to retry")
            return
        transition = self._state.transition(RecordingState.PROCESSING)
        if transition.is_err:
            self._show_error(transition.unwrap_err())
            return
        self.refresh_ui()
        await self._transcribe_current_audio(self._state.audio_file_path)

    async def _transcribe_current_audio(self, audio_path: Path) -> None:
        self.window.transcript_area.setPlainText("Transcribing...")
        result = await self._transcriber.transcribe(audio_path, self._config)
        if result.is_err:
            self._cancel_done_tray_feedback()
            self._state.current_state = RecordingState.ERROR
            self.window.transcript_area.setPlainText(result.unwrap_err())
            self.refresh_ui()
            return

        transcript = result.unwrap()
        self._current_transcript = transcript.text
        self._session_cost += transcript.cost_estimate
        self.window.transcript_area.setPlainText(transcript.text)
        self._state.current_state = RecordingState.SUCCESS
        self._show_done_tray_feedback()
        self.refresh_ui()

        history_entry = HistoryEntry(
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            audio_file=audio_path.name,
            transcript=transcript.text,
            language=transcript.language,
            model=transcript.model,
            duration_sec=transcript.duration_sec,
            noise_reduction=self._config.noise_reduction,
        )
        appended = append_history_entry(self._paths.history_path, history_entry)
        if appended.is_ok:
            self._history.insert(0, history_entry)

        if self._config.auto_copy:
            clipboard = QGuiApplication.clipboard()
            clipboard.setText(transcript.text)

    def copy_transcript(self) -> None:
        if not self._current_transcript:
            return
        QGuiApplication.clipboard().setText(self._current_transcript)

    def show_settings(self) -> None:
        dialog = SettingsDialog(self._config, self._paths.audio_dir, self.window)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        updated = dialog.updated_config()
        saved = save_config(updated, self._paths.config_path)
        if saved.is_err:
            self._show_error(saved.unwrap_err())
            return
        self._config = updated
        self.refresh_ui()

    def show_history(self) -> None:
        self._cancel_done_tray_feedback()
        dialog = HistoryDialog(self._history, self.window)
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.selected_entry is None:
            return
        entry = dialog.selected_entry
        self._current_transcript = entry.transcript
        self.window.transcript_area.setPlainText(entry.transcript)
        self._state.audio_file_path = self._paths.audio_dir / entry.audio_file
        self._state.current_state = RecordingState.SUCCESS
        self.refresh_ui()

    def _update_timer(self) -> None:
        if self._state.current_state != RecordingState.RECORDING:
            return
        elapsed = max(0, int(time.monotonic() - self._recorder.started_at))
        minutes, seconds = divmod(elapsed, 60)
        self.window.set_timer_text(f"{minutes:02d}:{seconds:02d}")

    def _show_error(self, message: str) -> None:
        self.window.transcript_area.setPlainText(message)
        self.refresh_ui()
        QMessageBox.warning(self.window, APP_NAME, message)

    def show(self) -> None:
        if self._tray_available:
            self.tray_icon.show()
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    def quit(self) -> None:
        if self._state.current_state == RecordingState.RECORDING:
            self._recorder.cancel()
        if self._tray_available:
            self.tray_icon.hide()
        self._app.quit()


def build_stylesheet() -> str:
    """Place styles here"""

    return ""


def create_application() -> QApplication:
    """Create or reuse the QApplication instance."""

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    if not isinstance(app, QApplication):
        raise RuntimeError("Expected QApplication instance")
    app.setApplicationName(APP_ID)
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setDesktopFileName(APP_ID)
    fallback_icon = render_svg_icon(build_tray_icon_svg(state=TrayIconState.IDLE, color=TRAY_NEUTRAL_COLOR), size=64)
    app.setWindowIcon(QIcon.fromTheme(APP_ID, fallback_icon))
    app.setStyleSheet(build_stylesheet())
    return app


def _sigint_handler(*_args: object) -> None:
    QApplication.quit()


def configure_platform_environment() -> None:
    """Apply platform-specific environment defaults before Qt starts."""

    if sys.platform.startswith("linux") and "QT_QPA_PLATFORMTHEME" not in os.environ:
        os.environ["QT_QPA_PLATFORMTHEME"] = "xdgdesktopportal"


def bootstrap() -> AppResult[TinyRecorderController]:
    """Prepare filesystem, config, Qt app, and controller."""

    paths = resolve_app_paths()
    prepared = ensure_app_dirs(paths)
    if prepared.is_err:
        return Err(prepared.unwrap_err())

    config_result = load_config(paths.config_path)
    if config_result.is_err:
        return Err(config_result.unwrap_err())

    app = create_application()
    controller = TinyRecorderController(app, paths, config_result.unwrap())
    return Ok(controller)


def main() -> int:
    """Run the Qt app under qasync."""

    configure_platform_environment()

    controller_result = bootstrap()
    if controller_result.is_err:
        print(f"Error: {controller_result.unwrap_err()}", file=sys.stderr)
        return 1

    controller = controller_result.unwrap()
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        print("Error: QApplication failed to initialize", file=sys.stderr)
        return 1

    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)
    signal.signal(signal.SIGINT, _sigint_handler)

    timer = QTimer()
    timer.start(200)
    timer.timeout.connect(lambda: None)

    controller.show()
    if not controller.can_transcribe():
        controller.show_settings()

    with loop:
        loop.run_forever()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130) from None
