#!/bin/bash
echo "=== Pulling latest update ==="
git -C ~/vfx pull
chmod +x ~/vfx/update.sh
echo "=== Running install.sh ==="
bash ~/vfx/doinstall.sh
echo "=== Update selesai! ==="
