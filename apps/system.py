"""
backend.py — MT Manager
Semua logika bisnis, I/O filesystem, konfigurasi, dan konstanta desain.
Tidak mengimport tkinter sama sekali.
"""

import re
import json
import os
import shutil
import subprocess
import threading
import datetime
import time
from pathlib import Path
from urllib.request import urlopen, Request

__version__ = "2.0"

# ── Config ────────────────────────────────────────────────────────────────────
CONFIG_PATH = Path.home() / ".config" / "mt_manager" / "settings.json"


def load_config() -> dict:
    try:
        if CONFIG_PATH.exists():
            return json.loads(CONFIG_PATH.read_text())
    except Exception:
        pass
    return {}


def save_config(data: dict):
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps(data, indent=2))
    except Exception:
        pass


# ── Design Tokens ─────────────────────────────────────────────────────────────
BG          = "#0a0e11"
BG2         = "#11181e"
BG3         = "#171f26"
BG4         = "#0d171f"
ACCENT      = "#26b0ff"
ACCENT1     = "#ffffff"
ACCENT4     = "#97e0f7"
ACCENT3     = "#00c896"
ACCENT2     = "#ffffff"
ACCENT_DIM  = "#033154"
BORDER      = "#1c2438"
BORDER2     = "#263045"
DANGER      = "#ff5b5b"
WARN        = "#f0a030"
FG          = "#e8edf5"
FG2         = "#aeb9c9"
FG3         = "#717c8f"
WHITE       = "#ffffff"
PURPLE      = "#a78bfa"

# ── Paths ─────────────────────────────────────────────────────────────────────
ALLOWED_ROOT = Path.home()
DOCS_DIR     = Path.home() / "Documents"

# ── Table Config ──────────────────────────────────────────────────────────────
TABLE_FONT_SIZE    = 10
TABLE_HEADING_SIZE = 9
TABLE_COLUMNS = [
    ("name",     "NAME",     0,   "w", True),
    ("size",     "SIZE",     90,  "e", False),
    ("modified", "MODIFIED", 130, "e", False),
]

# ── Category ──────────────────────────────────────────────────────────────────
CAT_COL_WIDTH = 100
CAT_COLORS = {
    "Expert":    "#00c896",
    "Indicator": "#f0a030",
    "Script":    "#a78bfa",
    "Log":       "#e8edf5",
}

# ── Autostart ─────────────────────────────────────────────────────────────────
AUTOSTART_DIR    = Path.home() / ".config" / "autostart"
AS_COL_WIDTH     = 30
AS_TRACK_W       = 34
AS_TRACK_H       = 18
AS_THUMB_R       = 7
AS_COLOR_ON      = "#00c896"
AS_COLOR_OFF     = "#2a3545"
AS_THUMB_COL     = "#ffffff"
AS_TRACK_OFF_BDR = "#3a4a5f"

# ── Checkbox ──────────────────────────────────────────────────────────────────
CHK_COL_WIDTH = 36
CHK_FONT_SIZE = 14
CHK_CHAR_OFF  = "\u25a1"
CHK_CHAR_ON   = "\u2713"
TABLE_ROW_HEIGHT = 30

# ── Archive types ─────────────────────────────────────────────────────────────
EXTRACT_EXTS = {".zip", ".rar", ".tar", ".gz", ".bz2", ".xz", ".7z",
                ".tar.gz", ".tar.bz2", ".tar.xz"}

# ── Font ──────────────────────────────────────────────────────────────────────
# Daftar prioritas; resolve_font() memakai yang pertama tersedia di sistem.
# Entri terakhir ("Helvetica"/"Courier") selalu ada di Tk sebagai fallback.
FONT        = ("Inter", "SF Pro Text", "Segoe UI", "Noto Sans",
               "Ubuntu", "Cantarell", "DejaVu Sans", "Helvetica")
FONT_MONO   = ("JetBrains Mono", "Cascadia Mono", "SF Mono", "Consolas",
               "Noto Sans Mono", "DejaVu Sans Mono", "Courier")
SIDEBAR_W   = 250


# ── Disk helpers ────────────────────────────────────────────────────────────────
def disk_usage(path=None) -> tuple:
    """Return (free_bytes, total_bytes) untuk partisi yang memuat `path`.
    Bila path None/tidak ada, naik ke ancestor terdekat; fallback ke home."""
    try:
        target = Path(path) if path else ALLOWED_ROOT
        while not target.exists() and target != target.parent:
            target = target.parent
        if not target.exists():
            target = ALLOWED_ROOT
        u = shutil.disk_usage(str(target))
        return u.free, u.total
    except Exception:
        return 0, 0


def fmt_disk(n: int) -> str:
    """Bytes → string ringkas (GB/TB)."""
    gb = n / (1024 ** 3)
    if gb >= 1024:
        return f"{gb / 1024:.1f} TB"
    if gb >= 10:
        return f"{gb:.0f} GB"
    return f"{gb:.1f} GB"


# ── Archive helpers ────────────────────────────────────────────────────────────
def is_archive(path: Path) -> bool:
    name = path.name.lower()
    return any(name.endswith(ext) for ext in EXTRACT_EXTS)


def extract_file(path: Path, dest_dir: Path) -> tuple[bool, str]:
    """Ekstrak arsip ke dest_dir. Return (ok, message)."""
    try:
        if shutil.which("xarchiver"):
            r = subprocess.run(
                ["xarchiver", "--extract-to", str(dest_dir), str(path)],
                capture_output=True, text=True, timeout=120,
            )
            if r.returncode == 0:
                return True, ""
            return False, r.stderr.strip().splitlines()[-1] if r.stderr.strip() else "exit != 0"
        # fallback: Python zipfile (lazy import)
        if path.suffix == ".zip":
            import zipfile  # noqa: PLC0415 — intentional lazy import
            with zipfile.ZipFile(path, "r") as zf:
                zf.extractall(dest_dir)
            return True, ""
        return False, "xarchiver not found and the format is not supported by the fallback."
    except Exception as e:
        return False, str(e)


# ── yad file picker ────────────────────────────────────────────────────────────
def yad_pick_file(title: str, filetypes: list[str], start_dir: Path,
                  root_widget=None) -> str | None:
    """Buka yad file picker. Mengembalikan path string atau None.

    Semua ekstensi digabung menjadi SATU --file-filter agar langsung tampil
    semua file yang cocok tanpa harus memilih dari dropdown filter.
    Format yad: "Label | *.ext1 *.ext2 ..."
    """
    cmd = ["yad", "--file-selection",
           "--title", title,
           "--filename", str(start_dir) + "/",
           "--button=Select:0", "--button=Cancel:1"]
    if filetypes:
        # Buat label dari ekstensi: "*.ex4 *.ex5 *.mq4 *.mq5"
        exts  = " ".join(filetypes)
        label = exts.replace("*.", "").replace(" ", "/").upper()  # "EX4/EX5/MQ4/MQ5"
        # Satu filter gabungan → semua ekstensi tampil sekaligus
        cmd += ["--file-filter", f"{label} | {exts}"]
        # Filter "Semua File" sebagai pilihan kedua
        cmd += ["--file-filter", "All Files | *"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if r.returncode == 0:
            return r.stdout.strip()
    except Exception:
        pass
    return None


# ── Themed popup helper (message-only, non-GUI) ────────────────────────────────
# Actual popup dibuat di frontend.py; ini hanya data model.
POPUP_ICONS = {
    "success": ("\u2713", "#5ecf3e"),
    "error":   ("\u2717", DANGER),
    "warning": ("\u26a0", WARN),
    "info":    ("\u2139", ACCENT),
}


# ── Installer detection ───────────────────────────────────────────────────────
def detect_installer_type(exe_path: Path) -> str:
    """Baca byte header .exe untuk deteksi Inno Setup vs NSIS vs unknown.
    Hanya baca 8 KB pertama — signature selalu ada di awal file.
    """
    _READ_SIZE = 8192
    try:
        with exe_path.open("rb") as fh:
            data = fh.read(_READ_SIZE)
        if b"Inno Setup" in data:
            return "inno"
        if b"Nullsoft" in data or b"NSIS" in data:
            return "nsis"
        # Fallback: cek sisa sampai 64 KB jika tidak ditemukan di 8 KB pertama
        with exe_path.open("rb") as fh:
            data = fh.read(65536)
        if b"Inno Setup" in data:
            return "inno"
        if b"Nullsoft" in data or b"NSIS" in data:
            return "nsis"
    except Exception:
        pass
    return "unknown"


def try_silent_install(installer_path: Path, inst_type: str,
                       win_path: str, group_value: str,
                       log_fn=None) -> "subprocess.Popen | None":
    """Coba jalankan installer dalam mode silent."""
    try:
        if inst_type == "inno":
            cmd = ["wine", str(installer_path),
                   "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
                   f"/DIR={win_path}", f"/GROUP={group_value}"]
        elif inst_type == "nsis":
            cmd = ["wine", str(installer_path),
                   "/S", f"/D={win_path}", f"/GROUP={group_value}"]
        else:
            return None
        if log_fn:
            log_fn(f"Silent cmd: {' '.join(cmd)}")
        return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    except FileNotFoundError:
        raise
    except Exception as e:
        if log_fn:
            log_fn(f"Silent launch error: {e}")
        return None


def silent_succeeded(proc: "subprocess.Popen", install_dir_win: str,
                     timeout: int = 120) -> bool:
    """Tunggu proc selesai lalu verifikasi folder tujuan terbuat."""
    deadline = time.time() + timeout
    while proc.poll() is None:
        if time.time() > deadline:
            try:
                proc.kill()
            except Exception:
                pass
            return False
        time.sleep(0.5)
    try:
        wp = install_dir_win.replace("\\", "/").strip()
        if len(wp) >= 3 and wp[1] == ":":
            wp = wp[3:]
        linux_path = Path.home() / ".wine/drive_c" / wp.lstrip("/")
        return linux_path.exists()
    except Exception:
        return proc.returncode == 0


# ── Wine launcher ─────────────────────────────────────────────────────────────
def wine_launch_bg(exe_path: Path, on_success=None, on_error=None):
    """Jalankan exe via wine di daemon thread."""
    def _do():
        try:
            subprocess.Popen(
                ["wine", str(exe_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if on_success:
                on_success()
        except FileNotFoundError:
            if on_error:
                on_error("wine_not_found")
        except Exception as e:
            if on_error:
                on_error(str(e))
    threading.Thread(target=_do, daemon=True).start()


# ── find_exe ──────────────────────────────────────────────────────────────────
def find_exe(t: dict, mt4_name: str, mt5_name: str) -> Path | None:
    tp = Path(t["path"])
    if t["type"] == "MT5":
        c = tp / mt5_name
        return c if c.exists() else None
    ip = t.get("install_path")
    if ip:
        c = Path(ip) / mt4_name
        if c.exists():
            return c
    c = tp / mt4_name
    return c if c.exists() else None


# ── MT Install (background) ────────────────────────────────────────────────────
def run_mt_installer_bg(installer_path: Path, qty: int, base_name: str = "",
                        on_progress=None, on_finish=None):
    """Jalankan installer sebanyak qty kali di background thread."""
    base_stem = base_name.strip() or installer_path.stem
    inst_type = detect_installer_type(installer_path)

    def _do():
        errors   = []
        done_cnt = 0
        for i in range(qty):
            suffix      = f" {i + 1}" if qty > 1 else ""
            dir_value   = f"{base_stem}{suffix}"
            group_value = f"{base_stem}{suffix}"
            win_path    = f"C:\\Program Files (x86)\\{dir_value}"
            if on_progress:
                on_progress(i, qty, dir_value)
            silent_ok = False
            if inst_type in ("inno", "nsis"):
                try:
                    proc = try_silent_install(installer_path, inst_type, win_path, group_value)
                    if proc:
                        silent_ok = silent_succeeded(proc, win_path)
                        if silent_ok:
                            done_cnt += 1
                        else:
                            errors.append(f"[{i+1}] Silent install failed (folder not created).")
                except FileNotFoundError:
                    errors.append(f"[{i+1}] wine not found")
                    break
                except Exception as e:
                    errors.append(f"[{i+1}] silent error: {e}")
            if not silent_ok:
                try:
                    proc = subprocess.Popen(
                        ["wine", str(installer_path)],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    proc.wait()
                    done_cnt += 1
                except FileNotFoundError:
                    errors.append(f"[{i+1}] wine not found")
                    break
                except Exception as e:
                    errors.append(f"[{i+1}] {e}")
        if on_finish:
            on_finish(done_cnt, qty, installer_path.name, errors)

    threading.Thread(target=_do, daemon=True).start()


# ── MT Duplicate (background) ─────────────────────────────────────────────────
def run_mt_duplicate_bg(src_folder: Path, base_name: str, linux_base: Path,
                        qty: int, mt_type: str,
                        on_copy_progress=None, on_launch_progress=None,
                        on_finish=None, cancelled_flag: list = None,
                        custom_names: list = None):
    """Copy src_folder ke linux_base/<nama> N di background thread.

    custom_names: list of str dengan panjang qty — nama folder tiap duplikat.
                  Jika None atau elemen kosong, pakai nama default "<base_name> N".
    Launch MT hanya dilakukan SETELAH semua copy selesai, atau terhadap yang
    sudah ter-copy jika dibatalkan di tengah jalan.
    """
    if cancelled_flag is None:
        cancelled_flag = [False]

    def _do():
        errors   = []
        done_cnt = [0]
        launched = []

        for i in range(qty):
            if cancelled_flag[0]:
                break

            # Tentukan nama folder: custom jika ada, default jika tidak
            if custom_names and i < len(custom_names) and custom_names[i].strip():
                dst_name = custom_names[i].strip()
            else:
                dst_name = f"{base_name} {i + 2}"

            dst_path = linux_base / dst_name
            if on_copy_progress:
                on_copy_progress(i, qty, dst_name)
            try:
                final_path = dst_path
                if final_path.exists():
                    suffix = 2
                    while True:
                        candidate = linux_base / f"{dst_name} {suffix}"
                        if not candidate.exists():
                            final_path = candidate
                            break
                        suffix += 1
                shutil.copytree(str(src_folder), str(final_path))
                done_cnt[0] += 1
                launched.append(final_path)
            except Exception as e:
                errors.append(f"[{dst_name}] Copy failed: {e}")

        # Launch semua yang berhasil di-copy (baik selesai semua maupun di-cancel)
        exe_name = "terminal64.exe" if mt_type == "MT5" else "terminal.exe"
        launch_errors = []
        for j, dst_path in enumerate(launched):
            exe_path = dst_path / exe_name
            if on_launch_progress:
                on_launch_progress(j, len(launched), dst_path.name, exe_name)
            if not exe_path.exists():
                launch_errors.append(f"[{dst_path.name}] {exe_name} not found")
            else:
                try:
                    subprocess.Popen(
                        ["wine", str(exe_path)],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except Exception as e:
                    launch_errors.append(f"[{dst_path.name}] {e}")
            if j < len(launched) - 1:
                time.sleep(0.3)

        if on_finish:
            was_cancelled = cancelled_flag[0]
            on_finish(done_cnt[0], qty, src_folder.name,
                      errors + launch_errors, was_cancelled)

    threading.Thread(target=_do, daemon=True).start()


# ── MT Scan ───────────────────────────────────────────────────────────────────
def scan_terminals_bg(on_result):
    """Scan terminal MT di filesystem di background thread.
    on_result(found_list) dipanggil di background — caller wajib root.after() ke main thread.
    """
    home     = Path.home()
    _wine_c  = home / ".wine/drive_c"
    _games_c = home / "Games/drive_c"

    def _parse_origin(folder):
        origin = folder / "origin.txt"
        if not origin.exists():
            return folder.name[:22], None
        try:
            raw_bytes = origin.read_bytes()
        except OSError:
            return folder.name[:22], None
        raw = None
        for enc in ("utf-16", "utf-16-le", "utf-16-be", "utf-8", "latin-1"):
            try:
                dec = raw_bytes.decode(enc, errors="strict").replace("\x00", "").strip()
                if dec and ("\\" in dec or ":" in dec):
                    raw = dec
                    break
            except (UnicodeDecodeError, ValueError):
                continue
        if not raw:
            raw = raw_bytes.decode("utf-16", errors="ignore").replace("\x00", "").strip()
        if not raw:
            return folder.name[:22], None
        line   = raw.splitlines()[0].strip()
        name   = (line.replace("\\", "/").rstrip("/").split("/")[-1].strip()
                  or folder.name[:22])
        install = None
        try:
            wp = line.replace("\\", "/").strip().rstrip("/")
            if len(wp) >= 3 and wp[1] == ":":
                wp = wp[3:]
            if wp:
                for wc in (_wine_c, _games_c):
                    c = wc / wp
                    if c.exists():
                        install = c
                        break
        except Exception:
            pass
        return name, install

    def _worker():
        found = []
        # MT5
        for base in (_wine_c / "Program Files", _wine_c / "Program Files (x86)"):
            if not base.exists():
                continue
            for exe in base.rglob("terminal64.exe"):
                mt_dir = exe.parent
                mql5   = mt_dir / "MQL5"
                if mql5.exists():
                    found.append({
                        "type": "MT5", "name": mt_dir.name,
                        "path": str(mt_dir),
                        "experts":    mql5 / "Experts",
                        "indicators": mql5 / "Indicators",
                        "scripts":    mql5 / "Scripts",
                        "logs":       mt_dir / "logs",
                    })
        # MT4
        users_dir = _wine_c / "users"
        if users_dir.exists():
            for userdir in users_dir.iterdir():
                tb = userdir / "AppData/Roaming/MetaQuotes/Terminal"
                if not tb.exists():
                    continue
                for folder in tb.iterdir():
                    mql4 = folder / "MQL4"
                    if mql4.exists():
                        _n4, _ip4 = _parse_origin(folder)
                        if _ip4 is None:
                            continue
                        found.append({
                            "type": "MT4", "name": _n4,
                            "path": str(folder),
                            "install_path": _ip4,
                            "experts":    mql4 / "Experts",
                            "indicators": mql4 / "Indicators",
                            "scripts":    mql4 / "Scripts",
                            "logs":       folder / "logs",
                        })
        def _nat_key(item):
            parts = re.split(r"(\d+)", item["name"].lower())
            return [int(p) if p.isdigit() else p for p in parts]
        found.sort(key=lambda x: (0 if x["type"] == "MT4" else 1, _nat_key(x)))
        on_result(found)

    threading.Thread(target=_worker, daemon=True).start()


# ── Autostart helpers ─────────────────────────────────────────────────────────
def broker_already_installed(broker_name: str, version: str, terminals: list):
    """Return terminal dict pertama yang cocok bila broker `broker_name`
    dengan tipe MT `version` sudah terpasang, selain itu None.
    Pencocokan sederhana: nama broker (lowercase) muncul sebagai substring
    di nama terminal, dan tipe MT-nya sama (MT4 ≠ MT5 dianggap beda program)."""
    key = (broker_name or "").strip().lower()
    if not key:
        return None
    for t in terminals:
        if t.get("type") != version:
            continue
        if key in (t.get("name") or "").lower():
            return t
    return None


def autostart_desktop_path(t: dict) -> Path:
    safe = t["name"].replace(" ", "_").replace("/", "_")
    return AUTOSTART_DIR / f"{safe}.desktop"


def autostart_is_on(t: dict) -> bool:
    return autostart_desktop_path(t).exists()


def autostart_icon_path(t: dict) -> Path | None:
    if t["type"] == "MT5":
        ico = Path(t["path"]) / "Terminal.ico"
        return ico if ico.exists() else None
    ip = t.get("install_path")
    if ip:
        ico = Path(ip) / "terminal.ico"
        if ico.exists():
            return ico
    ico = Path(t["path"]) / "terminal.ico"
    return ico if ico.exists() else None


def autostart_set(t: dict, enable: bool, find_exe_fn) -> bool:
    """Enable/disable autostart untuk terminal t.
    find_exe_fn(t) → Path|None
    """
    dst = autostart_desktop_path(t)
    if enable:
        AUTOSTART_DIR.mkdir(parents=True, exist_ok=True)
        exe = find_exe_fn(t)
        if exe is None:
            return False
        icon_path = autostart_icon_path(t)
        icon_line = f"Icon={icon_path}\n" if icon_path else ""
        dst.write_text(
            "[Desktop Entry]\n"
            "Type=Application\n"
            f"Name={t['name']}\n"
            f"Exec=wine \"{exe}\"\n"
            f"{icon_line}"
            "Hidden=false\n"
            "NoDisplay=false\n"
            "X-GNOME-Autostart-enabled=true\n"
        )
        return True
    try:
        dst.unlink(missing_ok=True)
    except Exception:
        pass
    return False


# ── File list scanning ────────────────────────────────────────────────────────
def scan_terminal_files(t: dict) -> list[tuple]:
    """Return list of (label, fname, sz, mtime) untuk semua file di terminal t."""
    rows = []
    for key, label in (("experts", "Expert"), ("indicators", "Indicator"),
                        ("scripts", "Script"), ("logs", "Log")):
        folder = t.get(key)
        if not (folder and folder.exists()):
            continue
        try:
            entries = sorted(
                (e for e in os.scandir(folder) if e.is_file(follow_symlinks=False)),
                key=lambda e: e.name,
            )
        except OSError:
            continue
        for e in entries:
            try:
                st = e.stat()
            except OSError:
                continue
            kb = st.st_size / 1024
            sz = f"{kb:.1f} KB" if kb < 1024 else f"{kb / 1024:.2f} MB"
            mtime = datetime.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d")
            rows.append((label, e.name, sz, mtime))
    return rows


# ── Update helpers ────────────────────────────────────────────────────────────
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


# ── wget download ─────────────────────────────────────────────────────────────
def wget_download_bg(url: str, dest_dir: Path,
                     on_success, on_error, on_timeout):
    """Unduh url ke dest_dir via wget di background thread."""
    def _run():
        try:
            result = subprocess.run(
                ["wget", "-P", str(dest_dir), "--content-disposition", url],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode != 0:
                err_lines = result.stderr.strip().splitlines()
                err = err_lines[-1] if err_lines else "Unknown error"
                on_error(err)
                return
            files_after = sorted(dest_dir.iterdir(),
                                  key=lambda f: f.stat().st_mtime, reverse=True)
            downloaded = next((f for f in files_after if f.is_file()), None)
            on_success(downloaded)
        except subprocess.TimeoutExpired:
            on_timeout()
        except Exception as e:
            on_error(str(e))
    threading.Thread(target=_run, daemon=True).start()


# ── MT Broker Download List ───────────────────────────────────────────────────
# URL raw GitHub (bukan halaman HTML, tapi link "raw")
MT_BROKER_LIST_URL = (
    "https://raw.githubusercontent.com/digitalku/vfxwelcome/refs/heads/master/MT_BROKER_LIST.txt"
)


def _parse_broker_line(line: str) -> tuple | None:
    """Parse satu baris: MT4|Nama Broker|https://url.exe
    Baris kosong atau diawali '#' diabaikan.
    """
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    parts = line.split("|", 2)
    if len(parts) != 3:
        return None
    versi, nama, url = (p.strip() for p in parts)
    if versi not in ("MT4", "MT5") or not url.startswith("http"):
        return None
    return (versi, nama, url)


def fetch_broker_list(timeout: int = 10) -> tuple[list, str]:
    """Fetch dan parse daftar broker dari GitHub.
    Selalu ambil versi terbaru — bypass HTTP cache dengan header dan query param.

    Return:
        (list_of_tuples, error_msg)
        — Jika sukses: ([(versi, nama, url), ...], "")
        — Jika gagal:  ([], pesan_error)
    """
    try:
        import time as _time
        # Tambahkan timestamp sebagai query param agar URL selalu unik → tidak di-cache
        bust = int(_time.time())
        url  = f"{MT_BROKER_LIST_URL}?nocache={bust}"
        req  = Request(url, headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma":        "no-cache",
            "Expires":       "0",
        })
        with urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", errors="replace")
        result = [_parse_broker_line(line) for line in text.splitlines()]
        result = [r for r in result if r is not None]
        if not result:
            return [], "Broker list file is empty or in an unrecognized format."
        return result, ""
    except Exception as e:
        return [], f"Failed to fetch broker list: {e}"


def fetch_broker_list_bg():
    """Fetch daftar broker di background thread.

    Return: queue.Queue — isi satu item ("ok", list) atau ("err", msg).
    Caller wajib poll queue dari main thread (mis. via root.after).
    Tidak ada callback yang dipanggil dari background thread
    sehingga aman untuk Tkinter yang tidak thread-safe.
    """
    import queue as _q
    q = _q.Queue()
    def _run():
        result, err = fetch_broker_list()
        q.put(("ok", result) if result else ("err", err))
    threading.Thread(target=_run, daemon=True).start()
    return q



def wget_then_install_bg(url: str, dest_dir: Path, broker_name: str,
                         on_progress, on_success, on_error, on_timeout):
    """Unduh installer via wget, jalankan via wine, lalu hapus file .exe.

    Callbacks:
      on_progress(msg)           — update teks status
      on_success(exe_name, name) — installer dijalankan, exe sudah dihapus
      on_error(msg)              — gagal unduh atau jalankan
      on_timeout()               — wget timeout
    """
    def _run():
        try:
            # Snapshot file .exe yang sudah ada sebelum unduh
            existing = {f for f in dest_dir.iterdir() if f.suffix.lower() == ".exe"} \
                       if dest_dir.exists() else set()

            on_progress(f"Downloading {broker_name}\u2026")
            result = subprocess.run(
                ["wget", "-P", str(dest_dir), "--content-disposition", url],
                capture_output=True, text=True, timeout=300,
            )
            if result.returncode != 0:
                err_lines = result.stderr.strip().splitlines()
                err = err_lines[-1] if err_lines else f"exit {result.returncode}"
                on_error(f"Download failed: {err[:80]}")
                return

            # Temukan file .exe baru (yang belum ada sebelumnya)
            after = {f for f in dest_dir.iterdir() if f.suffix.lower() == ".exe"}
            new_files = after - existing
            exe = max(new_files, key=lambda f: f.stat().st_mtime) if new_files else None
            if exe is None:
                all_exe = sorted(after, key=lambda f: f.stat().st_mtime, reverse=True)
                exe = all_exe[0] if all_exe else None
            if exe is None:
                on_error("File .exe not found after download.")
                return

            on_progress(f"Running installer {exe.name}\u2026")
            exe_name = exe.name
            exe_path = exe   # simpan referensi sebelum thread lain
            try:
                proc = subprocess.Popen(
                    ["wine", str(exe_path)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
            except FileNotFoundError:
                on_error("wine not found. Install: sudo apt install wine")
                return
            except Exception as e:
                on_error(f"Failed to run installer: {e}")
                return

            # Hapus .exe SETELAH proses Wine selesai (di thread daemon terpisah)
            def _wait_and_delete():
                try:
                    proc.wait()          # tunggu installer MT benar-benar selesai
                    time.sleep(2)        # jeda kecil agar file tidak terkunci
                    exe_path.unlink(missing_ok=True)
                except Exception:
                    pass

            threading.Thread(target=_wait_and_delete, daemon=True).start()
            on_success(exe_name, broker_name)

        except subprocess.TimeoutExpired:
            on_timeout()
        except Exception as e:
            on_error(str(e))

    threading.Thread(target=_run, daemon=True).start()


# ── Uninstall MT helpers ──────────────────────────────────────────────────────
def run_uninstall_bg(uninstall_exe: Path, t: dict,
                     on_done, on_wine_missing, on_error):
    """Jalankan uninstall.exe via wine di background."""
    def _do():
        try:
            proc = subprocess.Popen(
                ["wine", str(uninstall_exe)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            proc.wait()
            on_done(proc.returncode, t)
        except FileNotFoundError:
            on_wine_missing()
        except Exception as e:
            on_error(str(e))
    threading.Thread(target=_do, daemon=True).start()
