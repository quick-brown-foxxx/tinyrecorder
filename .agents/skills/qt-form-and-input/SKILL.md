---
name: qt-form-and-input
description: >
  Fill forms, handle file dialogs, and use the clipboard in Qt/PySide apps.
  Use when asked to "fill a form", "enter text in multiple fields",
  "open a file", "save a file", "handle file dialog", "copy to clipboard",
  "paste from clipboard", "read clipboard", or any multi-field data entry task.
  Covers form filling recipes, QFileDialog automation, and clipboard read/write.
  Clipboard and file dialog commands are alpha.
  Do NOT use for basic single-widget clicks or typing -- see qt-app-interaction.
---

# Forms, File Dialogs, and Clipboard

## When to use this skill

Use this skill for:
- Forms with multiple fields that need filling
- File open/save dialogs (QFileDialog)
- Clipboard read/write operations
- Combo box and dropdown selection
- Modal dialog detection and dismissal

For single-widget interaction (one click, one type, reading a label), use `qt-app-interaction` instead. This skill builds on that foundation with multi-step recipes.

All commands work the same from host or VM -- no SSH wrapping needed. Use `vm run` only for arbitrary commands.

## Form filling

### The `fill` command

`fill` is a compound action: focus the widget, clear existing text, then type the new value. One command replaces three.

```
qt-ai-dev-tools fill "value" --role "text" --name "Field"
```

**Signature:**

```
qt-ai-dev-tools fill <value> [--role TEXT] [--name TEXT] [--app TEXT]
                              [--no-clear] [--visible/--no-visible]
                              [--exact] [--index INT]
```

| Flag | Default | Purpose |
|------|---------|---------|
| `--role, -r` | `"text"` | Widget role to match |
| `--name, -n` | none | Widget name substring to match |
| `--app` | none | Target a specific app by name |
| `--no-clear` | false | Skip clearing the field before typing |
| `--visible/--no-visible` | visible | Only match visible widgets |
| `--exact` | false | Require exact name match instead of substring |
| `--index` | none | Select the Nth match (0-based) when multiple widgets match |

### Multi-field form recipe

```bash
# 1. Inspect -- identify all text fields
qt-ai-dev-tools find --role "text" --json

# 2. Fill each field by name
qt-ai-dev-tools fill "John Doe" --role "text" --name "Name"
qt-ai-dev-tools fill "john@example.com" --role "text" --name "Email"
qt-ai-dev-tools fill "555-0100" --role "text" --name "Phone"

# 3. Submit
qt-ai-dev-tools click --role "push button" --name "Submit"

# 4. Verify
qt-ai-dev-tools text --role "label" --name "Status"
qt-ai-dev-tools screenshot -o /tmp/form-result.png
```

### When fields lack unique names

Use `--index` to target by position:

```bash
qt-ai-dev-tools fill "first value" --role "text" --index 0
qt-ai-dev-tools fill "second value" --role "text" --index 1
```

Or use tab-order navigation:

```bash
qt-ai-dev-tools click --role "text" --index 0
qt-ai-dev-tools fill "first value" --role "text" --index 0
qt-ai-dev-tools key Tab
qt-ai-dev-tools type "second value"
qt-ai-dev-tools key Tab
qt-ai-dev-tools type "third value"
```

## File dialogs

QFileDialog is modal -- it blocks the main window and the bridge cannot respond while it is open. Use these AT-SPI commands to interact with file dialogs.

### Commands

**Detect** -- find an open file dialog, shows type and current path:

```
qt-ai-dev-tools file-dialog detect [--app TEXT] [--json]
```

**Fill** -- type a file path into the filename field:

```
qt-ai-dev-tools file-dialog fill <path> [--app TEXT]
```

**Accept** -- click the Open/Save/OK button:

```
qt-ai-dev-tools file-dialog accept [--app TEXT]
```

**Cancel** -- click the Cancel button:

```
qt-ai-dev-tools file-dialog cancel [--app TEXT]
```

### Complete file dialog recipe

```bash
# 1. Trigger the dialog (e.g., click File -> Open)
qt-ai-dev-tools click --role "menu" --name "File"
qt-ai-dev-tools click --role "menu item" --name "Open"

# 2. Detect the dialog
qt-ai-dev-tools file-dialog detect --json

# 3. Fill the path
qt-ai-dev-tools file-dialog fill /home/user/documents/data.csv

# 4. Accept
qt-ai-dev-tools file-dialog accept

# 5. Verify the file loaded
qt-ai-dev-tools text --role "label" --name "Status"
qt-ai-dev-tools tree
```

### Key constraint

The bridge (`qt-ai-dev-tools eval`) cannot respond while a modal dialog is open. Always use the `file-dialog` AT-SPI commands for dialog interaction, not the bridge.

## Clipboard

Read and write the system clipboard. Uses `xsel` (preferred) with `xclip` fallback inside the VM.

**Read:**

```
qt-ai-dev-tools clipboard read
```

**Write:**

```
qt-ai-dev-tools clipboard write "text to copy"
```

### Copy from app recipe

```bash
# Select text in the app (click the field first if needed)
qt-ai-dev-tools click --role "text" --name "Output"
qt-ai-dev-tools key ctrl+a
qt-ai-dev-tools key ctrl+c

# Read what was copied
qt-ai-dev-tools clipboard read
```

### Paste into app recipe

```bash
# Write to clipboard, then paste
qt-ai-dev-tools clipboard write "data to paste"
qt-ai-dev-tools click --role "text" --name "Input"
qt-ai-dev-tools key ctrl+v
```

## Combo box and dropdown selection

Dropdown items only appear in the AT-SPI tree after the combo box is opened. Always re-inspect after clicking.

### Click-based selection

```bash
# Find the combo box
qt-ai-dev-tools find --role "combo box"

# Open the dropdown
qt-ai-dev-tools click --role "combo box" --name "Country"

# Re-inspect -- items now visible as menu items
qt-ai-dev-tools tree --role "menu item"

# Click the target item
qt-ai-dev-tools click --role "menu item" --name "France"

# Verify
qt-ai-dev-tools text --role "combo box" --name "Country"
```

### Keyboard-based selection (often more reliable)

```bash
qt-ai-dev-tools click --role "combo box" --name "Country"
qt-ai-dev-tools key Down
qt-ai-dev-tools key Down
qt-ai-dev-tools key Return
```

## Handling dialogs

Modal dialogs appear as `[dialog]` or `[alert]` in the tree. They block interaction with the main window until dismissed.

```bash
# Detect -- look for dialog in the tree
qt-ai-dev-tools tree

# Find dialog buttons
qt-ai-dev-tools find --role "push button"

# Click the appropriate button
qt-ai-dev-tools click --role "push button" --name "OK"

# Verify dismissed
qt-ai-dev-tools tree
```

To dismiss an unexpected dialog quickly:

```
qt-ai-dev-tools key Escape
```

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| File dialog not detected | Dialog may use non-standard role | Run `qt-ai-dev-tools tree` and look for `[file chooser]` or `[dialog]` |
| Clipboard read returns empty | `xsel`/`xclip` not installed in VM | Run `qt-ai-dev-tools vm run "which xsel xclip"` to check |
| `fill` went to wrong field | Multiple fields match the role | Add `--name` to target by name, or `--index` to target by position |
| Combo dropdown items not visible | Tree not refreshed after opening | Re-run `qt-ai-dev-tools tree` after clicking the combo box |
| Dialog blocks bridge eval | Modal dialogs block Qt event loop | Use AT-SPI commands (`file-dialog`, `click`, `key`) instead of `eval` |
| Fill does not clear old text | App uses non-standard text widget | Try `--no-clear` flag and manually select-all + delete first |

## Related skills

- See `qt-app-interaction` for core widget interaction (inspect, click, type, verify).
- See `qt-runtime-eval` for executing code inside the running app via bridge.
- See `qt-desktop-integration` for system tray, notifications, and audio.
- See `qt-dev-tools-setup` for environment setup and VM configuration.
