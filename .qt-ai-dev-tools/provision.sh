#!/usr/bin/env bash
set -euo pipefail

echo "==> Installing system deps"
apt-get update -qq
apt-get install -y --no-install-recommends \
    make \
    nano \
    curl \
    wget \
    jq \
    ca-certificates \
    tree \
    micro \
    net-tools \
    traceroute \
    xvfb \
    x11-utils \
    xdotool \
    scrot \
    openbox \
    dbus-x11 \
    at-spi2-core \
    libatk-adaptor \
    python3-pip \
    python3-dbus \
    python3-gi \
    gir1.2-atspi-2.0 \
    pulseaudio \
    libpulse0 \
    libegl1 \
    libgl1 \
    libxcb-cursor0 \
    libxcb-icccm4 \
    libxcb-keysyms1 \
    libxcb-randr0 \
    libxcb-render-util0 \
    libxcb-xinerama0 \
    libxcb-xkb1 \
    libxkbcommon-x11-0 \
    sox \
    ffmpeg \
    xclip \
    xsel \
    dunst \
    stalonetray \
    pipewire \
    pipewire-pulse \
    wireplumber \
    gcc \
    valac \
    libgtk-3-dev \
    libdbusmenu-gtk3-dev \
    libdbusmenu-glib-dev \
    fonts-dejavu

echo "==> Installing Python packages (system)"
pip3 install --quiet --break-system-packages \
    basedpyright

# ── uv + project venv ─────────────────────────────────────────────────────
# Install uv so `uv run pytest` works inside the VM with all dev deps.
# The venv lives outside /vagrant to avoid rsync conflicts with the host.
echo "==> Installing uv"
curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="/opt/uv" sh
ln -sf /opt/uv/uv /usr/local/bin/uv
ln -sf /opt/uv/uvx /usr/local/bin/uvx

echo "==> Creating project venv with uv sync"
VM_VENV="/home/vagrant/.venv-qt-ai-dev-tools"
su - vagrant -c "UV_PROJECT_ENVIRONMENT=$VM_VENV uv sync --project /vagrant"

# Link system-only gi/pygobject into the venv (not pip-installable).
# gi.repository.Atspi requires: gi package, _gi C extension, pygtkcompat.
# NOTE: apt installs gi into /usr/lib/python3/dist-packages/, NOT the path
# returned by sysconfig.get_path('purelib') (/usr/local/lib/...).  We locate
# gi by actually importing it, which always gives the real path.
VENV_SITE=$("$VM_VENV/bin/python" -c "import sysconfig; print(sysconfig.get_path('purelib'))")
SYS_GI_DIR=$(python3 -c "import gi, os; print(os.path.dirname(gi.__file__))")
SYS_SITE=$(dirname "$SYS_GI_DIR")
for name in gi pygtkcompat; do
    if [ -e "$SYS_SITE/$name" ]; then
        ln -sf "$SYS_SITE/$name" "$VENV_SITE/$name"
    fi
done
# Link compiled _gi*.so extensions (may live next to gi/ in the same site dir)
for so in "$SYS_SITE"/_gi*.so; do
    [ -e "$so" ] && ln -sf "$so" "$VENV_SITE/"
done

# ── Build and install snixembed (SNI tray proxy) ───────────────────────────
# snixembed proxies StatusNotifierItem (SNI) D-Bus tray icons into the XEmbed
# tray provided by stalonetray.  Not packaged for Ubuntu 24.04, so we build
# from source and apply a patch to fix the RegisteredStatusNotifierItems
# property (upstream returns empty).
echo "==> Building snixembed from source"
SNIXEMBED_BUILD=$(mktemp -d)
git clone --depth 1 https://git.sr.ht/~steef/snixembed "$SNIXEMBED_BUILD/snixembed"

cat > "$SNIXEMBED_BUILD/snixembed/src/statusnotifierwatcher.vala" << 'VALA_EOF'
[DBus (name = "org.kde.StatusNotifierWatcher")]
public class StatusNotifierWatcher : Object {
    public const string NAME = "org.kde.StatusNotifierWatcher";
    public const string OBJECT = "/StatusNotifierWatcher";

    GenericArray<string> _registered_items;

    // Methods
    public void register_status_notifier_item(string service, BusName sender) {
        var name = service;
        if (!DBus.is_name(service)) {
            // appindicator fallback
            name = sender;
        }

        if (watchers.contains(name)) {
            stdout.printf("%s (%s) is already registered; ignoring registration\n", name, service);
            return;
        }

        watchers[name] = Bus.watch_name(BusType.SESSION, name, BusNameWatcherFlags.NONE,
            (conn, item, owner) => status_notifier_item_registered(service, sender),
            (conn, item) => {
                Bus.unwatch_name(watchers[name]);
                watchers.remove(name);
                _registered_items.remove(item);
                status_notifier_item_unregistered(item);
            });
        _registered_items.add(name);
    }

    public void register_status_notifier_host(string service) {
        // We probably don't have to anything here, as we just proxy
    }

    // Properties
    public string[] registered_status_notifier_items {
        owned get {
            return _registered_items.data;
        }
    }
    public bool is_status_notifier_host_registered { get { return true; } }

    // This property is undocumented yet KDE implements it
    public int protocol_version { get { return 0; } }

    // Signals
    internal signal bool status_notifier_item_registered(string service, BusName sender);
    public signal bool status_notifier_item_unregistered(string service);
    public signal bool status_notifier_host_registered();

    // Internal
    HashTable<string, uint> watchers;
    construct {
        watchers = new HashTable<string, uint>(str_hash, str_equal);
        _registered_items = new GenericArray<string>();
    }
}
VALA_EOF

make -C "$SNIXEMBED_BUILD/snixembed"
make -C "$SNIXEMBED_BUILD/snixembed" install
rm -rf "$SNIXEMBED_BUILD"

# ── Xvfb service (system) ───────────────────────────────────────────────────
echo "==> Setting up Xvfb as a service"
cat > /etc/systemd/system/xvfb.service << 'EOF'
[Unit]
Description=Virtual framebuffer X server
After=network.target

[Service]
ExecStart=/usr/bin/Xvfb :99 -screen 0 1920x1080x24 -ac
Restart=on-failure
User=vagrant

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now xvfb

# ── Desktop session service (user) ──────────────────────────────────────────
# Runs dbus session + openbox + at-spi as a single unit for the vagrant user.
# This way every SSH command that sources .bashrc gets a working AT-SPI tree.
#
# The startup logic lives in a standalone script to avoid systemd ExecStart
# quoting issues with bash one-liners containing grep/sed.

mkdir -p /home/vagrant/.local/bin
mkdir -p /home/vagrant/.config/systemd/user

cat > /home/vagrant/.local/bin/desktop-session.sh << 'EOF'
#!/bin/bash
# Desktop session startup: openbox + AT-SPI + tray + audio
set -eu

/usr/libexec/at-spi-bus-launcher --launch-immediately &

# Wait for the AT-SPI bus to become available (up to 5 attempts)
ATSPI_ADDR=""
for _attempt in 1 2 3 4 5; do
  sleep 0.5
  ATSPI_ADDR=$(dbus-send --session --dest=org.a11y.Bus --print-reply \
    /org/a11y/bus org.a11y.Bus.GetAddress 2>/dev/null | \
    grep 'string "' | sed 's/.*string "//;s/"//') || true
  if [ -n "$ATSPI_ADDR" ]; then
    break
  fi
done

openbox &
sleep 0.5

# Set AT_SPI_BUS on root window AFTER openbox starts — openbox takes ownership
# of the root window and may clear properties set before it launches.
if [ -n "$ATSPI_ADDR" ]; then
  xprop -root -f AT_SPI_BUS 8s -set AT_SPI_BUS "$ATSPI_ADDR"
fi
snixembed &
sleep 0.5
stalonetray --kludges=force_icons_size -i 24 --grow-gravity=NE &
sleep 0.5
dunst &
sleep 0.5
pipewire &
sleep 0.5
wireplumber &
sleep 0.5
pipewire-pulse &

wait
EOF
chmod +x /home/vagrant/.local/bin/desktop-session.sh

cat > /home/vagrant/.config/systemd/user/desktop-session.service << 'EOF'
[Unit]
Description=Headless desktop session (openbox + AT-SPI)
After=default.target

[Service]
Type=simple
Environment=DISPLAY=:99
ExecStart=/home/vagrant/.local/bin/desktop-session.sh
Restart=on-failure
RestartSec=2

[Install]
WantedBy=default.target
EOF

chown -R vagrant:vagrant /home/vagrant/.local
chown -R vagrant:vagrant /home/vagrant/.config

# Enable lingering so user services start at boot (not just on login)
loginctl enable-linger vagrant

# Start the user service
su - vagrant -c "XDG_RUNTIME_DIR=/run/user/\$(id -u) systemctl --user daemon-reload"
su - vagrant -c "XDG_RUNTIME_DIR=/run/user/\$(id -u) systemctl --user enable --now desktop-session.service"

# ── Environment (.bashrc, idempotent) ───────────────────────────────────────
MARKER="# === qt-dev-env ==="
if ! grep -q "$MARKER" /home/vagrant/.bashrc; then
    cat >> /home/vagrant/.bashrc << EOF

$MARKER
export DISPLAY=:99
export QT_QPA_PLATFORM=xcb
export QT_ACCESSIBILITY=1
export QT_LINUX_ACCESSIBILITY_ALWAYS_ON=1
export QT_AI_DEV_TOOLS_VM=1
export QT_AI_DEV_TOOLS_BRIDGE=1
export UV_PROJECT_ENVIRONMENT=\$HOME/.venv-qt-ai-dev-tools

# Inherit the user dbus session (from desktop-session.service)
if [ -z "\$DBUS_SESSION_BUS_ADDRESS" ]; then
    export DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/\$(id -u)/bus"
fi
EOF
fi

echo "==> Done."
