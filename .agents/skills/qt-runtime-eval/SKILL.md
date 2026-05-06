---
name: qt-runtime-eval
description: >
  Execute Python code inside running Qt/PySide apps via the bridge.
  Use when asked to "run code inside the app", "eval an expression",
  "read internal widget state", "call Qt methods directly",
  "bypass AT-SPI limitations", "access app internals", "check a property
  that AT-SPI doesn't expose", or when AT-SPI inspection is insufficient.
  The bridge is the Chrome DevTools evaluate_script equivalent for Qt.
  Do NOT use for normal widget clicks or text input — see qt-app-interaction.
---

# Qt Runtime Eval

## When to use this skill

Use the bridge when AT-SPI cannot give you what you need:

- **Internal widget properties** -- AT-SPI shows the label text but you need `QComboBox.currentData()`, `QCheckBox.isChecked()`, or a custom property.
- **Calling Qt methods directly** -- trigger a slot, toggle visibility, resize a widget, call `repaint()`.
- **Running multi-step logic inside the app** -- iterate over model rows, collect data from multiple widgets in one call, run assertions on internal state.
- **Reading model data** -- row counts, cell values, selection state from `QAbstractItemModel` subclasses.
- **Anything AT-SPI roles/names/text cannot express** -- style sheets, font metrics, palette colors, custom Q_PROPERTY values.

For normal widget clicking, typing, and tree inspection, use `qt-app-interaction`. The bridge is the power tool -- reach for it when the standard inspect-interact-verify loop is insufficient.

## Setup

Two methods. Choose based on your Python version.

### App-installed (any Python version)

Add to your app after `QApplication` is created:

```python
from qt_ai_dev_tools.bridge import start
start()
```

Set the env var to enable (bridge is a no-op without it):

```bash
export QT_AI_DEV_TOOLS_BRIDGE=1
```

### Auto-inject (Python 3.14+ only)

No code changes needed. Inject into a running process:

```bash
qt-ai-dev-tools bridge inject --pid <PID>
```

Uses `sys.remote_exec` -- only available in Python 3.14+.

## Commands

### Eval

```bash
# Eval expression, return result
qt-ai-dev-tools eval "expression"

# Exec statement, return captured stdout
qt-ai-dev-tools eval "statement"

# Return result as structured JSON
qt-ai-dev-tools eval --json "code"

# Eval from file
qt-ai-dev-tools eval --file script.py

# Eval from stdin
qt-ai-dev-tools eval --file - < script.py

# Target specific app by PID
qt-ai-dev-tools eval --pid PID "code"

# Set execution timeout (default 30s)
qt-ai-dev-tools eval --timeout 60 "long_running_code()"
```

Expressions return their value. Statements (assignments, loops, `print()`) return `None` as result but captured stdout is printed.

### Bridge management

```bash
# List active bridge sockets
qt-ai-dev-tools bridge status

# List as JSON
qt-ai-dev-tools bridge status --json

# Inject into running Python 3.14+ app
qt-ai-dev-tools bridge inject --pid PID
```

## Pre-populated namespace

Every eval session has these names available without imports:

| Name | Description |
|------|-------------|
| `app` | The running `QApplication` instance |
| `widgets` | `dict[str, QWidget]` -- all widgets with `objectName`, keyed by name |
| `find(type, name)` | `app.findChild(type, name)` -- find one widget by type and name |
| `findall(type)` | Find all widgets of given type |
| `_` | Result of the last eval expression |
| `QApplication` | `PySide6.QtWidgets.QApplication` |
| `QWidget` | `PySide6.QtWidgets.QWidget` |
| `QPushButton` | `PySide6.QtWidgets.QPushButton` |
| `QLabel` | `PySide6.QtWidgets.QLabel` |
| `QLineEdit` | `PySide6.QtWidgets.QLineEdit` |
| `QTextEdit` | `PySide6.QtWidgets.QTextEdit` |
| `QComboBox` | `PySide6.QtWidgets.QComboBox` |
| `QCheckBox` | `PySide6.QtWidgets.QCheckBox` |
| `QRadioButton` | `PySide6.QtWidgets.QRadioButton` |
| `QSlider` | `PySide6.QtWidgets.QSlider` |
| `QSpinBox` | `PySide6.QtWidgets.QSpinBox` |
| `Qt` | Qt constants (e.g., `Qt.AlignCenter`, `Qt.Checked`) |

## Recipes

### Read a widget property

```bash
qt-ai-dev-tools eval "widgets['status_label'].text()"
```

### Find all buttons

```bash
qt-ai-dev-tools eval "findall(QPushButton)"
```

### Click via Qt API (bypasses xdotool)

```bash
qt-ai-dev-tools eval "widgets['save_btn'].click()"
```

### Read combo box internal data

```bash
qt-ai-dev-tools eval "widgets['country'].currentData()"
```

### Multi-line with stdout capture

```bash
qt-ai-dev-tools eval "for btn in findall(QPushButton): print(btn.text())"
```

### Check if widget is enabled

```bash
qt-ai-dev-tools eval "widgets['save_btn'].isEnabled()"
```

### Access model data

```bash
qt-ai-dev-tools eval "widgets['table'].model().rowCount()"
```

### Get window title

```bash
qt-ai-dev-tools eval "app.activeWindow().windowTitle()"
```

## Limitations

- **Modal dialogs block the bridge.** While a modal dialog is open (QFileDialog, QMessageBox, etc.), the bridge cannot respond because the Qt event loop is blocked by the modal. Use AT-SPI and xdotool for dialog interaction (see `qt-form-and-input` skill).
- **Statements return None.** Assignments, loops, and `print()` calls return `None` as their result value. Use `print()` to produce output -- stdout is captured and returned.
- **Bridge must be active.** Either `bridge.start()` must be called in the app code with `QT_AI_DEV_TOOLS_BRIDGE=1` set, or `bridge inject` must be used on a Python 3.14+ process.

## Troubleshooting

**"No bridge socket found"** -- The app is not running, `bridge.start()` was not called, or `QT_AI_DEV_TOOLS_BRIDGE=1` is not set. Verify the app is running: `qt-ai-dev-tools apps`. For inject method: requires Python 3.14+.

**"Connection refused" / "Broken pipe"** -- The app crashed or was killed. Check the PID is alive: `kill -0 <pid>`. Delete stale sockets: `rm /tmp/qt-ai-dev-tools-bridge-<pid>.sock`.

**`NameError`** -- The name is not in the pre-populated namespace. Check spelling. Inspect available names on a widget: `qt-ai-dev-tools eval "dir(widgets['name'])"`.

**`AttributeError`** -- Wrong method name on the widget. Inspect available methods: `qt-ai-dev-tools eval "dir(widgets['name'])"`.

**Bridge inject fails** -- Requires Python 3.14+ (`sys.remote_exec`). For older Python, use the app-installed method (add `bridge.start()` to app code).

## Related skills

- **`qt-dev-tools-setup`** -- install qt-ai-dev-tools, configure VM, verify environment
- **`qt-app-interaction`** -- inspect widgets, click, type, verify results via AT-SPI (the core workflow loop)
- **`qt-form-and-input`** -- clipboard and file dialog automation
- **`qt-desktop-integration`** -- system tray, notifications, and audio
