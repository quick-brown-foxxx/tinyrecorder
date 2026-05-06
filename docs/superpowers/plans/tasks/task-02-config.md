# Task 2: Config (TOML load/save)

**Phase:** 2 (parallel with: Task 3)
**Dependencies:** Task 1, Task 2b (needs `UserDirectories` from platform layer)
**Skills:** `writing-python-code`, `testing-python`
**Files to create:** `src/config.py`
**Test files:** `tests/unit/test_config.py`
**Estimated complexity:** medium

---

**Goal:** Implement TOML-backed config with dataclass, load/save/create-default, and validation. Config file path is provided by `UserDirectories.config_dir` (from platform layer) rather than hardcoded XDG paths.

> **Note (TOML vs QSettings):** This project uses TOML config files instead of Qt QSettings (as recommended by the building-qt-apps skill). Rationale: TOML is human-readable, version-controllable, cross-platform without Qt dependency, and aligns with Python ecosystem conventions. QSettings is registry-based on some platforms and harder to debug.

> **Note (paths):** Config does NOT import paths from `constants.py`. Instead, `load_config()` and `save_config()` receive the config file path as a parameter. The caller (startup code) obtains the path via `UserDirectories.config_dir / "config.toml"`. This keeps config platform-agnostic — it just reads/writes TOML at whatever path it's given.

#### 2a. Write failing tests

- [ ] Create `tests/unit/test_config.py`:

```python
"""Tests for TOML config load/save/validation."""

from pathlib import Path

import pytest

from tinyrecorder.config import AppConfig, create_default_config, load_config, save_config


class TestConfigCreateDefaults:
    """test_config_create_defaults: Config module creates a default config file when none exists."""

    def test_creates_file_at_expected_path(self, tmp_path: Path) -> None:
        config_path = tmp_path / "tinyrecorder" / "config.toml"
        result = create_default_config(config_path)
        assert result.is_ok
        assert config_path.exists()

    def test_file_is_valid_toml(self, tmp_path: Path) -> None:
        import tomllib

        config_path = tmp_path / "tinyrecorder" / "config.toml"
        create_default_config(config_path)
        with open(config_path, "rb") as f:
            data = tomllib.load(f)
        assert "api" in data
        assert "recording" in data
        assert "app" in data

    def test_default_values_match_spec(self, tmp_path: Path) -> None:
        config_path = tmp_path / "tinyrecorder" / "config.toml"
        result = create_default_config(config_path)
        assert result.is_ok
        config = result.unwrap()
        assert config.model == "gpt-4o-mini-transcribe"
        assert config.language == "auto"
        assert config.auto_copy is True
        assert config.noise_reduction is False
        assert config.sample_rate == 16000
        assert config.device == ""
        assert config.api_key == ""


class TestConfigLoadModifySaveReload:
    """test_config_load_modify_save_reload: Config can be loaded, modified, saved, and reloaded."""

    def test_round_trip_preserves_changes(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.toml"
        create_result = create_default_config(config_path)
        assert create_result.is_ok

        load_result = load_config(config_path)
        assert load_result.is_ok
        config = load_result.unwrap()

        from dataclasses import replace

        modified = replace(config, model="whisper-1")

        save_result = save_config(modified, config_path)
        assert save_result.is_ok

        reload_result = load_config(config_path)
        assert reload_result.is_ok
        reloaded = reload_result.unwrap()
        assert reloaded.model == "whisper-1"
        assert reloaded.language == config.language
        assert reloaded.auto_copy == config.auto_copy
        assert reloaded.noise_reduction == config.noise_reduction

    def test_save_creates_parent_dirs(self, tmp_path: Path) -> None:
        config_path = tmp_path / "deep" / "nested" / "config.toml"
        config = AppConfig()
        result = save_config(config, config_path)
        assert result.is_ok
        assert config_path.exists()


class TestConfigCorruptResetsToDefaults:
    """test_config_corrupt_resets_to_defaults: Corrupt config file is replaced with defaults."""

    def test_invalid_toml_returns_defaults(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.toml"
        config_path.write_text("this is not [valid toml }{}{")
        result = load_config(config_path)
        assert result.is_ok
        config = result.unwrap()
        assert config.model == "gpt-4o-mini-transcribe"

    def test_corrupt_file_is_overwritten(self, tmp_path: Path) -> None:
        import tomllib

        config_path = tmp_path / "config.toml"
        config_path.write_text("this is not valid toml {{{")
        load_config(config_path)
        with open(config_path, "rb") as f:
            data = tomllib.load(f)
        assert "api" in data


class TestConfigDataclassValidation:
    """test_config_dataclass_validation: Config dataclass rejects invalid values."""

    def test_invalid_model_name_rejected(self, tmp_path: Path) -> None:
        import tomli_w

        config_path = tmp_path / "config.toml"
        config_path.write_bytes(tomli_w.dumps({
            "api": {"key": "", "model": "invalid-model"},
            "recording": {"language": "auto", "noise_reduction": False, "sample_rate": 16000, "device": ""},
            "app": {"auto_copy": True},
        }))
        result = load_config(config_path)
        assert result.is_ok
        config = result.unwrap()
        # Invalid model should fall back to default
        assert config.model == "gpt-4o-mini-transcribe"

    def test_invalid_language_rejected(self, tmp_path: Path) -> None:
        import tomli_w

        config_path = tmp_path / "config.toml"
        config_path.write_bytes(tomli_w.dumps({
            "api": {"key": "", "model": "gpt-4o-mini-transcribe"},
            "recording": {"language": "klingon", "noise_reduction": False, "sample_rate": 16000, "device": ""},
            "app": {"auto_copy": True},
        }))
        result = load_config(config_path)
        assert result.is_ok
        config = result.unwrap()
        assert config.language == "auto"

    def test_negative_sample_rate_rejected(self, tmp_path: Path) -> None:
        import tomli_w

        config_path = tmp_path / "config.toml"
        config_path.write_bytes(tomli_w.dumps({
            "api": {"key": "", "model": "gpt-4o-mini-transcribe"},
            "recording": {"language": "auto", "noise_reduction": False, "sample_rate": -1, "device": ""},
            "app": {"auto_copy": True},
        }))
        result = load_config(config_path)
        assert result.is_ok
        config = result.unwrap()
        assert config.sample_rate == 16000


class TestConfigMissingOptionalFields:
    """test_config_missing_optional_fields: Missing sections are filled with defaults."""

    def test_config_missing_optional_fields_fills_defaults(self, tmp_path: Path) -> None:
        """Config with only [api] section (missing [recording] and [app]) fills defaults."""
        import tomli_w

        config_path = tmp_path / "config.toml"
        config_path.write_bytes(tomli_w.dumps({
            "api": {"key": "sk-test", "model": "gpt-4o-mini-transcribe"},
        }))
        result = load_config(config_path)
        assert result.is_ok
        config = result.unwrap()
        # api fields preserved
        assert config.api_key == "sk-test"
        assert config.model == "gpt-4o-mini-transcribe"
        # missing sections filled with defaults
        assert config.language == "auto"
        assert config.noise_reduction is False
        assert config.sample_rate == 16000
        assert config.device == ""
        assert config.auto_copy is True
```

- [ ] Run tests to see them fail:

```bash
uv run pytest tests/unit/test_config.py -v -n0
```

#### 2b. Implement config module

- [ ] Create `src/config.py`:

```python
"""TOML config load/save with typed dataclass and validation."""

from dataclasses import dataclass, replace
from pathlib import Path

import tomllib
import tomli_w
from rusty_results import Err, Ok, Result

from tinyrecorder.constants import (
    DEFAULT_LANGUAGE,
    DEFAULT_MODEL,
    SAMPLE_RATE,
    SUPPORTED_LANGUAGES,
    SUPPORTED_MODELS,
)


@dataclass(slots=True)
class AppConfig:
    """Application configuration with validated defaults.

    Fields map to config.toml sections:
      [api] -> api_key, model
      [recording] -> language, noise_reduction, sample_rate, device
      [app] -> auto_copy
    """

    api_key: str = ""
    model: str = DEFAULT_MODEL
    language: str = DEFAULT_LANGUAGE
    noise_reduction: bool = False
    sample_rate: int = SAMPLE_RATE
    device: str = ""
    auto_copy: bool = True


def _validate_config(config: AppConfig) -> AppConfig:
    """Return a new AppConfig with invalid fields replaced by defaults."""
    fixes: dict[str, str | int | bool] = {}
    if config.model not in SUPPORTED_MODELS:
        fixes["model"] = DEFAULT_MODEL
    if config.language not in SUPPORTED_LANGUAGES:
        fixes["language"] = DEFAULT_LANGUAGE
    if config.sample_rate <= 0:
        fixes["sample_rate"] = SAMPLE_RATE
    if fixes:
        return replace(config, **fixes)  # type: ignore[arg-type]  # rationale: dict values are union of field types, replace accepts **kwargs
    return config


def _config_to_toml_dict(config: AppConfig) -> dict[str, dict[str, str | int | bool]]:
    """Convert AppConfig to nested dict matching TOML structure."""
    return {
        "api": {
            "key": config.api_key,
            "model": config.model,
        },
        "recording": {
            "language": config.language,
            "noise_reduction": config.noise_reduction,
            "sample_rate": config.sample_rate,
            "device": config.device,
        },
        "app": {
            "auto_copy": config.auto_copy,
        },
    }


def _toml_dict_to_config(data: dict[str, object]) -> AppConfig:
    """Parse nested TOML dict into AppConfig, using defaults for missing/wrong-typed fields."""
    defaults = AppConfig()
    api = data.get("api")
    api_dict = api if isinstance(api, dict) else {}
    recording = data.get("recording")
    recording_dict = recording if isinstance(recording, dict) else {}
    app = data.get("app")
    app_dict = app if isinstance(app, dict) else {}

    raw_key = api_dict.get("key", defaults.api_key)
    api_key = raw_key if isinstance(raw_key, str) else defaults.api_key

    raw_model = api_dict.get("model", defaults.model)
    model = raw_model if isinstance(raw_model, str) else defaults.model

    raw_language = recording_dict.get("language", defaults.language)
    language = raw_language if isinstance(raw_language, str) else defaults.language

    raw_nr = recording_dict.get("noise_reduction", defaults.noise_reduction)
    noise_reduction = raw_nr if isinstance(raw_nr, bool) else defaults.noise_reduction

    raw_sr = recording_dict.get("sample_rate", defaults.sample_rate)
    sample_rate = raw_sr if isinstance(raw_sr, int) else defaults.sample_rate

    raw_device = recording_dict.get("device", defaults.device)
    device = raw_device if isinstance(raw_device, str) else defaults.device

    raw_ac = app_dict.get("auto_copy", defaults.auto_copy)
    auto_copy = raw_ac if isinstance(raw_ac, bool) else defaults.auto_copy

    return AppConfig(
        api_key=api_key,
        model=model,
        language=language,
        noise_reduction=noise_reduction,
        sample_rate=sample_rate,
        device=device,
        auto_copy=auto_copy,
    )


def load_config(path: Path) -> Result[AppConfig, str]:
    """Load config from TOML file. On corrupt file, reset to defaults and overwrite.

    Args:
        path: Path to config.toml file.

    Returns:
        Ok(AppConfig) on success, Err(str) on unrecoverable I/O error.
    """
    if not path.exists():
        return create_default_config(path)
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except (tomllib.TOMLDecodeError, OSError):
        # Corrupt file — reset to defaults
        config = AppConfig()
        save_result = save_config(config, path)
        if save_result.is_err:
            return Err(save_result.unwrap_err())
        return Ok(config)
    raw_config = _toml_dict_to_config(data)
    validated = _validate_config(raw_config)
    # If validation changed anything, persist the corrected config
    if validated != raw_config:
        save_result = save_config(validated, path)
        if save_result.is_err:
            return Err(save_result.unwrap_err())
    return Ok(validated)


def save_config(config: AppConfig, path: Path) -> Result[None, str]:
    """Save config to TOML file, creating parent directories as needed.

    Args:
        config: AppConfig to serialize.
        path: Target file path.

    Returns:
        Ok(None) on success, Err(str) on I/O error.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        toml_dict = _config_to_toml_dict(config)
        with open(path, "wb") as f:
            tomli_w.dump(toml_dict, f)
        return Ok(None)
    except OSError as e:
        return Err(f"Failed to save config to {path}: {e}")


def create_default_config(path: Path) -> Result[AppConfig, str]:
    """Create a default config file at the given path.

    Args:
        path: Target file path (parent dirs created automatically).

    Returns:
        Ok(AppConfig) with default values, Err(str) on I/O error.
    """
    config = AppConfig()
    save_result = save_config(config, path)
    if save_result.is_err:
        return Err(save_result.unwrap_err())
    return Ok(config)
```

- [ ] Run tests to see them pass:

```bash
uv run pytest tests/unit/test_config.py -v -n0
```

- [ ] Run type checker and linter:

```bash
uv run basedpyright src/config.py
uv run ruff check src/config.py
```

- [ ] Commit: `feat(config): TOML config load/save with validation and defaults`
