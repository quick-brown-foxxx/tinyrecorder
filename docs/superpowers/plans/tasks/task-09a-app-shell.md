# Task 9a: UI -- App Shell + System Tray

**Phase:** 5 (parallel with: Task 9b, Task 9c, Task 11)
**Dependencies:** Task 2, Task 3
**Skills:** `building-qt-apps`, `writing-python-code`
**Files to create:** `src/ui/__init__.py`, `src/ui/app.py`, `src/ui/styles.py`
**Test files:** `tests/unit/test_ui_app.py`
**Estimated complexity:** small

> **Testing note:** The pytest-qt tests in this task are smoke tests that verify widget instantiation and basic state logic. They are NOT e2e tests. Real end-to-end UI testing is done in Task 13 using qt-ai-dev-tools with a VM, which tests the actual running app through AT-SPI accessibility.

---

**Goal:** Create QApplication factory, qasync event loop setup, signal handling, system tray icon with menu, and a `run_gui` stub.

> **Note:** The `qapp` fixture is defined in `tests/conftest.py` (Task 1). Do NOT redefine it in this task's test file. Import it from conftest automatically via pytest fixture discovery.

> **Note:** `run_gui` is defined as a stub that raises `NotImplementedError`. Task 12 replaces it with the real implementation. This resolves the implicit dependency where Task 10's `__main__.py` calls `run_gui` before Task 12 exists.

#### Steps

- [ ] Create `tests/unit/test_ui_app.py` with import and factory tests:

```python
"""Tests for UI app shell."""

import sys
from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QApplication

from tinyrecorder.ui.app import create_app, AppShell


def test_create_app_returns_qapplication(qapp: QApplication) -> None:
    """create_app returns a QApplication instance (or reuses existing)."""
    app = create_app()
    assert isinstance(app, QApplication)
    assert app.applicationName() == "TinyRecorder"


def test_app_shell_creates_tray_icon(qapp: QApplication) -> None:
    """AppShell creates a system tray icon."""
    from PySide6.QtWidgets import QSystemTrayIcon

    shell = AppShell(qapp)
    assert isinstance(shell.tray_icon, QSystemTrayIcon)
    assert shell.tray_icon.isVisible() is False  # not shown until run


def test_app_shell_tray_menu_has_actions(qapp: QApplication) -> None:
    """Tray menu contains Show/Hide, Settings, Quit actions."""
    shell = AppShell(qapp)
    menu = shell.tray_icon.contextMenu()
    assert menu is not None
    action_texts = [a.text() for a in menu.actions()]
    assert "Show/Hide" in action_texts
    assert "Settings" in action_texts
    assert "Quit" in action_texts
```

- [ ] Run tests and confirm they fail:

```bash
uv run pytest tests/unit/test_ui_app.py -x -v 2>&1 | head -40
```

- [ ] Create `src/ui/__init__.py`:

```python
"""TinyRecorder UI package."""
```

- [ ] Create `src/ui/styles.py`:

```python
"""TinyRecorder UI theme constants and stylesheets."""

# Color palette
COLOR_BG_PRIMARY = "#1e1e2e"
COLOR_BG_SECONDARY = "#313244"
COLOR_BG_SURFACE = "#45475a"
COLOR_TEXT_PRIMARY = "#cdd6f4"
COLOR_TEXT_SECONDARY = "#a6adc8"
COLOR_ACCENT = "#89b4fa"
COLOR_ACCENT_HOVER = "#74c7ec"
COLOR_RECORDING = "#f38ba8"
COLOR_SUCCESS = "#a6e3a1"
COLOR_ERROR = "#f38ba8"
COLOR_WARNING = "#f9e2af"
COLOR_VU_LOW = "#a6e3a1"
COLOR_VU_MID = "#f9e2af"
COLOR_VU_HIGH = "#f38ba8"

# Font sizes
FONT_SIZE_SMALL = 11
FONT_SIZE_NORMAL = 13
FONT_SIZE_LARGE = 16
FONT_SIZE_XLARGE = 20

# Dimensions
WINDOW_DEFAULT_WIDTH = 400
WINDOW_DEFAULT_HEIGHT = 550
WINDOW_MIN_WIDTH = 350
WINDOW_MIN_HEIGHT = 450
VU_METER_HEIGHT = 20
RECORD_BUTTON_SIZE = 64

APP_STYLESHEET = f"""
QMainWindow, QDialog {{
    background-color: {COLOR_BG_PRIMARY};
    color: {COLOR_TEXT_PRIMARY};
}}

QLabel {{
    color: {COLOR_TEXT_PRIMARY};
    font-size: {FONT_SIZE_NORMAL}px;
}}

QPushButton {{
    background-color: {COLOR_BG_SECONDARY};
    color: {COLOR_TEXT_PRIMARY};
    border: 1px solid {COLOR_BG_SURFACE};
    border-radius: 6px;
    padding: 8px 16px;
    font-size: {FONT_SIZE_NORMAL}px;
}}

QPushButton:hover {{
    background-color: {COLOR_BG_SURFACE};
    border-color: {COLOR_ACCENT};
}}

QPushButton:disabled {{
    color: {COLOR_TEXT_SECONDARY};
    background-color: {COLOR_BG_PRIMARY};
    border-color: {COLOR_BG_SECONDARY};
}}

QPushButton#recordButton {{
    background-color: {COLOR_RECORDING};
    color: {COLOR_BG_PRIMARY};
    border-radius: {RECORD_BUTTON_SIZE // 2}px;
    font-size: {FONT_SIZE_LARGE}px;
    font-weight: bold;
    min-width: {RECORD_BUTTON_SIZE}px;
    min-height: {RECORD_BUTTON_SIZE}px;
    max-width: {RECORD_BUTTON_SIZE}px;
    max-height: {RECORD_BUTTON_SIZE}px;
}}

QPushButton#recordButton:hover {{
    background-color: {COLOR_ERROR};
}}

QComboBox {{
    background-color: {COLOR_BG_SECONDARY};
    color: {COLOR_TEXT_PRIMARY};
    border: 1px solid {COLOR_BG_SURFACE};
    border-radius: 4px;
    padding: 4px 8px;
    font-size: {FONT_SIZE_SMALL}px;
}}

QComboBox:hover {{
    border-color: {COLOR_ACCENT};
}}

QComboBox QAbstractItemView {{
    background-color: {COLOR_BG_SECONDARY};
    color: {COLOR_TEXT_PRIMARY};
    selection-background-color: {COLOR_BG_SURFACE};
}}

QTextEdit {{
    background-color: {COLOR_BG_SECONDARY};
    color: {COLOR_TEXT_PRIMARY};
    border: 1px solid {COLOR_BG_SURFACE};
    border-radius: 6px;
    padding: 8px;
    font-size: {FONT_SIZE_NORMAL}px;
}}

QProgressBar {{
    background-color: {COLOR_BG_SECONDARY};
    border: 1px solid {COLOR_BG_SURFACE};
    border-radius: 3px;
    text-align: center;
    max-height: {VU_METER_HEIGHT}px;
}}

QProgressBar::chunk {{
    background-color: {COLOR_VU_LOW};
    border-radius: 2px;
}}

QLineEdit {{
    background-color: {COLOR_BG_SECONDARY};
    color: {COLOR_TEXT_PRIMARY};
    border: 1px solid {COLOR_BG_SURFACE};
    border-radius: 4px;
    padding: 6px 8px;
    font-size: {FONT_SIZE_NORMAL}px;
}}

QLineEdit:focus {{
    border-color: {COLOR_ACCENT};
}}

QCheckBox {{
    color: {COLOR_TEXT_PRIMARY};
    font-size: {FONT_SIZE_NORMAL}px;
    spacing: 8px;
}}

QStatusBar {{
    background-color: {COLOR_BG_SECONDARY};
    color: {COLOR_TEXT_SECONDARY};
    font-size: {FONT_SIZE_SMALL}px;
}}

QListWidget {{
    background-color: {COLOR_BG_SECONDARY};
    color: {COLOR_TEXT_PRIMARY};
    border: 1px solid {COLOR_BG_SURFACE};
    border-radius: 4px;
}}

QListWidget::item {{
    padding: 6px 8px;
}}

QListWidget::item:selected {{
    background-color: {COLOR_BG_SURFACE};
}}

QMenu {{
    background-color: {COLOR_BG_SECONDARY};
    color: {COLOR_TEXT_PRIMARY};
    border: 1px solid {COLOR_BG_SURFACE};
}}

QMenu::item:selected {{
    background-color: {COLOR_BG_SURFACE};
}}
"""
```

- [ ] Create `src/ui/app.py`:

```python
"""QApplication factory, system tray, signal handling, qasync setup."""

from __future__ import annotations

import signal
import sys
from typing import TYPE_CHECKING, Final, Literal

from collections.abc import Callable

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from tinyrecorder.ui.styles import APP_STYLESHEET

_SEPARATOR: Final = "SEPARATOR"
_Entry = tuple[str, Callable[[], None]] | Literal["SEPARATOR"]

if TYPE_CHECKING:
    from tinyrecorder.config import AppConfig
    from tinyrecorder.ui.main_window import MainWindow


def create_app() -> QApplication:
    """Create or return the singleton QApplication.

    Sets app name, stylesheet, and org info.
    """
    existing = QApplication.instance()
    if existing is not None:
        assert isinstance(existing, QApplication)
        return existing

    app = QApplication(sys.argv)
    app.setApplicationName("TinyRecorder")
    app.setOrganizationName("TinyRecorder")
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(APP_STYLESHEET)
    return app


class AppShell:
    """Application shell: tray icon, signal handling, qasync loop.

    Owns the system tray icon and its context menu. The main window
    is created separately and attached via set_main_window().
    """

    def __init__(self, app: QApplication) -> None:
        self._app = app
        self._main_window: MainWindow | None = None

        # System tray icon
        self.tray_icon = QSystemTrayIcon(app)
        self.tray_icon.setToolTip("TinyRecorder")

        # Tray icon (use theme icon or fallback)
        icon = QIcon.fromTheme("audio-input-microphone")
        if icon.isNull():
            icon = app.style().standardIcon(app.style().StandardPixmap.SP_MediaVolume)  # type: ignore[union-attr]  # rationale: style() guaranteed non-None after QApplication init
        self.tray_icon.setIcon(icon)

        # Context menu (declarative pattern)
        self._setup_tray_menu()
        self.tray_icon.activated.connect(self._on_tray_activated)

        # Signal handling: Ctrl+C graceful quit
        # Timer trick: Python signal handlers only run between bytecodes,
        # but Qt blocks in its own event loop. A periodic timer forces
        # Python to check for pending signals.
        self._signal_timer = QTimer()
        self._signal_timer.setInterval(200)
        self._signal_timer.timeout.connect(lambda: None)
        self._signal_timer.start()

        signal.signal(signal.SIGINT, self._handle_sigint)
        signal.signal(signal.SIGTERM, self._handle_sigint)

    def _setup_tray_menu(self) -> None:
        """Build tray context menu from declarative entries list."""
        entries: list[_Entry] = [
            ("Show/Hide", self._toggle_window_visibility),
            _SEPARATOR,
            ("Settings", self._open_settings),
            _SEPARATOR,
            ("Quit", self._quit),
        ]

        menu = QMenu()
        for entry in entries:
            if entry is _SEPARATOR:
                menu.addSeparator()
            else:
                label, cb = entry
                menu.addAction(label, cb)
        self.tray_icon.setContextMenu(menu)

    def set_main_window(self, window: MainWindow) -> None:
        """Attach the main window for show/hide toggling."""
        self._main_window = window

    def show_tray(self) -> None:
        """Show the system tray icon."""
        self.tray_icon.setVisible(True)

    def _toggle_window_visibility(self) -> None:
        """Toggle the main window visible/hidden."""
        if self._main_window is None:
            return
        if self._main_window.isVisible():
            self._main_window.hide()
        else:
            self._main_window.show()
            self._main_window.raise_()
            self._main_window.activateWindow()

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        """Handle tray icon click -- toggle window visibility."""
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._toggle_window_visibility()

    def _open_settings(self) -> None:
        """Open the settings dialog."""
        # Wired in Task 12 when SettingsDialog exists
        pass

    def _quit(self) -> None:
        """Graceful quit: cleanup and exit."""
        self._signal_timer.stop()
        self._app.quit()

    def _handle_sigint(self, _signum: int, _frame: object) -> None:
        """Handle SIGINT/SIGTERM -- quit gracefully."""
        self._quit()


def run_gui(config: "AppConfig") -> int:
    """Launch the TinyRecorder GUI.

    This is a stub that raises NotImplementedError. Task 12 replaces this
    with the real implementation that wires all components together.

    Args:
        config: Loaded application configuration.

    Returns:
        Exit code (0 = success).

    Raises:
        NotImplementedError: Always, until Task 12 provides the real implementation.
    """
    raise NotImplementedError(
        "run_gui is a stub. Task 12 (Startup Integration) provides the real implementation."
    )
```

- [ ] Run tests and confirm they pass:

```bash
uv run pytest tests/unit/test_ui_app.py -x -v 2>&1 | head -40
```

- [ ] Commit: `feat(ui): add app shell with system tray, styles, and QApplication factory`
