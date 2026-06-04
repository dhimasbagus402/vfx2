"""
mt_backend.py — Logika non-UI MetaTrader Manager.

Semua fungsi di sini TIDAK mengimport tkinter.
Di-import oleh mt_ui.py yang memakai semua fungsi ini.
"""

import re
import json
import shutil
import subprocess
import datetime
from pathlib import Path

__version__ = "1.3"

# ── Config file (persist settings antar sesi) ─────────────────────────────────
CONFIG_PATH = Path.home() / ".config" / "mt_manager" / "settings.json"

def _load_config() -> dict:
    try:
        if CONFIG_PATH.exists():
            return json.loads(CONFIG_PATH.read_text())
    except Exception:
        pass
    return {}

def _save_config(data: dict):
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps(data, indent=2))
    except Exception:
        pass

# ── Paths & constants ─────────────────────────────────────────────────────────
ALLOWED_ROOT  = Path.home()
DOCS_DIR      = Path.home() / "Documents"
AUTOSTART_DIR = Path.home() / ".config" / "autostart"

EXTRACT_EXTS = {".zip", ".rar", ".tar", ".gz", ".bz2", ".xz", ".7z",
                ".tar.gz", ".tar.bz2", ".tar.xz"}


# ── File utilities ─────────────────────────────────────────────────────────────
def extract_file(filepath: Path, dest_dir: Path) -> tuple[bool, str]:
    if not shutil.which("xarchiver"):
        return False, "xarchiver tidak terinstall. Jalankan: sudo apt install xarchiver"
    try:
        subprocess.Popen(["xarchiver", "--extract-to", str(dest_dir), str(filepath)])
        return True, "xarchiver dibuka."
    except Exception as e:
        return False, str(e)


def is_archive(path: Path) -> bool:
    n = path.name.lower()
    return any(n.endswith(ext) for ext in EXTRACT_EXTS)


# ── Installer detection & silent install ──────────────────────────────────────
def _detect_installer_type(exe_path: Path) -> str:
    """Baca byte header .exe untuk deteksi Inno Setup vs NSIS vs unknown."""
    try:
        data = exe_path.read_bytes()
        if b"Inno Setup" in data[:65536]:
            return "inno"
        if b"Nullsoft" in data[:65536] or b"NSIS" in data[:65536]:
            return "nsis"
    except Exception:
        pass
    return "unknown"


def _try_silent_install(installer_path: Path, inst_type: str,
                        win_path: str, group_value: str,
                        log_fn=None) -> "subprocess.Popen | None":
    """
    Coba jalankan installer dalam mode silent.
    Return Popen object jika berhasil diluncurkan, None jika tidak support.

    Inno Setup : /VERYSILENT /SUPPRESSMSGBOXES /NORESTART
                 /DIR="C:\\path" /GROUP="nama group"
    NSIS        : /S /D=C:\\path  /GROUP=nama group

    Catatan: /VERYSILENT lebih kuat dari /SILENT —
      /SILENT    masih tampilkan progress window
      /VERYSILENT benar-benar tanpa UI sama sekali
    """
    try:
        if inst_type == "inno":
            cmd = [
                "wine", str(installer_path),
                "/VERYSILENT",
                "/SUPPRESSMSGBOXES",
                "/NORESTART",
                f"/DIR={win_path}",
                f"/GROUP={group_value}",
            ]
        elif inst_type == "nsis":
            cmd = [
                "wine", str(installer_path),
                "/S",
                f"/D={win_path}",
                f"/GROUP={group_value}",
            ]
        else:
            return None   # unknown → tidak coba silent

        if log_fn:
            log_fn(f"Silent cmd: {' '.join(cmd)}")

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        return proc
    except FileNotFoundError:
        raise
    except Exception as e:
        if log_fn:
            log_fn(f"Silent launch error: {e}")
        return None


def _silent_succeeded(proc: "subprocess.Popen", install_dir_win: str,
                      timeout: int = 120) -> bool:
    """
    Tunggu proc selesai (maks timeout detik) lalu verifikasi
    apakah folder tujuan benar-benar terbuat di Wine filesystem.

    Return True  → silent install sukses
    Return False → gagal / folder tidak ditemukan
    """
    import time
    deadline = time.time() + timeout
    while proc.poll() is None:
        if time.time() > deadline:
            try:
                proc.kill()
            except Exception:
                pass
            return False
        time.sleep(0.5)

    # Konversi Windows path → Linux path
    # "C:\\Program Files (x86)\\MT4 Broker 1"
    #   → ~/.wine/drive_c/Program Files (x86)/MT4 Broker 1
    try:
        wp = install_dir_win.replace("\\", "/").strip()
        if len(wp) >= 3 and wp[1] == ":":
            wp = wp[3:]
        linux_path = Path.home() / ".wine/drive_c" / wp.lstrip("/")
        return linux_path.exists()
    except Exception:
        return proc.returncode == 0


# ── Scan terminals (pure I/O, tanpa tkinter) ──────────────────────────────────
def _parse_origin(folder: Path, _wine_c: Path, _games_c: Path):
    """Baca origin.txt → (name, install_path)."""
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
                raw = dec; break
        except (UnicodeDecodeError, ValueError):
            continue
    if not raw:
        raw = raw_bytes.decode("utf-16", errors="ignore").replace("\x00", "").strip()
    if not raw:
        return folder.name[:22], None
    line = raw.splitlines()[0].strip()
    name = (line.replace("\\", "/").rstrip("/").split("/")[-1].strip()
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
                    install = c; break
    except Exception:
        pass
    return name, install


def scan_worker() -> list[dict]:
    """
    Semua I/O scan terminal — tidak menyentuh tkinter.
    Return list of terminal dicts, sudah di-sort.
    """
    home     = Path.home()
    _wine_c  = home / ".wine/drive_c"
    _games_c = home / "Games/drive_c"
    found    = []

    # ── MT5 ──
    for base in (_wine_c / "Program Files",
                 _wine_c / "Program Files (x86)"):
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

    # ── MT4 ──
    users_dir = _wine_c / "users"
    if users_dir.exists():
        for userdir in users_dir.iterdir():
            tb = userdir / "AppData/Roaming/MetaQuotes/Terminal"
            if not tb.exists():
                continue
            for folder in tb.iterdir():
                mql4 = folder / "MQL4"
                if mql4.exists():
                    _n4, _ip4 = _parse_origin(folder, _wine_c, _games_c)
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

    # Natural sort
    def _nat_key(item):
        parts = re.split(r"(\d+)", item["name"].lower())
        return [int(p) if p.isdigit() else p for p in parts]
    found.sort(key=lambda x: (0 if x["type"] == "MT4" else 1, _nat_key(x)))
    return found


# ── Autostart helpers (path only, tanpa tkinter) ──────────────────────────────
def _autostart_desktop_path(t: dict) -> Path:
    safe = t["name"].replace(" ", "_").replace("/", "_")
    return AUTOSTART_DIR / f"{safe}.desktop"


def _autostart_is_on(t: dict) -> bool:
    return _autostart_desktop_path(t).exists()


def _autostart_icon_path(t: dict):
    """Cari file icon Terminal.ico (MT5) atau terminal.ico (MT4) dari folder instalasi."""
    if t["type"] == "MT5":
        ico = Path(t["path"]) / "Terminal.ico"
        return ico if ico.exists() else None
    else:
        ip = t.get("install_path")
        if ip:
            ico = Path(ip) / "terminal.ico"
            if ico.exists():
                return ico
        ico = Path(t["path"]) / "terminal.ico"
        return ico if ico.exists() else None


# ── Find exe helper ────────────────────────────────────────────────────────────
def _find_exe(t: dict, mt4_name: str, mt5_name: str):
    """Cari file exe untuk terminal t. MT4 pakai install_path, MT5 pakai path langsung."""
    tp = Path(t["path"])
    if t["type"] == "MT5":
        c = tp / mt5_name
        return c if c.exists() else None
    # MT4
    ip = t.get("install_path")
    if ip:
        c = Path(ip) / mt4_name
        if c.exists():
            return c
    c = tp / mt4_name   # fallback AppData
    return c if c.exists() else None


# ── File listing (I/O tanpa tkinter) ──────────────────────────────────────────
def list_terminal_files(t: dict) -> list[dict]:
    """
    Return list of dicts:
      {iid, category, name, ext, size_str, modified_str, path}
    untuk semua EA / Indicator / Script / Log di terminal t.
    Dipakai oleh _reload_files() di UI untuk mengisi tabel tanpa I/O di main thread.
    """
    rows = []
    row  = 0
    _fmt = datetime.datetime.fromtimestamp
    for key, label in (("experts", "Expert"), ("indicators", "Indicator"),
                       ("scripts", "Script"), ("logs", "Log")):
        folder = t.get(key)
        if not (folder and folder.exists()):
            continue
        try:
            entries = sorted(
                (e for e in folder.iterdir() if e.is_file()),
                key=lambda e: e.name,
            )
        except OSError:
            continue
        for f in entries:
            try:
                st = f.stat()
            except OSError:
                continue
            kb = st.st_size / 1024
            sz = f"{kb:.1f} KB" if kb < 1024 else f"{kb/1024:.2f} MB"
            rows.append({
                "iid":          f"r{row}",
                "category":     label,
                "name":         f.name,
                "ext":          f.suffix.lower(),
                "size_str":     sz,
                "modified_str": _fmt(st.st_mtime).strftime("%Y-%m-%d"),
                "path":         f,
            })
            row += 1
    return rows
