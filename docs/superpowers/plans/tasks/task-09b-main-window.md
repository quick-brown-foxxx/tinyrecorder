# Task 9b: UI -- Main Window + Widgets

**Phase:** 5 (parallel with: Task 9a, Task 9c, Task 11)
**Dependencies:** Task 3
**Skills:** `building-qt-apps`, `writing-python-code`
**Files to create:** `src/ui/main_window.py`, `src/ui/widgets.py`
**Test files:** `tests/unit/test_main_window.py`
**Estimated complexity:** large

> **Testing note:** The pytest-qt tests in this task are smoke tests that verify widget instantiation and basic state logic. They are NOT e2e tests. Real end-to-end UI testing is done in Task 13 using qt-ai-dev-tools with a VM, which tests the actual running app through AT-SPI accessibility.

---

**Goal:** Create the main window with four zones (TopBar, RecordingZone, TranscriptZone, ActionBar), VU meter widget, and history panel. State-driven button enable/disable.

> **Note:** The `qapp` fixture is defined in `tests/conftest.py` (Task 1). Do NOT redefine it in this task's test file. Import it from conftest automatically via pytest fixture discovery.

#### Steps

- [ ] Create `tests/unit/test_main_window.py`:

```python
"""Tests for main window creation."""

import sys

import pytest
from PySide6.QtWidgets import QApplication

from tinyrecorder.ui.main_window import MainWindow
from tinyrecorder.state import RecordingState


def test_main_window_creates(qapp: QApplication) -> None:
    """MainWindow instantiates without error."""
    window = MainWindow()
    assert window is not None
    assert window.windowTitle() == "TinyRecorder"


def test_main_window_has_record_button(qapp: QApplication) -> None:
    """MainWindow contains a record button."""
    window = MainWindow()
    assert window.record_button is not None
    assert window.record_button.text() in ("● REC", "■ STOP")


def test_main_window_has_transcript_area(qapp: QApplication) -> None:
    """MainWindow contains a read-only transcript text area."""
    window = MainWindow()
    assert window.transcript_area is not None
    assert window.transcript_area.isReadOnly()


def test_main_window_has_action_buttons(qapp: QApplication) -> None:
    """MainWindow contains copy, retry, import, history buttons."""
    window = MainWindow()
    assert window.copy_button is not None
    assert window.retry_button is not None
    assert window.import_button is not None
    assert window.history_button is not None


def test_main_window_update_for_idle_state(qapp: QApplication) -> None:
    """In IDLE state, record button shows REC and action buttons are configured correctly."""
    window = MainWindow()
    window.update_for_state(RecordingState.IDLE)
    assert window.record_button.text() == "● REC"
    assert window.record_button.isEnabled()
    assert not window.copy_button.isEnabled()
    assert not window.retry_button.isEnabled()
    assert window.import_button.isEnabled()


def test_main_window_update_for_recording_state(qapp: QApplication) -> None:
    """In RECORDING state, record button shows STOP and cancel is visible."""
    window = MainWindow()
    window.update_for_state(RecordingState.RECORDING)
    assert window.record_button.text() == "■ STOP"
    assert window.record_button.isEnabled()
    assert window.cancel_button.isVisible()
    assert not window.import_button.isEnabled()


def test_main_window_update_for_success_state(qapp: QApplication) -> None:
    """In SUCCESS state, copy and retry are enabled."""
    window = MainWindow()
    window.update_for_state(RecordingState.SUCCESS)
    assert not window.record_button.isEnabled()
    assert window.copy_button.isEnabled()
    assert window.retry_button.isEnabled()
```

- [ ] Add to `MainWindow` a method to disable recording when no microphone is detected:

```python
def set_mic_available(self, available: bool) -> None:
    """Enable or disable the record button based on mic availability."""
    self.record_button.setEnabled(available)
    if not available:
        self.record_button.setToolTip("No microphone detected")
    else:
        self.record_button.setToolTip("")
```

- [ ] Add a `closeEvent` override so closing the window hides to tray instead of quitting:

```python
def closeEvent(self, event: QCloseEvent) -> None:
    """Override close to hide to tray instead of quitting."""
    event.ignore()
    self.hide()
```

- [ ] Add a status bar with state and cost labels to `MainWindow.__init__`:

```python
self.state_label = QLabel("Idle")
self.cost_label = QLabel("$0.00")
status_bar = self.statusBar()
if status_bar is not None:
    status_bar.addWidget(self.state_label)
    status_bar.addPermanentWidget(self.cost_label)
```

- [ ] Add a method to update the cost display:

```python
def set_cost_display(self, cost_usd: float) -> None:
    """Update the session cost label in the status bar."""
    self.cost_label.setText(f"${cost_usd:.4f}")
```

- [ ] Note: `set_timer_text(text: str)` already exists on `MainWindow`. Task 12's `ApplicationController` recording loop calls it with elapsed MM:SS on each tick.

- [ ] Add tests for the new features in `tests/unit/test_main_window.py`:

```python
def test_main_window_no_mic_disables_record(qapp: QApplication) -> None:
    """When no mic is available, record button is disabled with tooltip."""
    window = MainWindow()
    window.set_mic_available(False)
    assert not window.record_button.isEnabled()
    assert "No microphone" in window.record_button.toolTip()
    # Re-enable
    window.set_mic_available(True)
    assert window.record_button.isEnabled()


def test_close_hides_to_tray(qapp: QApplication) -> None:
    """Closing the window hides it instead of quitting."""
    from PySide6.QtGui import QCloseEvent

    window = MainWindow()
    window.show()
    assert window.isVisible()
    event = QCloseEvent()
    window.closeEvent(event)
    assert event.isAccepted() is False
    assert not window.isVisible()


def test_main_window_cost_display(qapp: QApplication) -> None:
    """Cost display updates correctly."""
    window = MainWindow()
    window.set_cost_display(0.0123)
    assert window.cost_label.text() == "$0.0123"
```

- [ ] Run tests and confirm they fail:

```bash
uv run pytest tests/unit/test_main_window.py -x -v 2>&1 | head -50
```

- [ ] Create `src/ui/widgets.py` (VUMeterWidget, HistoryPanel) -- same content as in the original plan.

- [ ] Create `src/ui/main_window.py` (MainWindow with four zones) -- same content as in the original plan.

- [ ] Run tests and confirm they pass:

```bash
uv run pytest tests/unit/test_main_window.py -x -v 2>&1 | head -50
```

- [ ] Commit: `feat(ui): add main window with four zones, VU meter, and history panel`
