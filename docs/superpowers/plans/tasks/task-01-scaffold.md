# Task 1: Project Scaffold + Constants

**Phase:** 1 (sequential)
**Dependencies:** None
**Skills:** `setting-up-python-projects`, `writing-python-code`
**Files to create:** `pyproject.toml`, `.pre-commit-config.yaml`, `.gitignore`, `.vscode/settings.json`, `.vscode/extensions.json`, `AGENTS.md`, `CLAUDE.md` (symlink), `docs/PHILOSOPHY.md`, `docs/coding_rules.md`, `scripts/bootstrap.py`, `src/tinyrecorder/__init__.py`, `src/tinyrecorder/__main__.py`, `src/tinyrecorder/constants.py`, `src/tinyrecorder/config.py`, `src/tinyrecorder/state.py`, `src/tinyrecorder/history.py`, `src/tinyrecorder/cli.py`, `src/tinyrecorder/ipc.py`, `src/tinyrecorder/platform/__init__.py`, `src/tinyrecorder/platform/protocols.py`, `src/tinyrecorder/platform/linux.py`, `src/tinyrecorder/audio/__init__.py`, `src/tinyrecorder/audio/devices.py`, `src/tinyrecorder/audio/recorder.py`, `src/tinyrecorder/audio/processor.py`, `src/tinyrecorder/audio/device_wrapper.py`, `src/tinyrecorder/transcription/__init__.py`, `src/tinyrecorder/transcription/provider.py`, `src/tinyrecorder/transcription/openai_provider.py`, `src/tinyrecorder/ui/__init__.py`, `src/tinyrecorder/ui/app.py`, `src/tinyrecorder/ui/main_window.py`, `src/tinyrecorder/ui/widgets.py`, `src/tinyrecorder/ui/styles.py`, `src/tinyrecorder/ui/settings_dialog.py`, `src/tinyrecorder/shared/__init__.py`, `src/tinyrecorder/shared/logging/__init__.py`, `src/tinyrecorder/shared/logging/logger_setup.py`, `src/tinyrecorder/shared/logging/non_log_stdout_output.py`, `tests/__init__.py`, `tests/unit/__init__.py`, `tests/integration/__init__.py`, `tests/fixtures/__init__.py`, `tests/conftest.py`
**Test files:** `tests/conftest.py` (shared fixtures only, no test cases)
**Estimated complexity:** small

---

> **CRITICAL: Import path convention.** The package layout is `src/tinyrecorder/`. ALL imports across ALL tasks must use `from tinyrecorder.<module> import ...` — NOT `from src.<module> import ...`. For example: `from tinyrecorder.config import AppConfig`, `from tinyrecorder.audio.recorder import AudioRecorder`, etc. The `src/` prefix is never part of import paths.

**Goal:** Create the project skeleton with all dependencies, tooling config, project docs, constants, and shared test fixtures.

- [ ] Create directory structure:

```bash
mkdir -p src/tinyrecorder/audio \
         src/tinyrecorder/transcription \
         src/tinyrecorder/ui \
         src/tinyrecorder/platform \
         src/tinyrecorder/shared/logging \
         tests/unit tests/integration tests/fixtures \
         .vscode docs scripts
```

- [ ] Create `pyproject.toml`:

```toml
[project]
name = "tinyrecorder"
description = "Compact PySide6 system tray speech-to-text app for Linux"
version = "0.1.0"
license = { text = "GPL-3.0" }
requires-python = ">=3.12"
dependencies = [
    "rusty-results>=1.1.2",
    "colorlog>=6.10.1",
    "PySide6>=6.9.0",
    "qasync>=0.27.1",
    "sounddevice>=0.5.1",
    "soundfile>=0.13.1",
    "numpy>=2.2.4",
    "scipy>=1.15.2",
    "noisereduce>=3.0.3",
    "openai>=1.75.0",
    "httpx>=0.28.1",
    "typer>=0.15.2",
    "tomli-w>=1.2.0",
    "pydub>=0.25.1",
]

[project.scripts]
tinyrecorder = "tinyrecorder.__main__:main"

[dependency-groups]
dev = [
    "pytest>=9.0.1",
    "pytest-xdist>=3.5.0",
    "pytest-cov>=7.0.0",
    "pytest-asyncio>=1.3.0",
    "pytest-qt>=4.5.0",
    "pytest-httpserver>=1.1.0",
    "ruff>=0.14.6",
    "basedpyright>=1.34.0",
    "pre-commit",
    "poethepoet",
]

[build-system]
build-backend = "hatchling.build"
requires = ["hatchling"]

[tool.hatch.build.targets.wheel]
packages = ["src/tinyrecorder"]

[tool.pyrigt]
pythonPlatform = "Linux"
pythonVersion = "3.12"
venvPath = "."
venv = ".venv"
typeCheckingMode = "strict"
reportAny = "error"
reportExplicitAny = "error"
reportImplicitStringConcatenation = "none"
reportUnusedCallResult = "none"
reportUnnecessaryIsInstance = "none"
reportUnnecessaryTypeIgnoreComment = "error"
reportMissingModuleSource = "error"
reportPrivateUsage = "error"
reportOptionalMemberAccess = "error"
reportOptionalCall = "error"
reportAttributeAccessIssue = "error"
exclude = [
    "**/__pycache__",
    ".venv",
    "venv",
    "build",
    "dist",
]

[tool.ruff]
line-length = 120
target-version = "py312"
extend-exclude = [
    "venv", ".venv", "*.egg", "*.egg-info",
    "**/dist", "**/build", "**/__pycache__",
    ".git", ".pytest_cache",
]

[tool.ruff.lint]
extend-select = [
    "E", "F", "W",
    "I",
    "N",
    "UP",
    "ASYNC",
    "S",
    "B",
    "A",
    "C4",
    "SIM",
    "PT",
    "PERF",
    "RUF",
]
ignore = [
    "N802",   # Qt event handlers use camelCase
    "S101",   # assert usage (needed in tests and preconditions)
    "RUF001", # ambiguous unicode (Russian text)
]

[tool.ruff.lint.per-file-ignores]
"tests/*" = ["S101", "PT018"]

[tool.ruff.lint.flake8-tidy-imports.banned-api]
"sounddevice" = { msg = "Use src/tinyrecorder/audio/devices or src/tinyrecorder/audio/recorder instead" }
"noisereduce" = { msg = "Use src/tinyrecorder/audio/processor instead" }

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
asyncio_mode = "auto"
addopts = ["-n", "auto", "--dist", "worksteal", "-m", "not e2e"]
markers = [
    "unit: unit tests",
    "integration: integration tests",
    "e2e: end-to-end tests (requires qt-ai-dev-tools VM)",
]

[tool.poe.tasks]
test = "pytest"
app = "python -m tinyrecorder"

[tool.poe.tasks.lint_full]
shell = "basedpyright . && ruff check --fix . && ruff format ."
```

- [ ] Create `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: local
    hooks:
      - id: uv-sync
        name: uv-sync
        entry: uv sync --quiet
        language: system
        always_run: true
        pass_filenames: false
      - id: ruff
        name: ruff
        entry: uv run ruff check --fix
        language: system
        types: [python]
      - id: ruff-format
        name: ruff-format
        entry: uv run ruff format
        language: system
        types: [python]
      - id: basedpyright
        name: basedpyright
        entry: uv run basedpyright
        language: system
        types: [python]
        pass_filenames: true
        stages: [pre-commit]
```

- [ ] Create `.gitignore`:

```gitignore
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
*.egg
*.egg-info/
dist/
build/

# Virtual environments
.venv/
venv/

# IDE
.idea/
*.swp
*.swo
*~

# Testing
.pytest_cache/
htmlcov/
.coverage
coverage.xml

# Environment
.env
.env.*

# OS
.DS_Store
Thumbs.db

# uv
uv.lock
```

- [ ] Create `.vscode/settings.json`:

```json
{
    "python.defaultInterpreterPath": "${workspaceFolder}/.venv/bin/python",
    "python.analysis.typeCheckingMode": "off",
    "[python]": {
        "editor.defaultFormatter": "charliermarsh.ruff",
        "editor.formatOnSave": true,
        "editor.codeActionsOnSave": {
            "source.fixAll": "explicit",
            "source.organizeImports": "explicit"
        }
    },
    "basedpyright.analysis.typeCheckingMode": "strict",
    "ruff.lineLength": 120,
    "files.exclude": {
        "**/__pycache__": true,
        "**/*.pyc": true,
        ".venv": true
    }
}
```

- [ ] Create `.vscode/extensions.json`:

```json
{
    "recommendations": [
        "charliermarsh.ruff",
        "detachhead.basedpyright",
        "ms-python.python"
    ]
}
```

- [ ] Create `AGENTS.md`:

```markdown
# TinyRecorder — Agent Instructions

## Project Overview

TinyRecorder is a compact PySide6 system tray speech-to-text application for Linux.
It records audio from the microphone, applies noise reduction, sends it to OpenAI's
transcription API, and copies the result to the clipboard.

## Key Decisions

- **Package layout:** `src/tinyrecorder/` — all imports use `from tinyrecorder.<module> import ...`
- **Error handling:** Result-based (`rusty-results`) — no bare exceptions, no silent swallowing
- **Type checking:** basedpyright strict mode — `reportAny = "error"`, `reportExplicitAny = "error"`
- **Linting:** ruff with extended rule set (see pyproject.toml)
- **Testing:** pytest with xdist parallelism, pytest-qt for UI, pytest-httpserver for API mocking
- **Async:** qasync event loop integration for PySide6 + asyncio
- **Architecture:** Manager → Service → Wrapper layering for Qt components

## References

- `docs/PHILOSOPHY.md` — project philosophy and design principles
- `docs/coding_rules.md` — coding standards and conventions
- `docs/superpowers/plans/` — implementation plan and task breakdowns

## Skills

When working on this project, load these skills before writing code:

- `writing-python-code` — for any Python code
- `building-qt-apps` — for PySide6/Qt code
- `testing-python` — for tests
- `setting-up-python-projects` — for project config changes
- `setting-up-logging` — for logging setup
```

- [ ] Create `CLAUDE.md` as symlink:

```bash
ln -s AGENTS.md CLAUDE.md
```

- [ ] Create `docs/PHILOSOPHY.md`:

```markdown
# Project Philosophy

## Core Principles

1. **Correctness over convenience.** Type safety, strict checking, and explicit error handling
   are non-negotiable. If basedpyright complains, fix the code — do not weaken the config.

2. **Result-based error handling.** Use `rusty-results` `Result[T, E]` for all fallible operations.
   Exceptions are for truly exceptional situations (programmer errors, corrupted state).

3. **No Any.** The type checker is configured to reject `Any`. If you need dynamic typing,
   use `object` or a protocol. If a library returns `Any`, wrap it and cast explicitly.

4. **Small, focused modules.** Each file should do one thing. If a module grows beyond ~200 lines,
   it likely needs splitting.

5. **Tests are first-class.** Every module gets tests. Use fixtures, not setup methods.
   Mock at boundaries, not internals.

## Architecture

- **src layout:** `src/tinyrecorder/` with subpackages for `audio`, `transcription`, `ui`, `shared`
- **Manager → Service → Wrapper** for Qt components (see `building-qt-apps` skill)
- **qasync** for bridging Qt event loop with asyncio
- **Single-instance** enforcement via Unix domain socket IPC
```

- [ ] Create `docs/coding_rules.md`:

```markdown
# Coding Rules

## Type Annotations

- All functions must have full type annotations (parameters + return type)
- Use `Final` for constants
- Use `TypeAlias` or `type` statements for complex types
- No `Any` — use `object`, protocols, or explicit casts

## Error Handling

- Use `Result[T, E]` from `rusty-results` for fallible operations
- Define specific error types per module (dataclasses, not exceptions)
- Pattern: `result = do_thing(); if result.is_err: return Err(...)`
- Reserve exceptions for: programmer errors, corrupt state, unrecoverable situations

## Imports

- Use absolute imports: `from tinyrecorder.audio.recorder import AudioRecorder`
- Never use `from src.` prefix — `src/` is the source root, not a package
- Group: stdlib → third-party → local, separated by blank lines (ruff handles this)

## Naming

- `snake_case` for functions, methods, variables, modules
- `PascalCase` for classes, type aliases
- `UPPER_SNAKE_CASE` for constants
- Qt event handler overrides may use `camelCase` (suppressed via `N802`)

## Testing

- Test files: `tests/unit/test_<module>.py`, `tests/integration/test_<feature>.py`
- Use fixtures from `conftest.py`, not setUp/tearDown
- Use `pytest-httpserver` for API mocking, not `unittest.mock.patch` on HTTP clients
- Use `pytest-qt` with session-scoped `qapp` fixture for UI tests

## Code Style

- Line length: 120 characters
- Format with `ruff format`, lint with `ruff check --fix`
- Type check with `basedpyright`
- Run all three via `uv run poe lint_full`
```

- [ ] Create `scripts/bootstrap.py`:

```python
#!/usr/bin/env python3
"""Bootstrap script: install uv, sync deps, install pre-commit hooks."""

import subprocess
import sys


def run(cmd: list[str]) -> None:
    print(f"  → {' '.join(cmd)}")
    subprocess.check_call(cmd)


def main() -> None:
    print("Bootstrapping TinyRecorder development environment...\n")

    print("[1/3] Syncing dependencies with uv...")
    run(["uv", "sync", "--group", "dev"])

    print("[2/3] Installing pre-commit hooks...")
    run(["uv", "run", "pre-commit", "install"])

    print("[3/3] Running initial lint check...")
    run(["uv", "run", "poe", "lint_full"])

    print("\nBootstrap complete.")


if __name__ == "__main__":
    main()
```

- [ ] Create `src/tinyrecorder/__init__.py`:

```python
__version__ = "0.1.0"
```

- [ ] Create `src/tinyrecorder/constants.py`:

```python
"""App-wide constants: app name, default config values, audio defaults, supported models and languages.

Platform-specific paths (config dir, cache dir, data dir, socket path) are NOT defined here.
Use UserDirectories from tinyrecorder.platform for all path resolution.
"""

from typing import Final

APP_NAME: Final = "tinyrecorder"

# Audio defaults
SAMPLE_RATE: Final = 16000
CHANNELS: Final = 1
DTYPE: Final = "int16"
BLOCK_SIZE: Final = 1600  # 100ms at 16kHz

# Supported models
SUPPORTED_MODELS: Final[tuple[str, ...]] = (
    "gpt-4o-mini-transcribe",
    "gpt-4o-transcribe",
    "whisper-1",
)
DEFAULT_MODEL: Final = "gpt-4o-mini-transcribe"

# Supported languages
SUPPORTED_LANGUAGES: Final[tuple[str, ...]] = (
    "auto",
    "en",
    "ru",
)
DEFAULT_LANGUAGE: Final = "auto"
```

- [ ] Create logging infrastructure in `src/tinyrecorder/shared/`:

- [ ] Create `src/tinyrecorder/shared/__init__.py`:

```python
# src/tinyrecorder/shared/__init__.py — empty
```

- [ ] Create `src/tinyrecorder/shared/logging/__init__.py`:

```python
"""Reusable logging setup: file logging, stdout logging, non-log output."""

from tinyrecorder.shared.logging.logger_setup import (
    configure_logger_level,
    setup_file_logging,
    setup_stdout_logging,
)
from tinyrecorder.shared.logging.non_log_stdout_output import (
    write_error,
    write_info,
    write_success,
    write_warning,
)

__all__ = [
    "configure_logger_level",
    "setup_file_logging",
    "setup_stdout_logging",
    "write_error",
    "write_info",
    "write_success",
    "write_warning",
]
```

- [ ] Create `src/tinyrecorder/shared/logging/logger_setup.py`:

```python
"""Logger setup: file logging with rotation, colored stdout logging."""

import logging
from pathlib import Path

import colorlog
from logging.handlers import RotatingFileHandler


def setup_file_logging(
    log_dir: Path,
    app_name: str = "app",
    level: int = logging.DEBUG,
    max_bytes: int = 5_000_000,
    backup_count: int = 3,
) -> None:
    """Add RotatingFileHandler to root logger.

    Args:
        log_dir: Directory for log files (created if missing).
        app_name: Log file name prefix (produces <app_name>.log).
        level: Logging level for the file handler.
        max_bytes: Max size per log file before rotation.
        backup_count: Number of rotated backup files to keep.
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{app_name}.log"

    handler = RotatingFileHandler(
        log_path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    handler.setLevel(level)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logging.getLogger().addHandler(handler)


def setup_stdout_logging(level: int = logging.INFO) -> None:
    """Add colored StreamHandler to root logger (GUI/server only, NOT CLI).

    Args:
        level: Logging level for the stdout handler.
    """
    handler = colorlog.StreamHandler()
    handler.setLevel(level)
    formatter = colorlog.ColoredFormatter(
        "%(log_color)s%(levelname)-8s%(reset)s | %(name)s | %(message)s",
        log_colors={
            "DEBUG": "cyan",
            "INFO": "green",
            "WARNING": "yellow",
            "ERROR": "red",
            "CRITICAL": "bold_red",
        },
    )
    handler.setFormatter(formatter)
    logging.getLogger().addHandler(handler)


def configure_logger_level(
    logger_name: str,
    level: int,
    propagate: bool = True,
) -> None:
    """Set a specific logger's level.

    Args:
        logger_name: Dotted logger name (e.g. "httpx", "openai").
        level: Logging level to set.
        propagate: Whether the logger propagates to parent.
    """
    logger = logging.getLogger(logger_name)
    logger.setLevel(level)
    logger.propagate = propagate
```

- [ ] Create `src/tinyrecorder/shared/logging/non_log_stdout_output.py`:

```python
"""Non-log stdout/stderr output with color for CLI user-facing messages.

These functions write directly to stdout/stderr, bypassing the logging system.
Use for user-facing CLI output that should not appear in log files.
"""

import sys


def write_info(message: str) -> None:
    """Write an informational message to stdout in green."""
    sys.stdout.write(f"\033[32m{message}\033[0m\n")
    sys.stdout.flush()


def write_success(message: str) -> None:
    """Write a success message to stdout in green."""
    sys.stdout.write(f"\033[32m{message}\033[0m\n")
    sys.stdout.flush()


def write_warning(message: str) -> None:
    """Write a warning message to stdout in yellow."""
    sys.stdout.write(f"\033[33m{message}\033[0m\n")
    sys.stdout.flush()


def write_error(message: str) -> None:
    """Write an error message to stderr in red."""
    sys.stderr.write(f"\033[31m{message}\033[0m\n")
    sys.stderr.flush()
```

- [ ] Create empty placeholder files for all remaining modules:

```python
# src/tinyrecorder/__main__.py — placeholder
# src/tinyrecorder/config.py — placeholder
# src/tinyrecorder/state.py — placeholder
# src/tinyrecorder/history.py — placeholder
# src/tinyrecorder/cli.py — placeholder
# src/tinyrecorder/ipc.py — placeholder
# src/tinyrecorder/platform/__init__.py — placeholder
# src/tinyrecorder/platform/protocols.py — placeholder
# src/tinyrecorder/platform/linux.py — placeholder
# src/tinyrecorder/audio/__init__.py — empty
# src/tinyrecorder/audio/devices.py — placeholder
# src/tinyrecorder/audio/recorder.py — placeholder
# src/tinyrecorder/audio/processor.py — placeholder
# src/tinyrecorder/audio/device_wrapper.py — placeholder
# src/tinyrecorder/transcription/__init__.py — empty
# src/tinyrecorder/transcription/provider.py — placeholder
# src/tinyrecorder/transcription/openai_provider.py — placeholder
# src/tinyrecorder/ui/__init__.py — empty
# src/tinyrecorder/ui/app.py — placeholder
# src/tinyrecorder/ui/main_window.py — placeholder
# src/tinyrecorder/ui/widgets.py — placeholder
# src/tinyrecorder/ui/styles.py — placeholder
# src/tinyrecorder/ui/settings_dialog.py — placeholder
# tests/__init__.py — empty
# tests/unit/__init__.py — empty
# tests/integration/__init__.py — empty
# tests/fixtures/__init__.py — empty
```

- [ ] Create `tests/conftest.py` with shared fixtures (including session-scoped `qapp` fixture for UI tests):

```python
"""Shared fixtures for all tests."""

import struct
import sys
import wave
from pathlib import Path

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    """Shared QApplication for all UI tests.

    Session-scoped to avoid creating multiple QApplication instances
    (Qt only allows one per process).
    """
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


@pytest.fixture()
def tmp_config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Temporary config directory with XDG_CONFIG_HOME pointed here."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_dir))
    return config_dir


@pytest.fixture()
def tmp_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Temporary data directory with XDG_DATA_HOME pointed here."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("XDG_DATA_HOME", str(data_dir))
    return data_dir


@pytest.fixture()
def tmp_cache_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Temporary cache directory with XDG_CACHE_HOME pointed here."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache_dir))
    return cache_dir


@pytest.fixture()
def sample_pcm_data() -> bytes:
    """1 second of 440Hz sine wave as raw PCM: 16kHz mono int16."""
    sample_rate = 16000
    duration = 1.0
    t = np.linspace(0.0, duration, int(sample_rate * duration), endpoint=False)
    samples = (np.sin(2.0 * np.pi * 440.0 * t) * 32767).astype(np.int16)
    return samples.tobytes()


@pytest.fixture()
def sample_wav_file(tmp_path: Path, sample_pcm_data: bytes) -> Path:
    """Real WAV file: 1 second of 440Hz sine wave, 16kHz mono int16."""
    wav_path = tmp_path / "sample.wav"
    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit = 2 bytes
        wf.setframerate(16000)
        wf.writeframes(sample_pcm_data)
    return wav_path


@pytest.fixture()
def corrupt_audio_file(tmp_path: Path) -> Path:
    """File with random bytes, not valid audio."""
    corrupt_path = tmp_path / "corrupt.wav"
    corrupt_path.write_bytes(b"\x00\xde\xad\xbe\xef" * 200)
    return corrupt_path
```

- [ ] Run `uv sync --group dev` to install all dependencies

- [ ] Verify scaffold:

```bash
uv sync --group dev
uv run pre-commit install
uv run poe lint_full
```

- [ ] Commit: `chore(scaffold): project skeleton with deps, tooling, constants, and test fixtures`
