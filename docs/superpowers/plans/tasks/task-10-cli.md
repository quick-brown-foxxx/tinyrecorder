# Task 10: CLI

**Phase:** 6 (sequential, after Tasks 8 + 11)
**Dependencies:** Task 2, Task 8, Task 11
**Skills:** `writing-python-code`, `building-multi-ui-apps`, `testing-python`
**Files to create:** `src/cli.py`, `src/__main__.py`
**Test files:** `tests/integration/test_cli.py`
**Estimated complexity:** medium

---

**Goal:** Create the typer CLI with `transcribe`, `record-toggle`, `record-cancel`, and `status` commands, plus the `__main__.py` entry point.

> **Note (CLI `app` alias):** The module exports `app` (the typer app). Tests import it as `from tinyrecorder.cli import app as cli_app` for clarity, to avoid shadowing pytest's app fixtures. This is the standardized convention.

#### Steps

- [ ] Create `tests/integration/test_cli.py`:

```python
"""Integration tests for the CLI.

Uses typer.testing.CliRunner for in-process testing
and pytest-httpserver for mock OpenAI API.
"""

from __future__ import annotations

import json
import struct
import wave
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pytest
from pytest_httpserver import HTTPServer
from typer.testing import CliRunner
from werkzeug.wrappers import Request, Response

from tinyrecorder.cli import app as cli_app

if TYPE_CHECKING:
    pass


runner = CliRunner()


@pytest.fixture()
def sample_wav(tmp_path: Path) -> Path:
    """Create a real 1-second 16kHz mono WAV file with a 440Hz sine tone."""
    filepath = tmp_path / "test_audio.wav"
    sample_rate = 16000
    duration = 1.0
    t = np.linspace(0.0, duration, int(sample_rate * duration), endpoint=False)
    samples = (np.sin(2 * np.pi * 440 * t) * 32767 * 0.5).astype(np.int16)

    with wave.open(str(filepath), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(samples.tobytes())

    return filepath


@pytest.fixture()
def corrupt_file(tmp_path: Path) -> Path:
    """Create a file with random bytes (not valid audio)."""
    filepath = tmp_path / "corrupt.wav"
    filepath.write_bytes(b"\x00\xde\xad\xbe\xef" * 100)
    return filepath


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


def _write_config(config_dir: Path, api_key: str, base_url: str = "") -> Path:
    """Write a config.toml with given API key and optional base_url."""
    app_config_dir = config_dir / "tinyrecorder"
    app_config_dir.mkdir(parents=True, exist_ok=True)
    config_path = app_config_dir / "config.toml"

    lines = [
        "[api]",
        f'key = "{api_key}"',
        'model = "gpt-4o-mini-transcribe"',
    ]
    if base_url:
        lines.append(f'base_url = "{base_url}"')

    lines.extend([
        "",
        "[recording]",
        'language = "auto"',
        "noise_reduction = false",
        "sample_rate = 16000",
        'device = ""',
        "",
        "[app]",
        "auto_copy = false",
    ])

    config_path.write_text("\n".join(lines))
    return config_path


def test_cli_transcribe_file_success(
    httpserver: HTTPServer,
    sample_wav: Path,
    config_dir: Path,
    cache_dir: Path,
    data_dir: Path,
) -> None:
    """tinyrecorder transcribe FILE sends audio to API and prints transcript."""
    httpserver.expect_request(
        "/v1/audio/transcriptions",
        method="POST",
    ).respond_with_json({"text": "Hello world from Whisper"})

    _write_config(config_dir, "sk-test-key", httpserver.url_for(""))

    result = runner.invoke(cli_app, ["transcribe", str(sample_wav)])
    assert result.exit_code == 0, f"stderr: {result.output}"
    assert "Hello world from Whisper" in result.output


def test_cli_transcribe_missing_api_key(
    sample_wav: Path,
    config_dir: Path,
    cache_dir: Path,
    data_dir: Path,
) -> None:
    """tinyrecorder transcribe FILE fails when no API key is configured."""
    _write_config(config_dir, "")

    result = runner.invoke(cli_app, ["transcribe", str(sample_wav)])
    assert result.exit_code != 0
    assert "api key" in result.output.lower() or "api key" in (result.stderr or "").lower()


def test_cli_transcribe_invalid_file(
    config_dir: Path,
    cache_dir: Path,
    data_dir: Path,
) -> None:
    """tinyrecorder transcribe nonexistent.wav fails with clear error."""
    _write_config(config_dir, "sk-test-key")

    result = runner.invoke(cli_app, ["transcribe", "/nonexistent/path/audio.wav"])
    assert result.exit_code != 0
    assert "not found" in result.output.lower() or "no such file" in result.output.lower()


def test_cli_transcribe_corrupt_file(
    corrupt_file: Path,
    config_dir: Path,
    cache_dir: Path,
    data_dir: Path,
) -> None:
    """tinyrecorder transcribe FILE rejects a file that is not valid audio."""
    _write_config(config_dir, "sk-test-key")

    result = runner.invoke(cli_app, ["transcribe", str(corrupt_file)])
    assert result.exit_code != 0
    assert "format" in result.output.lower() or "corrupt" in result.output.lower()


def test_cli_transcribe_api_error_401(
    httpserver: HTTPServer,
    sample_wav: Path,
    config_dir: Path,
    cache_dir: Path,
    data_dir: Path,
) -> None:
    """tinyrecorder transcribe FILE reports invalid API key on 401."""
    httpserver.expect_request(
        "/v1/audio/transcriptions",
        method="POST",
    ).respond_with_json(
        {"error": {"message": "Invalid API key", "type": "invalid_request_error"}},
        status=401,
    )

    _write_config(config_dir, "sk-bad-key", httpserver.url_for(""))

    result = runner.invoke(cli_app, ["transcribe", str(sample_wav)])
    assert result.exit_code != 0
    assert "api key" in result.output.lower() or "401" in result.output.lower()


def test_cli_transcribe_api_error_429_retry(
    httpserver: HTTPServer,
    sample_wav: Path,
    config_dir: Path,
    cache_dir: Path,
    data_dir: Path,
) -> None:
    """tinyrecorder transcribe FILE retries on 429, succeeds on second attempt."""
    request_count: list[int] = [0]

    def handler(request: Request) -> Response:
        request_count[0] += 1
        if request_count[0] == 1:
            return Response(
                json.dumps({"error": {"message": "Rate limited", "type": "rate_limit_error"}}),
                status=429,
                content_type="application/json",
            )
        return Response(
            json.dumps({"text": "Retry succeeded"}),
            status=200,
            content_type="application/json",
        )

    httpserver.expect_request(
        "/v1/audio/transcriptions",
        method="POST",
    ).respond_with_handler(handler)

    _write_config(config_dir, "sk-test-key", httpserver.url_for(""))

    result = runner.invoke(cli_app, ["transcribe", str(sample_wav)])
    assert result.exit_code == 0, f"output: {result.output}"
    assert "Retry succeeded" in result.output
    assert request_count[0] == 2


def test_cli_transcribe_language_and_model_flags(
    httpserver: HTTPServer,
    sample_wav: Path,
    config_dir: Path,
    cache_dir: Path,
    data_dir: Path,
) -> None:
    """--lang and --model flags are forwarded to the API request."""
    received_data: dict[str, str] = {}

    def handler(request: Request) -> Response:
        # Extract form fields from multipart
        if request.form:
            received_data["language"] = request.form.get("language", "")
            received_data["model"] = request.form.get("model", "")
        return Response(
            json.dumps({"text": "Flagged transcription"}),
            status=200,
            content_type="application/json",
        )

    httpserver.expect_request(
        "/v1/audio/transcriptions",
        method="POST",
    ).respond_with_handler(handler)

    _write_config(config_dir, "sk-test-key", httpserver.url_for(""))

    result = runner.invoke(cli_app, [
        "transcribe", str(sample_wav),
        "--lang", "en",
        "--model", "whisper-1",
    ])
    assert result.exit_code == 0, f"output: {result.output}"
    assert received_data.get("language") == "en"
    assert received_data.get("model") == "whisper-1"


def test_cli_status_no_running_instance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """tinyrecorder status fails gracefully when no GUI instance is running."""
    # Point to a tmp runtime dir with no socket
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))

    result = runner.invoke(cli_app, ["status"])
    assert result.exit_code != 0
    assert "not running" in result.output.lower() or "no running" in result.output.lower()


def test_cli_record_toggle_no_running_instance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """tinyrecorder record-toggle fails when no GUI instance is running."""
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))

    result = runner.invoke(cli_app, ["record-toggle"])
    assert result.exit_code != 0
    assert "not running" in result.output.lower() or "no running" in result.output.lower()
```

- [ ] Run tests and confirm they fail:

```bash
uv run pytest tests/integration/test_cli.py -x -v 2>&1 | head -50
```

- [ ] At CLI startup (before any command runs), set up file logging only (NOT stdout logging -- CLI uses stdout for user output):

```python
import logging
from tinyrecorder.shared.logging import setup_file_logging
from tinyrecorder.platform import get_user_directories

setup_file_logging(log_dir=get_user_directories().data_dir / "logs", app_name="tinyrecorder")
```

- [ ] Create `src/cli.py` -- same as original plan but with standardized import pattern:

The module defines `app = typer.Typer(...)`. Tests import as `from tinyrecorder.cli import app as cli_app`.

- [ ] Create `src/__main__.py`:

```python
"""Entry point for `python -m src` or `tinyrecorder` console script."""

from tinyrecorder.cli import app

if __name__ == "__main__":
    app()
```

- [ ] Run tests and confirm they pass:

```bash
uv run pytest tests/integration/test_cli.py -x -v 2>&1 | head -80
```

- [ ] Commit: `feat(cli): add typer CLI with transcribe, record-toggle, record-cancel, status commands`
