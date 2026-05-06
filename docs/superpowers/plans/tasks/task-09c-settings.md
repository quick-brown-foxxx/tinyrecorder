# Task 9c: UI -- Settings Dialog

**Phase:** 5 (parallel with: Task 9a, Task 9b, Task 11)
**Dependencies:** Task 2
**Skills:** `building-qt-apps`, `writing-python-code`
**Files to create:** `src/ui/settings_dialog.py`
**Test files:** `tests/unit/test_settings_dialog.py`
**Estimated complexity:** small

---

**Goal:** Create a settings dialog for API key, auto-copy, noise reduction, and cache dir display.

> **Note:** The `qapp` fixture is defined in `tests/conftest.py` (Task 1). Do NOT redefine it in this task's test file. Import it from conftest automatically via pytest fixture discovery.

#### Steps

- [ ] Create `tests/unit/test_settings_dialog.py`:

```python
"""Tests for settings dialog."""

import sys

import pytest
from PySide6.QtWidgets import QApplication

from tinyrecorder.config import AppConfig
from tinyrecorder.ui.settings_dialog import SettingsDialog


def test_settings_dialog_creates(qapp: QApplication) -> None:
    """SettingsDialog instantiates without error."""
    config = AppConfig()
    dialog = SettingsDialog(config)
    assert dialog is not None
    assert dialog.windowTitle() == "Settings"


def test_settings_dialog_populates_from_config(qapp: QApplication) -> None:
    """SettingsDialog fields reflect the provided config values."""
    from dataclasses import replace

    config = replace(AppConfig(), api_key="sk-test-key-123", auto_copy=False, noise_reduction=True)

    dialog = SettingsDialog(config)
    # API key is masked (echoMode=Password) but text is set
    assert dialog.api_key_edit.text() == "sk-test-key-123"
    assert dialog.auto_copy_checkbox.isChecked() is False
    assert dialog.noise_reduction_checkbox.isChecked() is True


def test_settings_dialog_get_updated_config(qapp: QApplication) -> None:
    """get_updated_config returns a config reflecting dialog field values."""
    config = AppConfig()
    dialog = SettingsDialog(config)

    dialog.api_key_edit.setText("sk-new-key")
    dialog.auto_copy_checkbox.setChecked(True)
    dialog.noise_reduction_checkbox.setChecked(True)

    updated = dialog.get_updated_config()
    assert updated.api_key == "sk-new-key"
    assert updated.auto_copy is True
    assert updated.noise_reduction is True
```

- [ ] Run tests and confirm they fail:

```bash
uv run pytest tests/unit/test_settings_dialog.py -x -v 2>&1 | head -40
```

- [ ] Create `src/ui/settings_dialog.py`:

```python
"""Settings dialog for TinyRecorder configuration."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from tinyrecorder.config import AppConfig

# Note: cache_dir is passed as a constructor parameter (from UserDirectories.cache_dir).
# There is no CACHE_DIR constant; paths come from the platform layer.


class SettingsDialog(QDialog):
    """Modal dialog for editing application settings.

    Displays fields for API key, auto-copy, noise reduction,
    and cache directory. Returns an updated config on accept.
    """

    def __init__(self, config: AppConfig, cache_dir: Path | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(360)
        self._config = config

        layout = QVBoxLayout(self)

        form = QFormLayout()

        # API Key
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_edit.setPlaceholderText("sk-...")
        self.api_key_edit.setText(config.api_key)
        form.addRow("API Key:", self.api_key_edit)

        # Auto-copy
        self.auto_copy_checkbox = QCheckBox("Copy transcript to clipboard automatically")
        self.auto_copy_checkbox.setChecked(config.auto_copy)
        form.addRow("", self.auto_copy_checkbox)

        # Noise reduction
        self.noise_reduction_checkbox = QCheckBox("Apply noise reduction before transcription")
        self.noise_reduction_checkbox.setChecked(config.noise_reduction)
        form.addRow("", self.noise_reduction_checkbox)

        # Cache dir (read-only display)
        cache_label = QLabel(str(cache_dir) if cache_dir is not None else "(unknown)")
        cache_label.setToolTip("Audio files are stored here")
        cache_label.setWordWrap(True)
        form.addRow("Cache dir:", cache_label)

        layout.addLayout(form)

        # Buttons
        button_row = QHBoxLayout()
        button_row.addStretch()

        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        button_row.addWidget(cancel_button)

        save_button = QPushButton("Save")
        save_button.setDefault(True)
        save_button.clicked.connect(self.accept)
        button_row.addWidget(save_button)

        layout.addLayout(button_row)

    def get_updated_config(self) -> AppConfig:
        """Return a new AppConfig reflecting the current dialog field values.

        Returns:
            A copy of the original config with dialog values applied.
        """
        return replace(
            self._config,
            api_key=self.api_key_edit.text(),
            auto_copy=self.auto_copy_checkbox.isChecked(),
            noise_reduction=self.noise_reduction_checkbox.isChecked(),
        )
```

- [ ] Run tests and confirm they pass:

```bash
uv run pytest tests/unit/test_settings_dialog.py -x -v 2>&1 | head -40
```

- [ ] Commit: `feat(ui): add settings dialog for API key, auto-copy, noise reduction`
