"""
update.py — MT Manager
Logika update aplikasi (jalankan update.sh, cek update otomatis saat startup,
serta handler klik tombol Update di sidebar).
"""

import subprocess
import threading
from pathlib import Path

from widgets import themed_popup


def handle_update_click(app):
    """Handler untuk klik tombol Update di sidebar.

    app: instance MTManager — butuh app.root, app._status(),
         dan app._show_update_popup(update_sh).
    """
    update_sh = Path.home() / "vfx" / "update.sh"
    if not update_sh.exists():
        themed_popup(app.root, "error", "Update Failed",
            f"Script not found:\n{update_sh}")
        return
    app._status("Running update...")
    app._show_update_popup(update_sh)


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


def auto_update_check(app):
    """Cek update otomatis saat startup (silent check).

    app: instance MTManager — butuh app.root, app._status(),
         dan app._show_auto_update_result().
    """
    update_sh = Path.home() / "vfx" / "update.sh"
    if not update_sh.exists():
        # Tidak ada updater -> tak akan ada popup update, langsung cek What's New
        # (mis. saat launch pertama setelah restart pasca-update manual).
        app.root.after(0, app._whats_new_check)
        return
    app._status("Checking for updates automatically\u2026")

    def _on_new():
        # Update baru terpasang -> tampilkan popup restart. What's New SENGAJA
        # tidak dipanggil di sini; akan muncul pada launch berikutnya.
        app.root.after(0, lambda: app._show_auto_update_result(True))

    def _on_current():
        def _ui():
            app._status("App is up-to-date.")
            app._whats_new_check()
        app.root.after(0, _ui)

    def _on_err(msg):
        def _ui(m=msg):
            app._status(m)
            app._whats_new_check()
        app.root.after(0, _ui)

    run_auto_update_bg(update_sh, _on_new, _on_current, _on_err)
