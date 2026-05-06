---
name: qt-desktop-integration
description: >
  Interact with system tray icons, desktop notifications, and audio
  in Qt/PySide apps. Use when asked to "check the system tray",
  "click tray icon", "read tray menu", "listen for notifications",
  "dismiss notification", "test audio", "create virtual microphone",
  "record audio", "verify audio output", or any OS-level desktop
  integration testing. Covers D-Bus system tray (SNI), notification
  monitoring, and PipeWire audio. All commands in this skill are alpha.
  Do NOT use for widget interaction -- see qt-app-interaction.
---

# Qt Desktop Integration

System tray, notifications, and audio operate outside the widget tree. They use D-Bus and PipeWire, not AT-SPI. For widget interaction, use the `qt-app-interaction` skill instead.

All commands work the same from host or VM -- no SSH wrapping needed. Use `vm run` only for arbitrary commands.

## When to Use This Skill

Use this skill when testing desktop integration features:

- **System tray** -- app puts an icon in the system tray, you need to click it, read its menu, or select a menu item.
- **Notifications** -- app emits desktop notifications, you need to capture, verify, dismiss, or invoke actions on them.
- **Audio** -- app uses microphone input or audio output, you need to create a virtual mic, feed audio, record output, or verify audio is not silence.

These are Linux-specific capabilities. The VM must be running with the appropriate services (snixembed for tray, dbus-monitor for notifications, PipeWire for audio).

## System Tray

Requires SNI (StatusNotifierItem) support. The VM runs `snixembed` to bridge XEmbed tray icons to SNI. Apps using `QSystemTrayIcon` are accessible through these commands.

**`tray list`** -- list all tray items. Shows name, bus name, and object path.

```bash
qt-ai-dev-tools tray list
#   MyApp (org.kde.StatusNotifierItem-1234-1) @ /StatusNotifierItem
qt-ai-dev-tools tray list --json
```

**`tray click "AppName"`** -- left-click (D-Bus Activate) a tray icon by name substring. Use `--button right` for context menu via xdotool.

```bash
qt-ai-dev-tools tray click "MyApp"
qt-ai-dev-tools tray click "MyApp" --button right
```

**`tray menu "AppName"`** -- show context menu entries with indices. Add `--json` for structured output.

```bash
qt-ai-dev-tools tray menu "MyApp"
#   [0] Show Window
#   [1] Settings
#   [2] Quit
qt-ai-dev-tools tray menu "MyApp" --json
```

**`tray select "AppName" "Quit"`** -- click a specific menu item by label.

```bash
qt-ai-dev-tools tray select "MyApp" "Quit"
```

### Tray Recipe

List tray items, activate one, verify the app window appeared:

```bash
qt-ai-dev-tools tray list
qt-ai-dev-tools tray click "MyApp"
qt-ai-dev-tools tree   # verify the app window is now visible
```

Open a tray context menu and select an item:

```bash
qt-ai-dev-tools tray menu "MyApp"
qt-ai-dev-tools tray select "MyApp" "Settings"
qt-ai-dev-tools tree   # verify the settings dialog appeared
```

## Notifications

Uses `dbus-monitor` on `org.freedesktop.Notifications` to capture desktop notifications. Notifications are identified by numeric ID.

**`notify listen --timeout 10`** -- capture notifications for N seconds (default 5). Returns notification ID, app name, summary, body, and available actions.

```bash
qt-ai-dev-tools notify listen --timeout 10
#   [42] MyApp: Task Complete
#     The export finished successfully.
#     Action: open_file (Open File)
qt-ai-dev-tools notify listen --timeout 10 --json
```

**`notify dismiss 42`** -- dismiss a notification by ID.

```bash
qt-ai-dev-tools notify dismiss 42
```

**`notify action 42 "action_key"`** -- invoke an action button on a notification. The action key comes from `listen` output.

```bash
qt-ai-dev-tools notify action 42 "open_file"
```

### Notification Recipe

Trigger an action in the app, capture the resulting notification, then act on it:

```bash
qt-ai-dev-tools click --role "push button" --name "Export"
qt-ai-dev-tools notify listen --timeout 10 --json
# Parse the notification ID and action keys from JSON output
qt-ai-dev-tools notify action 42 "open_file"
```

**Caveat:** `QSystemTrayIcon.showMessage()` may not emit standard D-Bus notification signals depending on the notification backend. If notifications are not captured, the app may be using a non-standard path. Check with `notify listen` and a longer timeout first.

## Audio

PipeWire-based virtual microphone, recording, and verification. Use these commands to test audio input/output in Qt apps.

**`audio virtual-mic start`** -- create a virtual microphone via `pw-loopback`. Use `--name` to customize the node name (default: `virtual-mic`).

```bash
qt-ai-dev-tools audio virtual-mic start
qt-ai-dev-tools audio virtual-mic start --name "test-mic"
```

**`audio virtual-mic stop`** -- stop the virtual microphone.

```bash
qt-ai-dev-tools audio virtual-mic stop
```

**`audio virtual-mic play audio.wav`** -- feed an audio file into the virtual mic. Use `--name` to target a specific node.

```bash
qt-ai-dev-tools audio virtual-mic play /tmp/test-audio.wav
qt-ai-dev-tools audio virtual-mic play /tmp/test-audio.wav --name "test-mic"
```

**`audio record --duration 3 -o /tmp/out.wav`** -- record from PipeWire for N seconds (default 5). Use `--loopback` to capture output audio instead of input.

```bash
qt-ai-dev-tools audio record --duration 3 -o /tmp/out.wav
qt-ai-dev-tools audio record --duration 5 -o /tmp/out.wav --loopback
```

**`audio verify /tmp/out.wav`** -- check that a recording is not silence. Returns max amplitude, RMS amplitude, and duration. Exit code 1 if the file is silent. Use `--threshold` to adjust RMS sensitivity (default 0.001). Add `--json` for structured output.

```bash
qt-ai-dev-tools audio verify /tmp/out.wav
#   Status: NOT SILENT
#   Max amplitude: 0.234567
#   RMS amplitude: 0.045678
#   Duration: 3.00s
qt-ai-dev-tools audio verify /tmp/out.wav --threshold 0.01 --json
```

**`audio sources`** -- list available audio sources (inputs). Add `--json`.

```bash
qt-ai-dev-tools audio sources
qt-ai-dev-tools audio sources --json
```

**`audio status`** -- list active audio streams. Add `--json`.

```bash
qt-ai-dev-tools audio status
qt-ai-dev-tools audio status --json
```

### Audio Recipe

Full audio round-trip test: create a virtual mic, feed audio, record the output, verify it is not silence, clean up:

```bash
qt-ai-dev-tools audio virtual-mic start
qt-ai-dev-tools audio virtual-mic play /tmp/test-audio.wav
qt-ai-dev-tools audio record --duration 3 -o /tmp/out.wav --loopback
qt-ai-dev-tools audio verify /tmp/out.wav
qt-ai-dev-tools audio virtual-mic stop
```

## Troubleshooting

**"No tray items found"** -- check that `snixembed` is running in the VM (`vm run "pgrep snixembed"`). The app must use SNI (StatusNotifierItem), not XEmbed. `QSystemTrayIcon` typically supports SNI when a D-Bus watcher is present. Run `tray list` again after the app has fully started -- tray registration can be delayed.

**"No notifications captured"** -- increase the timeout (`--timeout 15`). Verify `dbus-monitor` is available in the VM. Check whether the app uses standard `org.freedesktop.Notifications` or a custom backend. `QSystemTrayIcon.showMessage()` may bypass the standard notification path. Try triggering the notification again while `notify listen` is active.

**"Audio verify reports silence"** -- check PipeWire is running with `audio status`. Verify the virtual mic is connected with `audio sources`. Ensure the app is actually using the virtual mic as its input source. Try a longer recording duration. Lower the threshold with `--threshold 0.0001` if the signal is very quiet.

**"Virtual mic start fails"** -- PipeWire must be running. Check with `vm run "systemctl --user status pipewire"`. The `pw-loopback` tool must be installed (`pipewire-utils` package).

## Related Skills

- **qt-dev-tools-setup** -- install qt-ai-dev-tools, configure the VM, verify the environment.
- **qt-app-interaction** -- inspect widgets, click buttons, type text, verify state via AT-SPI.
- **qt-form-and-input** -- fill forms, handle combo boxes, navigate tabs, work with text fields.
- **qt-runtime-eval** -- execute Python code inside running Qt apps via the bridge.
