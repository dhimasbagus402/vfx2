#!/bin/bash

echo "=== Installing dependencies ==="
sudo apt install -y python3-tk
sudo apt install -y yad

echo "=== Creating desktop shortcut ==="

DESKTOP_FILE="$HOME/Desktop/mt_manager.desktop"

cat > "$DESKTOP_FILE" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=MT Manager
Comment=MT Manager App
Exec=python3 $HOME/vfx/apps/mt_manager.py
Icon=$HOME/vfx/apps/mt_manager.png
Terminal=false
StartupNotify=true
EOF

chmod +x "$DESKTOP_FILE"

# Untuk GNOME: tandai sebagai trusted agar bisa dijalankan
if command -v gio &> /dev/null; then
    gio set "$DESKTOP_FILE" metadata::trusted true
fi

echo "=== Done! Shortcut 'MT Manager' sudah dibuat di Desktop ==="
