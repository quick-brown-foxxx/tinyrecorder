---
name: qt-dev-tools-setup
description: >
  Set up qt-ai-dev-tools for AI-driven Qt/PySide app interaction.
  Use when asked to "set up qt-ai-dev-tools", "initialize workspace",
  "configure VM for Qt testing", "boot the VM", "install qt-ai-dev-tools",
  or when starting a new project that needs headless Qt UI testing.
  Covers installation, workspace init, VM boot, environment verification,
  and self-update. Do NOT use for interacting with apps — see
  qt-app-interaction skill instead.
---

# Set up qt-ai-dev-tools

## When to use

- Setting up qt-ai-dev-tools for the first time (install, workspace init, VM boot)
- Verifying or repairing the VM environment (services, AT-SPI, display)
- Updating an existing qt-ai-dev-tools installation

## When NOT to use

- Interacting with a running Qt app (inspecting widgets, clicking, typing) -- use `qt-app-interaction`
- Executing code inside a running Qt app -- use `qt-runtime-eval`
- Working with clipboard, file dialogs, tray, notifications, or audio -- use `qt-form-and-input` or `qt-desktop-integration`

---

Follow these steps in order. Each step must succeed before proceeding.

## Step 1: Install the toolkit

**Option A -- use via uvx** (recommended, no installation needed):
```bash
uvx qt-ai-dev-tools workspace init
```
This runs directly without installing anything. All `qt-ai-dev-tools` commands work via `uvx qt-ai-dev-tools <command>`.

**Option B -- local copy** (advanced, you own the code):
```bash
uvx qt-ai-dev-tools install-and-own ./qt-ai-dev-tools --yes-I-will-maintain-it
cd qt-ai-dev-tools
uv sync
```
This copies the full toolkit source into your project. You own and maintain it.

Verify the CLI works:

```bash
# Option A:
uvx qt-ai-dev-tools --help
# Option B:
uv run qt-ai-dev-tools --help
```

Expected: help text listing available commands (tree, click, type, screenshot, vm, workspace, etc.).

**Prerequisites:** Linux host, `uv` installed, Vagrant with libvirt provider (vagrant-libvirt plugin + QEMU/KVM).

> **Note:** Commands below use `qt-ai-dev-tools` as the command prefix. If using Option A (uvx), prefix with `uvx`: `uvx qt-ai-dev-tools <command>`. If using Option B (local copy), prefix with `uv run`: `uv run qt-ai-dev-tools <command>`.

## Step 2: Initialize workspace

Generate Vagrantfile and provision.sh:

```bash
qt-ai-dev-tools workspace init
```

This creates `.qt-ai-dev-tools/Vagrantfile` and `.qt-ai-dev-tools/provision.sh`.

**WARNING: Review the Vagrantfile before proceeding.** You may need to adjust:
- `--static-ip` if DHCP is unreliable on your network (common with libvirt)
- `--memory` and `--cpus` for your machine's resources
- Network configuration for your libvirt setup

Re-run `workspace init` with options to change settings: `qt-ai-dev-tools workspace init --static-ip 192.168.121.100 --memory 8192`.

If this is a personal/local setup (not shared across the team), add `.qt-ai-dev-tools/` to `.gitignore`.

## Step 3: Start the VM

```bash
uv run qt-ai-dev-tools vm up
```

First boot: ~10 minutes (box download + provisioning). Subsequent boots: ~30 seconds.

Use `--silent` to suppress streaming output, or `-vv` to watch provisioning progress instead of waiting in silence.

## Step 4: Verify environment

Run three checks. All must pass.

**Check 1 -- Services:**

```bash
uv run qt-ai-dev-tools vm status
```

Expected: Xvfb, openbox, and AT-SPI services listed as running.

**Check 2 -- AT-SPI bus:**

```bash
uv run qt-ai-dev-tools apps
```

Expected: command succeeds without errors. No apps listed is fine -- it means no Qt app is running yet.

**Check 3 -- Display:**

```bash
uv run qt-ai-dev-tools screenshot -o /tmp/test.png
```

Expected: PNG file created showing the openbox desktop.

## Step 5: Launch target app

Sync project files to the VM, start the app, and wait for it to register on the AT-SPI bus:

```bash
uv run qt-ai-dev-tools vm sync
uv run qt-ai-dev-tools vm run "python3 /vagrant/app/main.py &"
uv run qt-ai-dev-tools wait --app main.py --timeout 15
```

Vagrant mounts the project root as `/vagrant` inside the VM. Your app files are at `/vagrant/` plus their path relative to the project root.

Key concept: `vm run` is for arbitrary commands inside the VM. All qt-ai-dev-tools UI commands (tree, click, type, screenshot, etc.) work from host or VM -- no wrapping needed.

If the app exits immediately, run it in the foreground to see errors:

```bash
uv run qt-ai-dev-tools vm run "python3 /vagrant/app/main.py"
```

## Step 6: Confirm interaction

Verify the app is visible to AT-SPI:

```bash
uv run qt-ai-dev-tools tree
```

Expected output:

```
[application] "main.py"
  [frame] "My App" @(720,387 480x320)
    [filler] ""
      [label] "Ready" @(736,403 448x14)
      [push button] "Save" @(1104,429 80x22)
```

Take a screenshot to visually confirm:

```bash
uv run qt-ai-dev-tools screenshot -o /tmp/verify.png
```

Setup is complete when both `tree` and `screenshot` show the running app.

## Self-update

Update an existing shadcn-style installation (preserves config and notes):

```bash
uv run qt-ai-dev-tools self-update ./qt-ai-dev-tools
```

The argument is the path to the existing toolkit directory. This updates source files while keeping your local modifications to config.

## Debugging

When something goes wrong, use verbose mode to see exactly what commands are being executed:

```bash
# Show all shell commands (vagrant, xdotool, scrot, etc.):
uv run qt-ai-dev-tools -v vm up

# Show commands + their full stdout/stderr output:
uv run qt-ai-dev-tools -vv vm status

# Suppress streaming output (capture only, print on error):
uv run qt-ai-dev-tools --silent vm up

# Preview what would run without executing:
uv run qt-ai-dev-tools --dry-run tree
```

Logs are always written to `~/.local/state/qt-ai-dev-tools/logs/qt-ai-dev-tools.log`, even without `-v`. Check this file for post-mortem debugging.

## File sync

Keep host files in sync with the VM:

- **Manual:** `uv run qt-ai-dev-tools vm sync` -- run before each test cycle
- **Automatic:** `uv run qt-ai-dev-tools vm sync-auto` -- watches for changes in background

## Troubleshooting

### DHCP timeout (most common)

**Symptom:** `vm up` hangs at "Waiting for machine to get an IP address..."

**Cause:** vagrant-libvirt creates the `vagrant-libvirt` network with DHCP range starting at `.1`, which collides with the host bridge IP.

**Fix:** Recreate the network with a corrected DHCP range, then retry:

```bash
virsh -c qemu:///system net-destroy vagrant-libvirt 2>/dev/null
virsh -c qemu:///system net-undefine vagrant-libvirt 2>/dev/null

cat > /tmp/vagrant-libvirt-net.xml << 'EOF'
<network>
  <name>vagrant-libvirt</name>
  <forward mode="nat"/>
  <bridge name="virbr1" stp="on" delay="0"/>
  <ip address="192.168.121.1" netmask="255.255.255.0">
    <dhcp>
      <range start="192.168.121.2" end="192.168.121.254"/>
    </dhcp>
  </ip>
</network>
EOF

virsh -c qemu:///system net-define /tmp/vagrant-libvirt-net.xml
virsh -c qemu:///system net-start vagrant-libvirt
virsh -c qemu:///system net-autostart vagrant-libvirt

uv run qt-ai-dev-tools vm destroy
uv run qt-ai-dev-tools vm up
```

Alternative: re-run `workspace init --static-ip 192.168.121.100` to bypass DHCP entirely.

### AT-SPI not seeing the app

**Symptom:** `tree` shows nothing or errors.

**Fixes by cause:**
- **App not running:** Launch it and wait: `vm run "python3 /vagrant/app.py &"` then `wait --app app.py`
- **Xvfb down:** Check `vm run "pgrep Xvfb"`. Restart: `vm run "sudo systemctl start xvfb"`
- **D-Bus inactive:** Check `vm run "pgrep at-spi"`. Restart: `vm run "systemctl --user restart desktop-session"`
- **Wrong DISPLAY:** App must run on `:99`. The VM sets this automatically; custom scripts may need `DISPLAY=:99`

### PySide6 import error

**Symptom:** `ImportError: libEGL.so.1: cannot open shared object file`

**Cause:** Missing system libraries in the VM.

**Fix:**
```bash
uv run qt-ai-dev-tools vm run "sudo apt-get install -y libegl1 libxkbcommon0"
```

### Blank screenshots

**Symptom:** Screenshot shows nothing or only the desktop background.

**Fix:** Verify both services are running:
```bash
uv run qt-ai-dev-tools vm run "pgrep Xvfb"
uv run qt-ai-dev-tools vm run "pgrep openbox"
```

If either is missing, restart:
```bash
uv run qt-ai-dev-tools vm run "sudo systemctl start xvfb"
uv run qt-ai-dev-tools vm run "systemctl --user restart desktop-session"
```

## Next steps

Setup complete. Use the related skills for specific tasks:

- **`qt-app-interaction`** -- inspect widgets, click, type, verify results (the core workflow loop)
- **`qt-runtime-eval`** -- execute code inside running Qt apps via the bridge
- **`qt-form-and-input`** -- clipboard and file dialog automation
- **`qt-desktop-integration`** -- system tray, notifications, and audio
