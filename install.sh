#!/bin/bash
echo "=== Pulling latest update ==="
git -C ~/vfx2 pull
chmod +x ~/vfx2/update.sh
echo "=== Running install.sh ==="
bash ~/vfx2/doinstall.sh
echo "=== Update selesai! ==="
