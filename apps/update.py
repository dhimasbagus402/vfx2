"""
update.py — MT Manager
Logika update aplikasi (jalankan update.sh, cek update otomatis saat startup).
Tidak mengimport tkinter sama sekali.
"""

import subprocess
import threading
from pathlib import Path


def run_update_bg(update_sh: Path, on_done, on_fail):
    """Jalankan update.sh, panggil on_done(already_updated) atau on_fail(msg)."""
    def _run():
        try:
            proc = subprocess.run(
                ["bash", str(update_sh)],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            )
            out = proc.stdout or ""
            if proc.returncode != 0:
                err = out.strip().splitlines()[-1] if out.strip() else f"exit {proc.returncode}"
                on_fail(err)
            elif "already up to date" in out.lower():
                on_done(True)
            else:
                on_done(False)
        except Exception as e:
            on_fail(str(e))
    threading.Thread(target=_run, daemon=True).start()


def run_auto_update_bg(update_sh: Path, on_new_update, on_current, on_error):
    """Silent startup update check."""
    def _run():
        try:
            proc = subprocess.run(
                ["bash", str(update_sh)],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=60,
            )
            out = proc.stdout or ""
            if proc.returncode == 0 and "already up to date" not in out.lower():
                on_new_update()
            else:
                on_current()
        except subprocess.TimeoutExpired:
            on_error("Auto-update: timeout.")
        except Exception as e:
            on_error(f"Auto-update: {e}")
    threading.Thread(target=_run, daemon=True).start()
