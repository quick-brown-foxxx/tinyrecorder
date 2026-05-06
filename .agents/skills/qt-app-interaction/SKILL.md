---
name: qt-app-interaction
description: >
  Interact with Qt/PySide apps via AT-SPI accessibility. Use when asked
  to "test the UI", "click a button", "inspect widgets",
  "take a screenshot", "read widget state", "check the widget tree",
  or any task requiring direct Qt widget interaction. Covers the core
  inspect-interact-verify workflow. Do NOT use for: clipboard/file dialogs
  (see qt-form-and-input), tray/notifications/audio (see qt-desktop-integration),
  or runtime code execution (see qt-runtime-eval). Core commands are beta.
---

# Qt App Interaction

Every UI interaction follows three phases. Never skip phases. Blind interaction without inspection leads to clicking wrong widgets. Interaction without verification means you don't know if it worked.

All UI commands work the same from host or VM -- no SSH wrapping needed. Use `vm run` only for arbitrary non-qt-ai-dev-tools commands (launching apps, pytest, systemctl, etc.).

## Widget Addressing Flags

These flags control how widgets are matched. They appear on most commands.

| Flag | Effect | Default |
|------|--------|---------|
| `--visible` / `--no-visible` | Only match visible widgets | ON for `click`, `focus`, `fill`, `do`, `text`, `state`; OFF for `tree`, `find` |
| `--exact` | Exact name match instead of substring | OFF (substring match) |
| `--index N` | Select Nth match when multiple widgets share same role+name (0-based) | None (error if multiple) |
| `--app "name"` | Target a specific app when multiple Qt apps are on the AT-SPI bus | None (auto-detect, first Qt app) |

Use `--exact` when substring matching causes ambiguity (e.g., `--name "OK"` matching "OK" and "OK - Confirm"). Use `--index` when multiple identical widgets exist (e.g., two "Delete" buttons in different rows).

### Multi-app scenario

When multiple Qt apps are running, commands auto-connect to the first one and print a hint:

```
# Showing: main.py (also on bus: settings.py, editor.py)
# Use --app to select a different app
```

Target a specific app:

```bash
qt-ai-dev-tools tree --app "settings.py"
qt-ai-dev-tools click --role "push button" --name "Save" --app "editor.py"
```

## Phase 1: Inspect

Understand the current UI state before acting.

**`tree`** -- full widget tree. Shows `[role] "name" @(x,y WxH)`.

```
[application] "main.py"
  [frame] "My App" @(720,387 480x320)
    [filler] ""
      [label] "Status: Ready" @(736,403 448x14)
      [text] "" @(736,429 356x22)
      [push button] "Add" @(1104,429 80x22)
      [list] "" @(736,463 448x194)
      [push button] "Clear" @(736,669 80x22)
      [label] "Items: 0" @(1099,669 85x22)
```

Read this before every interaction sequence. Roles are in brackets, names in quotes, coordinates after @.

**`tree --role "push button"`** -- filter by role when the tree is large. Add `--visible` to exclude hidden widgets.

**`find --role "label" --name "Status"`** -- find a specific widget. Add `--json` for structured output with extents. Add `--exact` for exact name match.

**`find --role "push button" --name "OK" --index 0`** -- select the first match when multiple widgets share the same role+name.

**`text --role "label" --name "Status"`** -- read text content of a widget.

**`state --role "text" --json`** -- full widget details (role, name, text, extents).

**`screenshot -o /tmp/before.png`** -- visual check (~14-22 KB PNG).

**`apps`** -- list AT-SPI-visible applications. **`wait --app "name" --timeout 10`** -- block until app appears.

**`snapshot save before`** -- capture the current widget tree to `snapshots/before.json`. Use as a baseline before interactions.

**`snapshot diff before`** -- compare the current widget tree against a saved snapshot. Shows added, removed, and changed widgets. Add `--json` for structured output.

### When to use which

| Goal | Command |
|------|---------|
| First look at the UI | `tree` |
| Find a specific widget | `find --role "push button" --name "Save"` |
| Find among duplicates | `find --role "push button" --name "OK" --index 0` |
| Read a label's value | `text --role "label" --name "Status"` |
| Full widget details | `state --role "text" --json` |
| Visual check | `screenshot -o /tmp/check.png` |
| Is the app running? | `apps` or `wait --app "name"` |
| Filter tree to one type | `tree --role "push button"` |
| Only visible widgets | `tree --role "text" --visible` |
| Structured output | `find --role "text" --json` |
| Baseline before interaction | `snapshot save before` |
| What changed? | `snapshot diff before` |

## Phase 2: Interact

Perform the action.

**`click --role "push button" --name "Save"`** -- click by role+name. Uses xdotool at the widget's center coordinates. `--visible` is ON by default.

**`type "hello"`** -- type into the currently focused widget. The target widget MUST already be focused.

**`key Return`** -- send a keystroke. Common keys: `Return`, `Tab`, `Escape`, `BackSpace`, `Delete`, `Down`, `Up`, `Page_Down`, `Page_Up`. Modifiers: `"ctrl+a"`, `"ctrl+c"`, `"ctrl+v"`.

**`focus --role "text" --name "Email"`** -- set focus via AT-SPI (falls back to click).

**`fill "user@example.com" --role "text" --name "Email"`** -- focus + clear + type in one command. Preferred over manual focus+clear+type. Add `--no-clear` to append instead of replacing.

**`do click "Save" --role "push button" --verify "label:Status contains Saved"`** -- click + verify in one command. Add `--screenshot` to also capture after clicking.

### When to use which

| Goal | Command |
|------|---------|
| Press a button | `click --role "push button" --name "Save"` |
| Enter text in a field | `fill "value" --role "text" --name "Field"` |
| Clear and replace text | `fill "new value" --role "text" --name "Field"` |
| Append text (no clear) | `fill "value" --role "text" --name "Field" --no-clear` |
| Submit a form | `key Return` |
| Navigate between fields | `key Tab` |
| Close a dialog | `key Escape` |
| Select all text | `key "ctrl+a"` |
| Click and verify result | `do click "Save" --verify "label:Status contains Saved"` |
| Click among duplicates | `click --role "push button" --name "OK" --index 0` |

## Phase 3: Verify

Confirm the action worked. After every interaction sequence:

1. **Read the target widget state** -- did the label update? Did the text field accept input?

   ```bash
   qt-ai-dev-tools text --role "label" --name "Status"
   ```

2. **Read related widgets** -- did the item count increase? Did a new list item appear?

   ```bash
   qt-ai-dev-tools tree --role "list item"
   ```

3. **Take a screenshot if uncertain** -- visual confirmation catches things text inspection misses (layout issues, overlapping widgets, unexpected dialogs).

   ```bash
   qt-ai-dev-tools screenshot -o /tmp/after.png
   ```

4. **Diff against a snapshot** -- if you saved a baseline, compare to see exactly what changed.

   ```bash
   qt-ai-dev-tools snapshot diff before
   ```

Re-inspect the tree after interactions. The widget tree changes -- new items appear, labels update, dialogs open. Do not rely on stale tree output.

## Focus and Input Rules

These are critical. Violating them is the most common source of bugs.

- **Always focus or click a text field before typing.** `type` sends keystrokes to whatever widget currently has focus. If you skip this, text goes to the wrong place.
- **Use `fill` instead of manual focus+clear+type.** `fill` handles all three steps and is more reliable.
- **AT-SPI `editable_text.insert_text()` does NOT work with Qt.** It updates the accessibility layer but not Qt's internal model. Always use xdotool via `type`.
- **Clicking a widget gives it focus.** After `click --role "text"`, you can `type` immediately.
- **`key Tab` navigates fields** in tab order. Useful for forms.
- **Re-inspect the tree after focus changes.** Focus can change widget state (e.g., a combo box may expand its dropdown).

## Widget Roles Reference

Mapping between Qt widget classes and AT-SPI accessibility roles. Use these role strings with `--role`.

| Qt Widget | AT-SPI Role | Notes |
|-----------|-------------|-------|
| QPushButton | `push button` | Most reliable to click |
| QToolButton | `push button` | Same role as QPushButton |
| QLineEdit | `text` | Single-line text input |
| QTextEdit | `text` | Multi-line text input |
| QPlainTextEdit | `text` | Multi-line text input |
| QLabel | `label` | Read-only, primary verification target |
| QCheckBox | `check box` | Toggle with click |
| QRadioButton | `radio button` | Select with click |
| QComboBox | `combo box` | Click to open, then click menu item |
| QListWidget | `list` | Contains list items |
| QListWidgetItem | `list item` | Click to select |
| QTableWidget | `table` | Contains table cells |
| QTreeWidget | `tree` | Contains tree items |
| QTreeWidgetItem | `tree item` | Click to select, double-click to expand |
| QTabWidget | `page tab list` | Contains page tabs |
| QTabBar tab | `page tab` | Click to switch |
| QMenuBar | `menu bar` | Contains menus |
| QMenu | `menu` | Click to open |
| QAction | `menu item` | Click to activate |
| QDialog | `dialog` | Modal window |
| QMessageBox | `alert` | Message/question dialog |
| QFileDialog | `file chooser` | File selection dialog |
| QScrollArea | `scroll pane` | Scrollable container |
| QGroupBox | `panel` | Grouping container |
| QFrame | `filler` or `panel` | Container/separator |
| QMainWindow | `frame` | Top-level window |
| QStatusBar | `status bar` | Bottom status area |
| QProgressBar | `progress bar` | Read value via state/text |
| QSlider | `slider` | Interact via click at position |
| QSpinBox | `spin button` | Type value or use arrows |
| QToolBar | `tool bar` | Contains tool buttons |

**Key observations:**

- Multiple Qt widgets map to the same role (`text` covers QLineEdit, QTextEdit, QPlainTextEdit). Use `--name` to distinguish them.
- Roles are exact strings. `"push button"` works, `"pushbutton"` does not.
- Use `tree` to discover which roles exist in a given app. Not all apps use all widget types.
- Container widgets (`list`, `table`, `tree`, `page tab list`) hold child items. Inspect their children, not the container itself, to interact with individual entries.

## Troubleshooting

### Widget not found

**Symptom:** `Error: No widget found: role=push button, name=Save`

1. Re-inspect the tree: `qt-ai-dev-tools tree`
2. Check if the name changed -- labels are dynamic, the text may have updated.
3. Try partial name match: `find --role "push button" --name "Sav"` (matching is substring-based by default).
4. Check if a modal dialog is blocking -- look for `[dialog]` or `[alert]` in the tree.
5. The widget may not exist yet -- add `sleep 0.5` and re-inspect.

### Multiple widgets found

**Symptom:** `Error: Multiple widgets found for role=push button, name=OK`

1. Use `--exact` for exact name match: `click --role "push button" --name "OK" --exact`.
2. Use `--index N` to select the Nth match: `click --role "push button" --name "OK" --index 0`.
3. Use `find --json` to differentiate by extents (position/size), then target with `--index`.

### Click had no effect

**Symptom:** UI did not change after a click command.

1. Take a screenshot: `screenshot -o /tmp/debug.png` -- is the widget disabled (grayed out)?
2. Check for a modal dialog blocking the main window: `tree` and look for `[dialog]` or `[alert]`.
3. The widget may be in a scroll area and not fully visible -- scroll it into view first.
4. Verify you matched the right widget: `find --role "push button" --name "Save" --json` and check the extents.
5. Use `-v` to see the exact xdotool coordinates used.

### Text went to wrong widget

**Symptom:** Typed text appeared in the wrong field, or did not appear at all.

1. Use `fill` instead of manual focus+type -- it handles focus explicitly.
2. If using `type` directly, click the target text field first: `click --role "text" --name "Email"` then `type "value"`.
3. Check for modal dialogs that may have stolen focus: `tree`.
4. Verify focus is where you expect: `state --role "text" --name "Email"`.

### Stale AT-SPI data

**Symptom:** Widget state reads as the old value immediately after an interaction.

1. Add a short delay: `sleep 0.5` between interaction and verification.
2. Re-read the widget: AT-SPI provides live data but the tree traversal caches during a single command invocation.
3. Run a fresh `text` or `state` command -- each invocation gets a new tree traversal.

## Debugging

When interactions don't work as expected, use verbose mode to see the underlying commands:

```bash
# See exactly what xdotool/scrot commands are executed:
qt-ai-dev-tools -v click --role "push button" --name "Save"

# Full output including command stdout/stderr:
qt-ai-dev-tools -vv fill "hello" --role "text" --name "Input"

# Preview commands without executing (check what would happen):
qt-ai-dev-tools --dry-run click --role "push button" --name "Save"
```

Logs are always written to `~/.local/state/qt-ai-dev-tools/logs/qt-ai-dev-tools.log`. Check this file to trace what happened after unexpected behavior.

## Related Skills

- **qt-form-and-input** -- multi-field form filling, clipboard operations, file dialog automation
- **qt-desktop-integration** -- system tray, notifications, audio subsystem interaction
- **qt-runtime-eval** -- execute Python code inside running Qt apps via the bridge (`eval` command)
- **qt-dev-tools-setup** -- install toolkit, configure VM, verify environment
