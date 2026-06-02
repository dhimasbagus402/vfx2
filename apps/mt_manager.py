import re
import json
import shutil
import subprocess
import threading
import datetime
from pathlib import Path
import tkinter as tk
import tkinter.font as tkf
from tkinter import ttk, messagebox
__version__ = "1.2"

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

# ── Design Tokens — sesuai HTML metatrader_manager_ui.html ────────────────────
BG          = "#0d1114"   # --bg
BG2         = "#0d1114"   # --bg2  (sidebar, titlebar, topbar)
BG3         = "#171f26"   # --bg3  (card / hover)
BG4         = "#0d171f"   # --bg4  (card2 / stripe)
ACCENT      = "#26b0ff"
ACCENT1     = "#ffffff"
ACCENT4     = "#97e0f7"
ACCENT3     = "#00c896"   # --accent  (teal-green)
ACCENT2     = "#ffffff"   # --accent2 (blue)
ACCENT_DIM  = "#033154"   # --accent-dim
BORDER      = "#1c2438"   # --border  (rgba white 7%)
BORDER2     = "#263045"   # --border2 (rgba white 12%)
DANGER      = "#ff5b5b"   # --danger
WARN        = "#f0a030"   # --warn
FG          = "#e8edf5"   # --text
FG2         = "#8a95a8"   # --text2
FG3         = "#8590a6"   # --text3
WHITE       = "#ffffff"
PURPLE      = "#a78bfa"

# (legacy colour aliases removed)

ALLOWED_ROOT = Path.home()
DOCS_DIR     = Path.home() / "Documents"

# ── Table Text Config ─────────────────────────────────────────────────────────
TABLE_FONT_SIZE    = 10        # ukuran font isi tabel
TABLE_HEADING_SIZE = 9         # ukuran font heading kolom
# Kolom-kolom tabel: (id, heading, lebar_px, anchor, stretch)
# Catatan: kolom "cat" dirender di cat_tree terpisah agar bisa beda warna per-baris
TABLE_COLUMNS = [
    ("name",     "NAME",     0,   "w",      True),
    ("type",     "TYPE",     70,  "center", False),
    ("size",     "SIZE",     80,  "e",      False),
    ("modified", "MODIFIED", 100, "w",      False),
]

# ── Category Column Config ─────────────────────────────────────────────────────
CAT_COL_WIDTH  = 100           # lebar kolom CATEGORY (px)
CAT_COLORS = {
    "Expert":    "#00c896",    # hijau
    "Indicator": "#f0a030",    # kuning
    "Script":    "#a78bfa",    # ungu
    "Log":       "#e8edf5",    # putih
}

# ── Autostart Toggle Config ───────────────────────────────────────────────────
AUTOSTART_DIR    = Path.home() / ".config" / "autostart"
# Slider dimensions
AS_COL_WIDTH     = 48              # lebar kolom canvas slider (px)
AS_TRACK_W       = 34              # lebar pill track
AS_TRACK_H       = 18              # tinggi pill track
AS_THUMB_R       = 7               # radius thumb circle
AS_COLOR_ON      = "#00c896"       # warna track saat ON
AS_COLOR_OFF     = "#2a3545"       # warna track saat OFF
AS_THUMB_COL     = "#ffffff"       # warna thumb
AS_TRACK_OFF_BDR = "#3a4a5f"       # border track saat OFF

# ── Checkbox Config ────────────────────────────────────────────────────────────
# Checkbox memakai Treeview TERPISAH (split-treeview) agar ukurannya
# 100% independen dari font teks kolom data di sebelah kanan.
CHK_COL_WIDTH = 36             # lebar kolom checkbox (px)
CHK_FONT_SIZE = 14             # ukuran karakter ☐/☑ — bebas, tidak pengaruhi teks tabel
CHK_CHAR_OFF  = "\u25a1"            # karakter checkbox kosong
CHK_CHAR_ON   = "\u25a0"            # karakter checkbox terisi

# Row height: 0 = auto (pakai nilai terbesar antara TABLE_FONT_SIZE & CHK_FONT_SIZE + padding)
# Kedua Treeview pakai row height yang sama agar baris tetap sejajar.
TABLE_ROW_HEIGHT   = 0         # 0 = auto; atau set manual mis. 32

EXTRACT_EXTS = {".zip", ".rar", ".tar", ".gz", ".bz2", ".xz", ".7z",
                ".tar.gz", ".tar.bz2", ".tar.xz"}

# Font: JetBrains Mono dengan fallback DejaVu Sans Mono
FONT        = "San Francisco"
FONT_MONO   = "San Francisco"
SIDEBAR_W   = 250


# ── Font resolver + shared tkf.Font cache ─────────────────────────────────────
_FONT_CACHE: dict = {}       # family name cache
_FONT_OBJ_CACHE: dict = {}   # tkf.Font object cache keyed (family, size, weight)

def resolve_font(preferred, fallback="DejaVu Sans Mono"):
    if preferred in _FONT_CACHE:
        return _FONT_CACHE[preferred]
    try:
        fams = tkf.families()
        result = preferred if preferred in fams else fallback
    except Exception:
        result = fallback
    _FONT_CACHE[preferred] = result
    return result

def get_font_obj(family, size, weight="normal"):
    """Return cached tkf.Font — satu object per (family, size, weight)."""
    key = (family, size, weight)
    if key not in _FONT_OBJ_CACHE:
        _FONT_OBJ_CACHE[key] = tkf.Font(family=family, size=size, weight=weight)
    return _FONT_OBJ_CACHE[key]


# ── Rounded Canvas Container ───────────────────────────────────────────────────
class RoundedBox(tk.Canvas):
    def __init__(self, parent, radius=8, bg=BG3,
                 border_color=BORDER2, border_w=1, **kw):
        outer = parent.cget("bg") if hasattr(parent, "cget") else BG
        super().__init__(parent, bg=outer, highlightthickness=0, **kw)
        self._r, self._bg, self._bc, self._bw = radius, bg, border_color, border_w
        self.inner = tk.Frame(self, bg=bg)
        self.bind("<Configure>", self._redraw)

    def _redraw(self, _=None):
        # Debounce: batalkan jadwal sebelumnya, jadwal ulang 8ms kemudian
        if hasattr(self, "_redraw_id") and self._redraw_id:
            self.after_cancel(self._redraw_id)
        self._redraw_id = self.after(8, self._do_redraw)

    def _do_redraw(self):
        self._redraw_id = None
        self.delete("rr")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 4 or h < 4:
            return
        r, bw = self._r, self._bw
        if bw:
            self._rr(0, 0, w-1, h-1, r, fill=self._bc)
        self._rr(bw, bw, w-bw-1, h-bw-1, max(1, r-bw), fill=self._bg)
        pad = bw + 1
        self.inner.place(x=pad, y=pad, width=w-pad*2, height=h-pad*2)

    def _rr(self, x1, y1, x2, y2, r, fill):
        pts = [x1+r,y1, x2-r,y1, x2,y1, x2,y1+r,
               x2,y2-r, x2,y2, x2-r,y2, x1+r,y2,
               x1,y2, x1,y2-r, x1,y1+r, x1,y1, x1+r,y1]
        self.create_polygon(pts, smooth=True, fill=fill, outline="", tags="rr")


# ── Custom Rounded Scrollbar ───────────────────────────────────────────────────
class RoundScrollbar(tk.Canvas):
    W         = 10
    ARROW_H   = 13
    THUMB_R   = 5
    TRACK_COL = BG
    THUMB_COL = BORDER2
    THUMB_HOV = "#3d5070"
    ARROW_COL = FG3
    ARROW_HOV = FG
    BTN_COL   = BG2
    BTN_HOV   = BG3

    def __init__(self, parent, command=None, **kw):
        kw.setdefault("width", self.W)
        outer = parent.cget("bg") if hasattr(parent, "cget") else BG
        super().__init__(parent, bg=outer, highlightthickness=0, cursor="arrow", **kw)
        self._cmd = command
        self._first = 0.0
        self._last  = 1.0
        self._drag  = None
        self._repeat_id = None
        self._hover_zone = None
        self.bind("<Configure>",       self._redraw)
        self.bind("<ButtonPress-1>",   self._on_press)
        self.bind("<B1-Motion>",       self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Motion>",          self._on_motion)
        self.bind("<Leave>",           self._on_leave)
        self.bind("<MouseWheel>",      self._on_wheel)
        self.bind("<Button-4>",        self._on_wheel)
        self.bind("<Button-5>",        self._on_wheel)

    def set(self, first, last):
        self._first = float(first)
        self._last  = float(last)
        self._redraw()

    def _track_y(self):
        return self.ARROW_H, self.winfo_height() - self.ARROW_H

    def _thumb_rect(self):
        t, b = self._track_y()
        span = b - t
        if span <= 0:
            return t, b
        y1 = t + self._first * span
        y2 = t + self._last  * span
        if y2 - y1 < 16:
            mid = (y1 + y2) / 2
            y1, y2 = mid - 8, mid + 8
        return y1, y2

    def _zone(self, y):
        h = self.winfo_height()
        if y < self.ARROW_H:          return "up"
        if y > h - self.ARROW_H:      return "down"
        ty1, ty2 = self._thumb_rect()
        if ty1 <= y <= ty2:           return "thumb"
        return "track"

    def _redraw(self, _=None):
        self.delete("all")
        w = self.W
        h = self.winfo_height()
        if h < self.ARROW_H * 2 + 4:
            return
        self.create_rectangle(0, self.ARROW_H, w, h - self.ARROW_H,
                               fill=self.TRACK_COL, outline="", tags="track_bg")
        ty1, ty2 = self._thumb_rect()
        tc = self.THUMB_HOV if self._hover_zone == "thumb" else self.THUMB_COL
        self._draw_rounded_rect(2, ty1+1, w-2, ty2-1, self.THUMB_R, tc)
        bu = self.BTN_HOV if self._hover_zone == "up" else self.BTN_COL
        self.create_rectangle(0, 0, w, self.ARROW_H, fill=bu, outline="", tags="btn_up")
        ac = self.ARROW_HOV if self._hover_zone == "up" else self.ARROW_COL
        self._draw_arrow(w//2, self.ARROW_H//2, "up", ac)
        bd = self.BTN_HOV if self._hover_zone == "down" else self.BTN_COL
        self.create_rectangle(0, h-self.ARROW_H, w, h, fill=bd, outline="", tags="btn_down")
        ac2 = self.ARROW_HOV if self._hover_zone == "down" else self.ARROW_COL
        self._draw_arrow(w//2, h - self.ARROW_H//2, "down", ac2)

    def _update_hover(self):
        """Lightweight update: hanya ubah warna hover tanpa full redraw."""
        w = self.W
        h = self.winfo_height()
        if h < self.ARROW_H * 2 + 4:
            return
        # thumb
        tc = self.THUMB_HOV if self._hover_zone == "thumb" else self.THUMB_COL
        self.itemconfig("thumb_shape", fill=tc)
        # btn up
        bu = self.BTN_HOV if self._hover_zone == "up" else self.BTN_COL
        self.itemconfig("btn_up", fill=bu)
        ac = self.ARROW_HOV if self._hover_zone == "up" else self.ARROW_COL
        self.itemconfig("arrow_up", fill=ac)
        # btn down
        bd = self.BTN_HOV if self._hover_zone == "down" else self.BTN_COL
        self.itemconfig("btn_down", fill=bd)
        ac2 = self.ARROW_HOV if self._hover_zone == "down" else self.ARROW_COL
        self.itemconfig("arrow_down", fill=ac2)

    def _draw_rounded_rect(self, x1, y1, x2, y2, r, color):
        r = min(r, (x2-x1)//2, max(1,(y2-y1)//2))
        pts = [x1+r,y1, x2-r,y1, x2,y1, x2,y1+r,
               x2,y2-r, x2,y2, x2-r,y2, x1+r,y2,
               x1,y2, x1,y2-r, x1,y1+r, x1,y1, x1+r,y1]
        self.create_polygon(pts, smooth=True, fill=color, outline="", tags="thumb_shape")

    def _draw_arrow(self, cx, cy, direction, color):
        s = 3
        if direction == "up":
            pts = [cx, cy-s, cx+s, cy+s, cx-s, cy+s]
            tag = "arrow_up"
        else:
            pts = [cx, cy+s, cx+s, cy-s, cx-s, cy-s]
            tag = "arrow_down"
        self.create_polygon(pts, fill=color, outline="", tags=tag)

    def _on_motion(self, e):
        zone = self._zone(e.y)
        if zone != self._hover_zone:
            self._hover_zone = zone
            # gunakan _update_hover (ringan) bila item sudah ada, else full redraw
            if self.find_withtag("thumb_shape"):
                self._update_hover()
            else:
                self._redraw()

    def _on_leave(self, _=None):
        if self._hover_zone is not None:
            self._hover_zone = None
            if self.find_withtag("thumb_shape"):
                self._update_hover()
            else:
                self._redraw()

    def _on_press(self, e):
        zone = self._zone(e.y)
        if zone == "thumb":
            ty1, _ = self._thumb_rect()
            self._drag = e.y - ty1
        elif zone == "up":
            self._scroll_step("scroll", -1, "units")
            self._start_repeat("scroll", -1, "units")
        elif zone == "down":
            self._scroll_step("scroll", 1, "units")
            self._start_repeat("scroll", 1, "units")
        elif zone == "track":
            t, b = self._track_y()
            span = b - t
            if span > 0:
                frac = (e.y - t) / span
                self._scroll_step("moveto", frac)

    def _on_drag(self, e):
        if self._drag is None:
            return
        t, b = self._track_y()
        span = b - t
        ty1, ty2 = self._thumb_rect()
        thumb_h = ty2 - ty1
        if span - thumb_h <= 0:
            return
        new_y1 = e.y - self._drag
        frac = (new_y1 - t) / (span - thumb_h)
        frac = max(0.0, min(1.0, frac))
        self._scroll_step("moveto", frac)

    def _on_release(self, _=None):
        self._drag = None
        self._cancel_repeat()

    def _on_wheel(self, e):
        if e.num == 4 or e.delta > 0:
            self._scroll_step("scroll", -3, "units")
        else:
            self._scroll_step("scroll",  3, "units")

    def _scroll_step(self, *args):
        if self._cmd:
            self._cmd(*args)

    def _start_repeat(self, *args):
        self._cancel_repeat()
        def _repeat():
            self._scroll_step(*args)
            self._repeat_id = self.after(80, _repeat)
        self._repeat_id = self.after(400, _repeat)

    def _cancel_repeat(self):
        if self._repeat_id:
            self.after_cancel(self._repeat_id)
            self._repeat_id = None


# ── Tooltip ────────────────────────────────────────────────────────────────────
class Tooltip:
    """Tooltip ringan: satu Toplevel di-reuse (withdraw/deiconify) bukan destroy/recreate."""
    def __init__(self, widget, text, delay=280, position="below"):
        self.widget   = widget
        self.text     = text
        self.delay    = delay
        self._id      = None
        self._win     = None   # dibuat sekali, lalu disembunyikan
        self._lbl     = None
        self._cx      = 0
        self._cy      = 0
        widget.bind("<Enter>",  self._schedule)
        widget.bind("<Motion>", self._on_motion)
        widget.bind("<Leave>",  self._cancel)
        widget.bind("<Button>", self._cancel)

    def _on_motion(self, e):
        self._cx = e.x_root
        self._cy = e.y_root

    def _schedule(self, e=None):
        self._cancel()
        if e:
            self._cx = e.x_root
            self._cy = e.y_root
        self._id = self.widget.after(self.delay, self._show)

    def _cancel(self, _=None):
        if self._id:
            self.widget.after_cancel(self._id)
            self._id = None
        if self._win:
            self._win.withdraw()

    def _build(self):
        """Buat Toplevel sekali — selanjutnya cukup update teks + posisi."""
        tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.configure(bg=BORDER2)
        tw.attributes("-topmost", True)
        tw.withdraw()
        outer = tk.Frame(tw, bg=BORDER2, padx=1, pady=1)
        outer.pack()
        inner = tk.Frame(outer, bg=BG3, padx=12, pady=7)
        inner.pack()
        _f = resolve_font(FONT)
        lbl = tk.Label(inner, text=self.text, bg=BG3, fg=FG2,
                       font=(_f, 9), justify="left", wraplength=380)
        lbl.pack()
        self._win = tw
        self._lbl = lbl

    def _show(self):
        if self._win is None:
            self._build()
        # Update teks jika berubah (untuk tooltip dinamis)
        if self._lbl["text"] != self.text:
            self._lbl.config(text=self.text)
        tw = self._win
        tw.deiconify()
        tw.update_idletasks()
        tw_ = tw.winfo_reqwidth()
        th_ = tw.winfo_reqheight()
        x = self._cx + 14
        y = self._cy + 18
        sw = tw.winfo_screenwidth()
        sh = tw.winfo_screenheight()
        if x + tw_ > sw: x = self._cx - tw_ - 6
        if y + th_ > sh: y = self._cy - th_ - 6
        tw.wm_geometry(f"+{x}+{y}")


# ── Themed message popup (menggantikan messagebox default tkinter) ────────────
def _themed_popup(root_or_widget, kind: str, title: str, msg: str,
                  btn_text: str = "OK", extra_btn=None):
    """
    Tampilkan popup bertema dark sesuai desain aplikasi.

    kind  : "error"   → ikon ✕ merah (DANGER)
            "warning" → ikon ⚠ kuning (WARN)
            "info"    → ikon ℹ biru   (ACCENT)
            "success" → ikon ✓ hijau
    extra_btn : None | ("Label", callback) — tombol kedua di kiri OK
    """
    ICON_MAP = {
        "error":   ("\u2715", DANGER),
        "warning": ("\u26a0", WARN),
        "info":    ("\u2139", ACCENT),
        "success": ("\u2713", "#5ecf3e"),
    }
    icon_char, icon_color = ICON_MAP.get(kind, ("\u2139", ACCENT))

    # Cari root Tk
    try:
        root = root_or_widget.winfo_toplevel()
    except Exception:
        root = root_or_widget

    _f  = resolve_font(FONT)
    _fm = resolve_font(FONT_MONO)

    win = tk.Toplevel(root)
    win.title(title)
    win.configure(bg=BG)
    win.resizable(False, False)
    win.attributes("-topmost", True)

    # Header
    hdr = tk.Frame(win, bg=BG2, height=48)
    hdr.pack(fill="x")
    hdr.pack_propagate(False)
    hdr_inner = tk.Frame(hdr, bg=BG2, padx=20)
    hdr_inner.pack(fill="both", expand=True)
    tk.Label(hdr_inner, text=f"{icon_char}  {title}",
             bg=BG2, fg=icon_color, font=(_f, 12, "bold")).pack(side="left", fill="y")
    tk.Frame(win, bg=BORDER, height=1).pack(fill="x")

    # Body
    body = tk.Frame(win, bg=BG, padx=24, pady=18)
    body.pack(fill="both", expand=True)
    big_icon = tk.Label(body, text=icon_char, bg=BG, fg=icon_color, font=(_f, 22))
    big_icon.grid(row=0, column=0, padx=(0, 16), sticky="n", pady=(2, 0))
    tk.Label(body, text=msg, bg=BG, fg=FG2,
             font=(_f, 10), justify="left", anchor="w",
             wraplength=380).grid(row=0, column=1, sticky="w")
    body.columnconfigure(1, weight=1)

    # Footer
    tk.Frame(win, bg=BORDER, height=1).pack(fill="x")
    foot = tk.Frame(win, bg=BG2, height=44)
    foot.pack(fill="x")
    foot.pack_propagate(False)
    fi = tk.Frame(foot, bg=BG2, padx=12)
    fi.pack(fill="both", expand=True)

    oh, _ = make_pill_btn(fi, btn_text, win.destroy,
                          bg=BG3, fg=FG, hover_bg=BG4,
                          font_size=9, padx=20, pady=6, radius=7)
    oh.pack(side="right", pady=8)

    if extra_btn:
        elabel, ecmd = extra_btn
        def _extra():
            win.destroy()
            ecmd()
        eh, _ = make_pill_btn(fi, elabel, _extra,
                              bg=ACCENT_DIM, fg=ACCENT, hover_bg="#1d2b36",
                              font_size=9, padx=20, pady=6, radius=7)
        eh.pack(side="right", pady=8, padx=(0, 6))

    win.update_idletasks()
    try:
        rx = root.winfo_x() + root.winfo_width()  // 2 - win.winfo_reqwidth()  // 2
        ry = root.winfo_y() + root.winfo_height() // 2 - win.winfo_reqheight() // 2
        win.geometry(f"+{rx}+{ry}")
    except Exception:
        pass
    win.deiconify()
    win.lift()
    win.focus_force()
    return win


# ── Helpers ────────────────────────────────────────────────────────────────────
def yad_pick_file(title="Pilih File", filetypes=None, start_dir=None,
                  root_widget=None):
    if not shutil.which("yad"):
        if root_widget:
            _themed_popup(root_widget, "error", "yad tidak ditemukan",
                "yad belum terinstall.\n\nJalankan:\n  sudo apt install yad")
        else:
            messagebox.showerror("yad tidak ditemukan",
                "yad belum terinstall.\n\nJalankan:\n  sudo apt install yad")
        return None
    start = str(start_dir) + "/" if start_dir else str(ALLOWED_ROOT) + "/"
    cmd = ["yad", "--file-selection", "--title", title,
           "--filename", start,
           "--width", "800", "--height", "520", "--center", "--on-top"]
    if filetypes:
        exts = " ".join(filetypes)
        cmd += ["--file-filter", f"MetaTrader Files ({exts})|{exts}"]
        cmd += ["--file-filter", "All Files (*)|*"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        path = result.stdout.strip()
        if not path:
            return None
        selected = Path(path)
        try:
            selected.resolve().relative_to(ALLOWED_ROOT.resolve())
        except ValueError:
            if root_widget:
                _themed_popup(root_widget, "error", "Akses Ditolak",
                    f"File harus berada di dalam:\n{ALLOWED_ROOT}\n\n"
                    f"File dipilih:\n{selected}")
            else:
                messagebox.showerror("Akses Ditolak",
                    f"File harus berada di dalam:\n{ALLOWED_ROOT}\n\nFile dipilih:\n{selected}")
            return None
        return str(selected) if selected.is_file() else None
    except Exception as e:
        if root_widget:
            _themed_popup(root_widget, "error", "Error", f"yad gagal:\n{e}")
        else:
            messagebox.showerror("Error", f"yad gagal:\n{e}")
        return None


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


# ── Canvas pill button (like HTML .btn) ────────────────────────────────────────
def make_pill_btn(parent, text, cmd, bg, fg, hover_bg,
                  font_size=10, padx=12, pady=6, radius=6, fill_x=False):
    """Renders a rounded pill button on a Canvas."""
    outer_bg = parent.cget("bg") if hasattr(parent, "cget") else BG
    holder   = tk.Frame(parent, bg=outer_bg)
    if fill_x:
        holder.pack(fill="x")
    canvas = tk.Canvas(holder, bg=outer_bg, highlightthickness=0, cursor="hand2")
    canvas.pack(fill="x" if fill_x else "none", expand=fill_x)
    _state = {"bg": bg}
    _f   = resolve_font(FONT)
    _fnt = get_font_obj(_f, font_size, "bold")   # cached — tidak buat object baru
    _ftuple = (_f, font_size, "bold")

    def _draw(b=None):
        bcolor = b or _state["bg"]
        canvas.delete("all")
        w = canvas.winfo_width()
        h = canvas.winfo_height()
        if w < 2 or h < 2:
            return
        r = radius
        pts = [r,0, w-r,0, w,0, w,r, w,h-r, w,h, w-r,h, r,h,
               0,h, 0,h-r, 0,r, 0,0, r,0]
        canvas.create_polygon(pts, smooth=True, fill=bcolor, outline="")
        canvas.create_text(w//2, h//2, text=text, fill=fg, font=_ftuple)

    def _enter(_=None): _state["bg"] = hover_bg; _draw(hover_bg)
    def _leave(_=None): _state["bg"] = bg;       _draw(bg)
    def _click(_=None): cmd()

    canvas.bind("<Configure>", lambda e: _draw())
    canvas.bind("<Enter>",     _enter)
    canvas.bind("<Leave>",     _leave)
    canvas.bind("<Button-1>",  _click)

    rw = _fnt.measure(text) + padx * 2
    rh = _fnt.metrics("linespace") + pady * 2
    canvas.config(height=rh, width=rw if not fill_x else 1)
    return holder, canvas

# legacy alias
make_rounded_btn = make_pill_btn


# ── Badge canvas widget (MT4 / MT5) ───────────────────────────────────────────
class Badge(tk.Canvas):
    """Small pill badge — e.g. 'MT4' in blue, 'MT5' in teal."""
    def __init__(self, parent, text, bg_color, fg_color, radius=4, **kw):
        _f   = resolve_font(FONT)
        _fnt = get_font_obj(_f, 8, "bold")   # cached
        w = _fnt.measure(text) + 5 * 2 + 2
        h = _fnt.metrics("linespace") + 2 * 2
        outer = parent.cget("bg") if hasattr(parent, "cget") else BG2
        super().__init__(parent, width=w, height=h,
                         bg=outer, highlightthickness=0, **kw)
        r = radius
        pts = [r,0, w-r,0, w,0, w,r, w,h-r, w,h, w-r,h, r,h,
               0,h, 0,h-r, 0,r, 0,0, r,0]
        self.create_polygon(pts, smooth=True, fill=bg_color, outline="")
        self.create_text(w//2, h//2, text=text, fill=fg_color,
                         font=(_f, 8, "bold"))


# ── Progress bar canvas widget ────────────────────────────────────────────────
class ProgressBar(tk.Canvas):
    def __init__(self, parent, height=3, bg=BG4, fill=ACCENT, **kw):
        outer = parent.cget("bg") if hasattr(parent, "cget") else BG
        super().__init__(parent, height=height, bg=outer,
                         highlightthickness=0, **kw)
        self._fill  = fill
        self._track = bg
        self._pct   = 0.0
        self.bind("<Configure>", self._redraw)

    def set(self, pct):
        self._pct = max(0.0, min(1.0, pct))
        self._redraw()

    def _redraw(self, _=None):
        if hasattr(self, "_redraw_id") and self._redraw_id:
            self.after_cancel(self._redraw_id)
        self._redraw_id = self.after(16, self._do_redraw)

    def _do_redraw(self):
        self._redraw_id = None
        self.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        if w < 2:
            return
        self.create_rectangle(0, 0, w, h, fill=self._track, outline="")
        fw = int(w * self._pct)
        if fw > 0:
            self.create_rectangle(0, 0, fw, h, fill=self._fill, outline="")


# ── Main App ───────────────────────────────────────────────────────────────────
class MTManager:
    def __init__(self, root):
        self.root = root
        self.root.title("MetaTrader Manager")
        self.root.geometry("1180x700")
        self.root.configure(bg=BG)
        self.root.resizable(True, True)
        self.root.minsize(900, 520)
        self.root.after(0, lambda: self.root.attributes("-zoomed", True))
        self.terminals      = []
        self._font          = resolve_font(FONT)
        self._font_mono     = resolve_font(FONT_MONO)
        self._cfg           = _load_config()
        self._as_state_cache = {}    # cache Path.exists() per iid untuk slider canvas
        self._all_term_rows  = ()    # cache get_children() setelah scan
        self._build_styles()
        self._build_ui()
        self.scan_terminals(silent=True)   # startup: tanpa popup "Scan Selesai"
        # Auto-update: jalankan di background setelah UI siap
        if self.auto_update_var.get():
            self.root.after(800, self._auto_update_check)

    # ── Styles ─────────────────────────────────────────────────────────────────
    def _build_styles(self):
        s = ttk.Style()
        s.theme_use("clam")
        f = self._font

        # row height bersama: dipakai oleh KEDUA treeview agar baris sejajar
        # hitung dari font masing-masing secara independen, ambil yang terbesar
        _rh_data = TABLE_FONT_SIZE * 2 + 6
        _rh_chk  = CHK_FONT_SIZE  * 2 + 6
        _rh = TABLE_ROW_HEIGHT if TABLE_ROW_HEIGHT > 0 else max(_rh_data, _rh_chk)
        self._shared_row_height = _rh   # simpan agar bisa dipakai _build_ui

        # ── Treeview data (kolom NAME, TYPE, dst) ──
        s.configure("App.Treeview",
            background=BG3, foreground=FG, fieldbackground=BG3,
            rowheight=_rh, font=(f, TABLE_FONT_SIZE),
            borderwidth=0, relief="flat",
            highlightthickness=0, highlightbackground=BG3, highlightcolor=BG3)
        s.configure("App.Treeview.Heading",
            background=BG4, foreground=FG3,
            font=(f, TABLE_HEADING_SIZE), relief="flat", borderwidth=0, padding=(10, 6))
        s.map("App.Treeview",
            background=[("selected", ACCENT_DIM)],
            foreground=[("selected", ACCENT)])
        s.map("App.Treeview.Heading",
            background=[("active", BG4)], relief=[("active", "flat")])

        # ── Treeview checkbox (kolom ☐/☑ terpisah — font independen) ──
        s.configure("Chk.Treeview",
            background=BG3, foreground=FG, fieldbackground=BG3,
            rowheight=_rh, font=(f, CHK_FONT_SIZE),   # ← font checkbox independen
            borderwidth=0, relief="flat",
            highlightthickness=0, highlightbackground=BG3, highlightcolor=BG3)
        s.configure("Chk.Treeview.Heading",
            background=BG4, foreground=FG3,
            font=(f, TABLE_HEADING_SIZE), relief="flat", borderwidth=0, padding=(0, 6))
        s.map("Chk.Treeview",
            background=[("selected", ACCENT_DIM)],
            foreground=[("selected", ACCENT)])
        s.map("Chk.Treeview.Heading",
            background=[("active", BG4)], relief=[("active", "flat")])

        # ── Treeview category (kolom CATEGORY terpisah — warna per-baris independen) ──
        s.configure("Cat.Treeview",
            background=BG3, foreground=FG, fieldbackground=BG3,
            rowheight=_rh, font=(f, TABLE_FONT_SIZE),
            borderwidth=0, relief="flat",
            highlightthickness=0, highlightbackground=BG3, highlightcolor=BG3)
        s.configure("Cat.Treeview.Heading",
            background=BG4, foreground=FG3,
            font=(f, TABLE_HEADING_SIZE), relief="flat", borderwidth=0, padding=(10, 6))
        s.map("Cat.Treeview",
            background=[("selected", ACCENT_DIM)],
            foreground=[("selected", ACCENT)])
        s.map("Cat.Treeview.Heading",
            background=[("active", BG4)], relief=[("active", "flat")])

        # Side treeview (terminal list) — no headings shown
        s.configure("Side.Treeview",
            background=BG2, foreground=FG, fieldbackground=BG2,
            rowheight=44, font=(f, 10), borderwidth=0, relief="flat",
            highlightthickness=0, highlightbackground=BG2, highlightcolor=BG2)
        s.map("Side.Treeview",
            background=[("selected", BG3)],
            foreground=[("selected", ACCENT)])

        # Suppress default scrollbars
        s.layout("Vertical.TScrollbar", [])
        s.layout("Horizontal.TScrollbar", [])

        # Remove outer border/highlight from Treeview widgets
        s.layout("App.Treeview", [
            ("Treeview.treearea", {"sticky": "nswe"})
        ])
        s.layout("Chk.Treeview", [
            ("Treeview.treearea", {"sticky": "nswe"})
        ])
        s.layout("Cat.Treeview", [
            ("Treeview.treearea", {"sticky": "nswe"})
        ])
        s.layout("Side.Treeview", [
            ("Treeview.treearea", {"sticky": "nswe"})
        ])


    # ── UI ─────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        f  = self._font
        fm = self._font_mono

        # ════════════════════════════════════════════════════════════════
        # TITLEBAR  — macOS dots + "MetaTrader Manager — Linux Edition"
        # ════════════════════════════════════════════════════════════════
        titlebar = tk.Frame(self.root, bg=BG2, height=36)
        titlebar.pack(fill="x", side="top")
        titlebar.pack_propagate(False)
        tk.Frame(self.root, bg=BORDER, height=1).pack(fill="x", side="top")

        tb_inner = tk.Frame(titlebar, bg=BG2)
        tb_inner.pack(fill="both", expand=True, padx=14)

        # Traffic-light dots
        dots = tk.Frame(tb_inner, bg=BG2)
        dots.pack(side="left", fill="y")
        for col in ("#ff5f57", "#febc2e", "#28c840"):
            c = tk.Canvas(dots, width=11, height=11, bg=BG2,
                          highlightthickness=0)
            c.pack(side="left", padx=(0, 5), pady=0)
            c.create_oval(1, 1, 10, 10, fill=col, outline="")
        dots.pack(side="left", pady=12)

        # Title text
        title_frame = tk.Frame(tb_inner, bg=BG2)
        title_frame.pack(side="left", padx=10, fill="y")
        tk.Label(title_frame, text="MetaTrader", bg=BG2, fg=ACCENT,
                 font=(f, 11, "bold")).pack(side="left")
        tk.Label(title_frame, text=" Manager \u2014 Linux Edition",
         bg=BG2, fg=FG2, font=(f, 11)).pack(side="left")
        tk.Label(title_frame, text=f"  v{__version__}",
         bg=BG2, fg=FG3, font=(f, 9)).pack(side="left", pady=(2, 0))

        # ════════════════════════════════════════════════════════════════
        # BODY  — sidebar + main
        # ════════════════════════════════════════════════════════════════
        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True)

        # ── SIDEBAR ──────────────────────────────────────────────────────
        sidebar = tk.Frame(body, bg=BG2, width=SIDEBAR_W)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        tk.Frame(body, bg=BORDER, width=1).pack(side="left", fill="y")

        # Sidebar header
        tk.Label(sidebar, text="TERMINALS", bg=BG2, fg=FG3,
                 font=(f, 8), anchor="w", padx=14, pady=10).pack(fill="x")

        # Scan button
        scan_wrap = tk.Frame(sidebar, bg=BG2, padx=10)
        scan_wrap.pack(fill="x", pady=(0, 8))

        scan_c = tk.Canvas(scan_wrap, bg=BG2, highlightthickness=0,
                           height=30, cursor="hand2")
        scan_c.pack(fill="x")
        self._scan_canvas = scan_c
        scan_c.bind("<Configure>", self._draw_scan_btn)
        scan_c.bind("<Enter>",     lambda e: self._draw_scan_btn(hover=True))
        scan_c.bind("<Leave>",     lambda e: self._draw_scan_btn(hover=False))
        scan_c.bind("<Button-1>",  lambda e: self.scan_terminals())

        # Group labels + terminal treeview
        self._sidebar_frame = sidebar   # store for group label injection

        # Terminal list with custom scrollbar
        tlist_outer = tk.Frame(sidebar, bg=BG2, padx=8)
        tlist_outer.pack(fill="both", expand=True, pady=(0, 6))

        tlist_box = RoundedBox(tlist_outer, radius=7, bg=BG2,
                               border_color=BORDER2, border_w=1)
        tlist_box.pack(fill="both", expand=True)

        sb_side = RoundScrollbar(tlist_box.inner, command=self._term_yview)
        sb_side.pack(side="right", fill="y", padx=(0, 2), pady=3)
        self._sb_side_ref = sb_side   # referensi untuk _on_side_scroll

        # ── AutoStart slider canvas (kiri, menggantikan Treeview) ──
        self._as_canvas = tk.Canvas(
            tlist_box.inner,
            width=AS_COL_WIDTH, bg=BG2,
            highlightthickness=0, cursor="hand2",
        )
        self._as_canvas.pack(side="left", fill="y")
        self._as_canvas.bind("<Button-1>",  self._on_as_click)
        self._as_canvas.bind("<Motion>",    self._on_as_motion)
        self._as_canvas.bind("<Leave>",     self._on_as_leave)
        self._as_canvas.bind("<Configure>", lambda e: self._draw_as_canvas())
        # tooltip hover state
        self._as_hover_iid  = None
        self._as_tooltip_id = None
        self._as_tooltip_win = None

        # ── Terminal tree (kanan, konten utama) ──
        self.term_tree = ttk.Treeview(
            tlist_box.inner,
            columns=("badge", "name", "sub"),
            show="",          # no headings
            selectmode="browse",
            style="Side.Treeview",
            yscrollcommand=self._on_side_scroll,
        )
        self.term_tree.config(style="Side.Treeview")
        self.term_tree.column("badge", width=38, anchor="center", stretch=False)
        self.term_tree.column("name",  stretch=True, anchor="w")
        self.term_tree.column("sub",   width=80, anchor="w", stretch=False)
        self.term_tree.pack(side="left", fill="both", expand=True)
        self.term_tree.bind("<<TreeviewSelect>>", self._on_select)
        self.term_tree.bind("<MouseWheel>", lambda e: self._side_wheel(e))
        self.term_tree.bind("<Button-4>",   lambda e: self._side_wheel(e))
        self.term_tree.bind("<Button-5>",   lambda e: self._side_wheel(e))
        self._as_canvas.bind("<MouseWheel>",   lambda e: self._side_wheel(e))
        self._as_canvas.bind("<Button-4>",     lambda e: self._side_wheel(e))
        self._as_canvas.bind("<Button-5>",     lambda e: self._side_wheel(e))
        self.term_tree.tag_configure("MT4", foreground=WHITE)
        self.term_tree.tag_configure("MT5", foreground=WHITE)
        self.term_tree.tag_configure("group", foreground=FG3, font=(f, 8))

        # ── MAIN PANEL ───────────────────────────────────────────────────
        main = tk.Frame(body, bg=BG)
        main.pack(side="left", fill="both", expand=True)

        # ── TOOLBAR ──
        toolbar = tk.Frame(main, bg=BG2, height=46)
        toolbar.pack(fill="x")
        toolbar.pack_propagate(False)
        tk.Frame(main, bg=BORDER, height=1).pack(fill="x")

        tb = tk.Frame(toolbar, bg=BG2, padx=12)
        tb.pack(fill="both", expand=True)

        # Install EA / Indicator — primary green button
        h1, c1 = make_pill_btn(tb, "\u2191 Install EA / Indicator",
                               self._install_menu,
                               bg=ACCENT_DIM, fg=ACCENT, hover_bg="#1d2b36",
                               font_size=10, padx=12, pady=7, radius=10)
        h1.pack(side="left", pady=8, padx=(0, 4))
        self._install_btn_holder = h1
        self._install_btn_canvas = c1

        # Separator
        tk.Frame(tb, bg=BORDER2, width=1).pack(side="left", fill="y", padx=6, pady=8)

        # Browse
        h2, c2 = make_pill_btn(tb, "\u25a6 Browse", self.browse_files,
                               bg=BG3, fg=FG, hover_bg=BG4,
                               font_size=10, padx=12, pady=7, radius=10)
        h2.pack(side="left", pady=8, padx=2)
        Tooltip(c2, "Buka data Folder MT")

        # Clear Logs
        h3, c3 = make_pill_btn(tb, "\u2015 Clear Logs", self.clear_logs,
                               bg="#261a05", fg=WARN, hover_bg="#3d2a08",
                               font_size=10, padx=12, pady=7, radius=10)
        h3.pack(side="left", pady=8, padx=2)
        Tooltip(c3, "Hapus semua Logs pada MT")

        # Delete
        h4, c4 = make_pill_btn(tb, "\u232b Delete", self.uninstall_file,
                               bg="#2a0f0f", fg=DANGER, hover_bg="#3d1212",
                               font_size=10, padx=12, pady=7, radius=10)
        h4.pack(side="left", pady=8, padx=2)
        Tooltip(c4, "Hapus EA atau Indikator pada MT")

        # Separator
        tk.Frame(tb, bg=BORDER2, width=1).pack(side="left", fill="y", padx=6, pady=8)

        # Uninstall MT (jalankan Uninstall.exe MT)
        h5, c5 = make_pill_btn(tb, "\u26d4 Uninstall MT", self.uninstall_ea_exe,
                               bg="#2a1a00", fg="#e07b00", hover_bg="#3d2800",
                               font_size=10, padx=12, pady=7, radius=10)
        h5.pack(side="left", pady=8, padx=2)
        Tooltip(c5, "Jalankan Uninstall.exe pada folder instalasi MT")
        
        # Install / Duplikat MT dropdown
        h8, c8 = make_pill_btn(tb, "\u2b07 Install MT  \u25be", self._install_mt_menu,
                               bg="#0a1f0a", fg="#5ecf3e", hover_bg="#152e15",
                               font_size=10, padx=12, pady=7, radius=10)
        h8.pack(side="left", pady=8, padx=2)
        self._install_mt_btn_holder = h8
        Tooltip(c8, "Install MT baru atau Duplikat MT yang sudah ada")

        # Separator
        tk.Frame(tb, bg=BORDER2, width=1).pack(side="left", fill="y", padx=6, pady=8)

        # Open MT (jalankan terminal.exe / terminal64.exe)
        h6, c6 = make_pill_btn(tb, "\u25b6 Open MT", self.open_mt,
                               bg="#0d2200", fg="#5ecf3e", hover_bg="#1a3a00",
                               font_size=10, padx=12, pady=7, radius=10)
        h6.pack(side="left", pady=8, padx=2)
        Tooltip(c6, "Jalankan terminal MT yang dipilih")

        # Open MetaEditor
        h7, c7 = make_pill_btn(tb, "\u270e MetaEditor", self.open_metaeditor,
                               bg="#001a2a", fg="#3ab8e0", hover_bg="#002a3d",
                               font_size=10, padx=12, pady=7, radius=10)
        h7.pack(side="left", pady=8, padx=2)
        Tooltip(c7, "Buka MetaEditor untuk MT yang dipilih")


        # ── CONTENT AREA (no scroll canvas — table fills remaining space) ──
        content_main = tk.Frame(main, bg=BG)
        content_main.pack(fill="both", expand=True)
        # keep compat alias for _scroll_to_wget
        self._content_canvas = None

        # ── INFO BAR ──
        info_wrap = tk.Frame(content_main, bg=BG, padx=14, pady=8)
        info_wrap.pack(fill="x")

        info_border = tk.Frame(info_wrap, bg=BORDER2)
        info_border.pack(fill="x")
        info_card = tk.Frame(info_border, bg=BG2, padx=14, pady=8)
        info_card.pack(fill="x", padx=1, pady=1)

        self._info_fields = {}
        for key, label, default in [
            ("terminal", "TERMINAL", "—"),
            ("type",     "TYPE",     "—"),
            ("path",     "PATH",     "—"),
        ]:
            col = tk.Frame(info_card, bg=BG2)
            col.pack(side="left", padx=(0, 28))
            tk.Label(col, text=label, bg=BG2, fg=FG3,
                     font=(f, 8), anchor="w").pack(anchor="w")
            var = tk.StringVar(value=default)
            color = FG if key == "type" else (ACCENT if key == "path" else FG)
            lbl = tk.Label(col, textvariable=var, bg=BG2, fg=color,
                           font=(f, 10, "bold"), anchor="w")
            lbl.pack(anchor="w")
            self._info_fields[key] = (var, lbl)

        # ── SECTION: Expert Advisors & Indicators ──
        sec_wrap = tk.Frame(content_main, bg=BG, padx=14)
        sec_wrap.pack(fill="both", expand=True)

        sec_header = tk.Frame(sec_wrap, bg=BG)
        sec_header.pack(fill="x", pady=(0, 4))
        tk.Label(sec_header, text="EXPERT ADVISORS & INDICATORS",
                 bg=BG, fg=FG3, font=(f, 8)).pack(side="left")
        tk.Frame(sec_header, bg=BORDER, height=1).pack(
            side="left", fill="x", expand=True, padx=(10, 0), pady=4)

        # File table — rounded box with custom scrollbar
        tbl_box = RoundedBox(sec_wrap, radius=7, bg=BG3,
                             border_color=BORDER2, border_w=1)
        tbl_box.pack(fill="both", expand=True)

        sb_file = RoundScrollbar(tbl_box.inner, command=self._file_yview)
        sb_file.pack(side="right", fill="y", padx=(0, 2), pady=3)

        # checked-set: stores iids of checked rows
        self._checked = set()
        self._all_checked = False

        # ── Treeview CHECKBOX (kiri, font independen via Chk.Treeview style) ──
        self.chk_tree = ttk.Treeview(
            tbl_box.inner,
            columns=("chk",),
            show="headings",
            selectmode="browse",
            style="Chk.Treeview",
            yscrollcommand=self._on_chk_scroll,
        )
        # Paksa hilangkan border/highlight di level widget (bukan hanya style)
        self.chk_tree.configure(takefocus=False)
        try:
            self.chk_tree.tk.call("ttk::style", "configure", "Chk.Treeview",
                                  "-highlightthickness", 0, "-borderwidth", 0)
        except Exception:
            pass
        self.chk_tree.heading("chk", text=CHK_CHAR_OFF, anchor="center",
                              command=self._toggle_all)
        self.chk_tree.column("chk", width=CHK_COL_WIDTH, minwidth=CHK_COL_WIDTH,
                             anchor="center", stretch=False)
        self.chk_tree.pack(side="left", fill="y")

        # Sync scroll: klik di chk_tree juga gerak file_tree & sebaliknya
        self.chk_tree.tag_configure("row_even", background=BG3)
        self.chk_tree.tag_configure("row_odd",  background=BG4)
        self.chk_tree.tag_configure("checked",  background=ACCENT_DIM)

        # Tidak ada separator — biarkan chk_tree dan cat_tree langsung berdempet

        # ── Treeview CATEGORY (tengah, warna per-kategori via tag independen) ──
        self.cat_tree = ttk.Treeview(
            tbl_box.inner,
            columns=("cat",),
            show="headings",
            selectmode="browse",
            style="Cat.Treeview",
            yscrollcommand=self._on_cat_scroll,
        )
        self.cat_tree.heading("cat", text="CATEGORY", anchor="w")
        self.cat_tree.column("cat", width=CAT_COL_WIDTH, minwidth=CAT_COL_WIDTH,
                             anchor="w", stretch=False)
        self.cat_tree.pack(side="left", fill="y")

        # Tag warna per-kategori — hanya berlaku di cat_tree ini
        for label, color in CAT_COLORS.items():
            self.cat_tree.tag_configure(label, foreground=color)
        self.cat_tree.tag_configure("row_even", background=BG3)
        self.cat_tree.tag_configure("row_odd",  background=BG4)
        self.cat_tree.tag_configure("checked",  background=ACCENT_DIM)

        # ── Treeview DATA (kanan, kolom NAME TYPE SIZE MODIFIED) ──
        self.file_tree = ttk.Treeview(
            tbl_box.inner,
            columns=("name", "type", "size", "modified"),
            show="headings", selectmode="browse",
            style="App.Treeview",
            yscrollcommand=self._on_file_scroll,
        )

        for col, lbl, w, anc, stretch in TABLE_COLUMNS:
            self.file_tree.heading(col, text=lbl)
            self.file_tree.column(col, width=w, anchor=anc, stretch=stretch)
        self.file_tree.pack(side="left", fill="both", expand=True)
        self._sb_file = sb_file   # simpan referensi untuk yscrollcommand

        # Paksa hilangkan border chk_tree dan cat_tree setelah window di-render
        def _kill_borders():
            for tree in (self.chk_tree, self.cat_tree):
                try:
                    tree.tk.call(tree, "configure",
                                 "-highlightthickness", 0,
                                 "-highlightbackground", BG3,
                                 "-highlightcolor", BG3,
                                 "-borderwidth", 0,
                                 "-relief", "flat")
                except Exception:
                    pass
        self.root.after_idle(_kill_borders)

        # toggle checkbox on click on chk_tree
        self.chk_tree.bind("<ButtonRelease-1>", self._on_chk_click)
        # klik di cat_tree / file_tree sync selection saja
        self.cat_tree.bind("<ButtonRelease-1>",  self._on_file_click)
        self.file_tree.bind("<ButtonRelease-1>", self._on_file_click)

        # file_tree: warna teks netral untuk semua baris (warna kategori ada di cat_tree)
        self.file_tree.tag_configure("row_even", background=BG3)
        self.file_tree.tag_configure("row_odd",  background=BG4)
        self.file_tree.tag_configure("checked",  background=ACCENT_DIM)

        # ── WGET PANEL ──
        self._wget_anchor = tk.Frame(content_main, bg=BG, height=1)
        self._wget_anchor.pack(fill="x", side="bottom")

        wget_sec = tk.Frame(content_main, bg=BG, padx=14)
        wget_sec.pack(fill="x", side="bottom", pady=(8, 14))

        wget_sec_hdr = tk.Frame(wget_sec, bg=BG)
        wget_sec_hdr.pack(fill="x", pady=(0, 6))
        tk.Label(wget_sec_hdr, text="WGET DOWNLOADER",
                 bg=BG, fg=FG3, font=(f, 8)).pack(side="left")
        tk.Frame(wget_sec_hdr, bg=BORDER, height=1).pack(
            side="left", fill="x", expand=True, padx=(10, 0), pady=4)

        wget_border = tk.Frame(wget_sec, bg=BORDER2)
        wget_border.pack(fill="x")
        wget_card = tk.Frame(wget_border, bg=BG2, padx=14, pady=12)
        wget_card.pack(fill="x", padx=1, pady=1)

        # Row 1: entry + download button
        row1 = tk.Frame(wget_card, bg=BG2)
        row1.pack(fill="x")

        entry_frame = tk.Frame(row1, bg=BORDER2, highlightthickness=0,
                               padx=1, pady=1)
        entry_frame.pack(side="left", fill="x", expand=True, padx=(0, 10))

        self.wget_var = tk.StringVar()
        self.wget_entry = tk.Entry(
            entry_frame, textvariable=self.wget_var,
            bg=BG3, fg=FG, insertbackground=ACCENT2, relief="flat",
            font=(fm, 9), highlightthickness=0,
        )
        self.wget_entry.pack(fill="x", ipady=7, padx=1)

        PLACEHOLDER = 'wget --content-disposition "https://dropfile.id/xxxxxx"'

        def _focus_in(e):
            if self.wget_var.get() == PLACEHOLDER:
                self.wget_var.set("")
                self.wget_entry.config(fg=FG)

        def _focus_out(e):
            if not self.wget_var.get().strip():
                self.wget_var.set(PLACEHOLDER)
                self.wget_entry.config(fg=FG3)

        self._wget_placeholder = PLACEHOLDER
        self.wget_var.set(PLACEHOLDER)
        self.wget_entry.config(fg=FG3)
        self.wget_entry.bind("<FocusIn>",
            lambda e: (_focus_in(e), entry_frame.config(bg=ACCENT2)))
        self.wget_entry.bind("<FocusOut>",
            lambda e: (_focus_out(e), entry_frame.config(bg=BORDER2)))
        self.wget_entry.bind("<Return>", lambda _: self.wget_download())

        def _show_context_menu(e):
            popup = tk.Toplevel(self.wget_entry)
            popup.wm_overrideredirect(True)
            popup.attributes("-topmost", True)
            outer = tk.Frame(popup, bg=BORDER2, padx=1, pady=1)
            outer.pack()
            inner = tk.Frame(outer, bg=BG3)
            inner.pack()

            def _do_paste():
                popup.destroy()
                self.wget_entry.focus_set()
                _focus_in(None)
                self.wget_entry.event_generate("<<Paste>>")

            row = tk.Frame(inner, bg=BG3, cursor="hand2")
            row.pack(fill="x")
            lbl = tk.Label(row, text="⧉  Paste", bg=BG3, fg=FG,
                           font=(fm, 10), anchor="w", padx=12, pady=8)
            lbl.pack(fill="x")

            def _enter(_): row.config(bg=BG4); lbl.config(bg=BG4, fg=ACCENT)
            def _leave(_): row.config(bg=BG3); lbl.config(bg=BG3, fg=FG)
            for w in (row, lbl):
                w.bind("<Enter>",    _enter)
                w.bind("<Leave>",    _leave)
                w.bind("<Button-1>", lambda _: _do_paste())

            popup.update_idletasks()
            pw = popup.winfo_reqwidth()
            ph = popup.winfo_reqheight()
            sx, sy = e.x_root, e.y_root
            sw = popup.winfo_screenwidth()
            sh = popup.winfo_screenheight()
            if sx + pw > sw: sx = sw - pw - 4
            if sy + ph > sh: sy = sy - ph - 4
            popup.wm_geometry(f"+{sx}+{sy}")
            popup.bind("<FocusOut>", lambda _: popup.destroy())
            popup.focus_set()
        self.wget_entry.bind("<Button-3>", _show_context_menu)

        Tooltip(self.wget_entry,
                'Masukkan URL atau perintah wget dari dropfile.id',
                delay=200, position="above")

        dl_h, _ = make_pill_btn(row1, "\u2193 Download", self.wget_download,
                                 bg=ACCENT_DIM, fg=ACCENT, hover_bg="#1d2b36",
                                 font_size=10, padx=14, pady=7, radius=7)
        dl_h.pack(side="left")

        # Row 2: progress area
        row2 = tk.Frame(wget_card, bg=BG2)
        row2.pack(fill="x", pady=(8, 0))

        self.wget_status_var = tk.StringVar(value="")
        self._wget_lbl = tk.Label(row2, textvariable=self.wget_status_var,
                                   bg=BG2, fg=FG3, font=(f, 9), anchor="w")
        self._wget_lbl.pack(side="left")

        self._wget_pct_var = tk.StringVar(value="")
        tk.Label(row2, textvariable=self._wget_pct_var,
                 bg=BG2, fg=ACCENT, font=(f, 9)).pack(side="right")

        self._progress = ProgressBar(wget_card, height=2, bg=BG4, fill=ACCENT)
        self._progress.pack(fill="x", pady=(4, 0))

        # Row 3: auto-extract hint
        row3 = tk.Frame(wget_card, bg=BG2)
        row3.pack(fill="x", pady=(6, 0))

        self.auto_extract_var = tk.BooleanVar(value=True)
        cb = tk.Checkbutton(row3, text=" Auto-extract enabled \u2014 ZIP, RAR, 7Z, TAR didukung via xarchiver",
                            variable=self.auto_extract_var,
                            bg=BG2, fg=FG3, selectcolor=BG3,
                            activebackground=BG2, activeforeground=FG,
                            font=(f, 9), relief="flat", borderwidth=0,
                            highlightthickness=0, cursor="hand2")
        cb.pack(side="left")
        Tooltip(cb, "Ekstrak otomatis jika file berupa ZIP/RAR/7Z", position="above")

        # ── STATUS BAR ──
        tk.Frame(self.root, bg=BG, height=10).pack(fill="x", side="bottom")
        status_bar = tk.Frame(self.root, bg=BG2, height=28)
        status_bar.pack(fill="x", side="bottom")
        status_bar.pack_propagate(False)

        sb_inner = tk.Frame(status_bar, bg=BG2, padx=10)
        sb_inner.pack(fill="both", expand=True)

        self.status_var = tk.StringVar(value="Tekan Scan untuk mendeteksi terminal.")

        # Left dots + status items
        self._mk_status_item(sb_inner, "0 terminal",     ACCENT,  dot=True, varname="_term_count_var")

        # Right side — Auto-update checkbox + Update button
        # ── Auto-update checkbox ──
        self.auto_update_var = tk.BooleanVar(
            value=self._cfg.get("auto_update", True)
        )

        def _on_auto_update_toggle():
            self._cfg["auto_update"] = self.auto_update_var.get()
            _save_config(self._cfg)

        au_frame = tk.Frame(sb_inner, bg=BG2)
        au_frame.pack(side="right", padx=(0, 6), fill="y")

        au_cb = tk.Checkbutton(
            au_frame,
            text="Auto-update",
            variable=self.auto_update_var,
            command=_on_auto_update_toggle,
            bg=BG2, fg=FG3,
            selectcolor=BG3,
            activebackground=BG2, activeforeground=FG,
            font=(self._font, 8),
            relief="flat", borderwidth=0,
            highlightthickness=0, cursor="hand2",
        )
        au_cb.pack(side="left", fill="y")
        Tooltip(au_cb, "Cek update otomatis saat aplikasi dijalankan", position="above")

        update_c = tk.Canvas(sb_inner, bg=BG2, highlightthickness=0,
                             height=10, cursor="hand2")
        update_c.pack(side="right", padx=(0, 4))
        self._update_canvas = update_c

        def _draw_update_btn(hover=False):
            update_c.delete("all")
            w = update_c.winfo_width()
            h = update_c.winfo_height()
            if w < 4 or h < 4:
                return
            bg_c = "#1a3a2a" if hover else "#0f2a1e"
            fg_c = ACCENT3
            r = 5
            pts = [r,0, w-r,0, w,0, w,r, w,h-r, w,h, w-r,h, r,h,
                   0,h, 0,h-r, 0,r, 0,0, r,0]
            update_c.create_polygon(pts, smooth=True, fill=bg_c, outline="")
            _f = self._font
            update_c.create_text(w//2, h//2, text="\u21ba  Update",
                                 fill=fg_c, font=(_f, 10, "bold"))

        def _update_enter(_): _draw_update_btn(hover=True)
        def _update_leave(_): _draw_update_btn(hover=False)
        def _run_update(_=None):
            update_sh = Path.home() / "vfx2" / "update.sh"
            if not update_sh.exists():
                _themed_popup(self.root, "error", "Update Gagal",
                    f"Script tidak ditemukan:\n{update_sh}")
                return
            self._status("Menjalankan update...")
            self._show_update_popup(update_sh)

        update_c.bind("<Configure>", lambda e: _draw_update_btn())
        update_c.bind("<Enter>",     _update_enter)
        update_c.bind("<Leave>",     _update_leave)
        update_c.bind("<Button-1>",  _run_update)
        Tooltip(update_c, "Update MT Manager", position="above")

        # measure and size the canvas
        _f2 = self._font
        _fnt2 = tkf.Font(family=_f2, size=11, weight="bold")
        _rw = _fnt2.measure("\u21ba  Update") + 10 * 2
        _rh = _fnt2.metrics("linespace") + 3 * 2
        update_c.config(width=_rw, height=_rh)

    def _mk_status_item(self, parent, text, color, dot=False, icon=None,
                        side="left", varname=None):
        f = self._font
        fr = tk.Frame(parent, bg=BG2)
        fr.pack(side=side, padx=(0, 14), fill="y")
        if dot:
            d = tk.Canvas(fr, width=7, height=7, bg=BG2, highlightthickness=0)
            d.pack(side="left", padx=(0, 4), pady=10)
            d.create_oval(1, 1, 6, 6, fill=color, outline="")
        if icon:
            tk.Label(fr, text=icon, bg=BG2, fg=FG3, font=(f, 9)).pack(side="left")
        lbl = tk.Label(fr, text=text, bg=BG2, fg=FG3, font=(f, 8))
        lbl.pack(side="left")
        if varname:
            var = tk.StringVar(value=text)
            lbl.config(textvariable=var)
            setattr(self, varname, var)

    def _draw_scan_btn(self, _=None, hover=False):
        c = self._scan_canvas
        c.delete("all")
        w = c.winfo_width()
        h = c.winfo_height()
        if w < 4 or h < 4:
            return
        bg  = "#1d2b36" if hover else ACCENT_DIM
        bdr = ACCENT
        r   = 7
        # border rect
        pts = [r,0, w-r,0, w,0, w,r, w,h-r, w,h, w-r,h, r,h,
               0,h, 0,h-r, 0,r, 0,0, r,0]
        c.create_polygon(pts, smooth=True, fill=bdr, outline="")
        # inner fill
        pts2 = [r+1,1, w-r-1,1, w-1,1, w-1,r+1, w-1,h-r-1, w-1,h-1,
                w-r-1,h-1, r+1,h-1, 1,h-1, 1,h-r-1, 1,r+1, 1,1, r+1,1]
        c.create_polygon(pts2, smooth=True, fill=bg, outline="")
        _f = self._font
        c.create_text(w//2, h//2, text="\u25ce  Scan Metatrader",
                      fill=ACCENT, font=(_f, 9, "bold"))

    # ── Update Popup ──────────────────────────────────────────────────────────
    def _show_update_popup(self, update_sh):
        """Jalankan update.sh, tampilkan hasil sederhana dengan opsi restart."""
        f = self._font

        win = tk.Toplevel(self.root)
        win.title("Update")
        win.configure(bg=BG)
        win.geometry("420x180")
        win.resizable(False, False)
        win.attributes("-topmost", True)

        # Tengahkan relatif ke root
        win.update_idletasks()
        rx = self.root.winfo_x() + self.root.winfo_width()  // 2 - 210
        ry = self.root.winfo_y() + self.root.winfo_height() // 2 - 90
        win.geometry(f"420x180+{rx}+{ry}")
        win.deiconify()
        win.update()
        try:
            win.grab_set()
        except Exception:
            pass

        body = tk.Frame(win, bg=BG, padx=28, pady=24)
        body.pack(fill="both", expand=True)

        icon_lbl = tk.Label(body, text="\u21ba", bg=BG, fg=ACCENT,
                            font=(f, 22))
        icon_lbl.grid(row=0, column=0, rowspan=2, padx=(0, 16), sticky="n")

        msg_var = tk.StringVar(value="Memeriksa update...")
        msg_lbl = tk.Label(body, textvariable=msg_var, bg=BG, fg=FG,
                           font=(f, 11, "bold"), anchor="w", justify="left")
        msg_lbl.grid(row=0, column=1, sticky="w")

        sub_var = tk.StringVar(value="")
        sub_lbl = tk.Label(body, textvariable=sub_var, bg=BG, fg=FG2,
                           font=(f, 9), anchor="w", justify="left")
        sub_lbl.grid(row=1, column=1, sticky="w", pady=(4, 0))

        # Footer tombol — tersembunyi dulu
        tk.Frame(win, bg=BORDER, height=1).pack(fill="x")
        foot = tk.Frame(win, bg=BG2, height=44)
        foot.pack(fill="x")
        foot.pack_propagate(False)
        foot_inner = tk.Frame(foot, bg=BG2, padx=12)
        foot_inner.pack(fill="both", expand=True)

        # tombol OK (tutup saja)
        ok_h, _ = make_pill_btn(foot_inner, "OK", win.destroy,
                                 bg=BG3, fg=FG, hover_bg=BG4,
                                 font_size=9, padx=20, pady=6, radius=7)

        # tombol Restart (tutup + relaunch)
        def _restart():
            win.destroy()
            import sys, os
            python = sys.executable
            os.execv(python, [python] + sys.argv)

        restart_h, _ = make_pill_btn(foot_inner, "\u21bb  Restart Aplikasi", _restart,
                                      bg=ACCENT_DIM, fg=ACCENT, hover_bg="#1d2b36",
                                      font_size=9, padx=20, pady=6, radius=7)

        def _done(already_updated):
            if already_updated:
                icon_lbl.config(text="\u2713", fg=ACCENT3)
                msg_var.set("Aplikasi sudah up-to-date.")
                sub_var.set("Tidak ada perubahan baru.")
                ok_h.pack(side="right", pady=8)
            else:
                icon_lbl.config(text="\u2713", fg=ACCENT3)
                msg_var.set("Update berhasil!")
                sub_var.set("Restart aplikasi untuk menerapkan perubahan.")
                restart_h.pack(side="right", pady=8, padx=(0, 6))
                ok_h.pack(side="right", pady=8)

        def _fail(msg):
            icon_lbl.config(text="\u2717", fg=DANGER)
            msg_var.set("Update gagal.")
            sub_var.set(msg[:72])
            ok_h.pack(side="right", pady=8)

        def _run():
            try:
                proc = subprocess.run(
                    ["bash", str(update_sh)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                out = proc.stdout or ""
                if proc.returncode != 0:
                    err = out.strip().splitlines()[-1] if out.strip() else f"exit {proc.returncode}"
                    win.after(0, _fail, err)
                elif "already up to date" in out.lower():
                    win.after(0, _done, True)
                else:
                    win.after(0, _done, False)
            except Exception as e:
                win.after(0, _fail, str(e))

        threading.Thread(target=_run, daemon=True).start()


    def _auto_update_check(self):
        """Cek update secara diam-diam saat startup; tampilkan popup hanya jika ada update baru."""
        update_sh = Path.home() / "vfx2" / "update.sh"
        if not update_sh.exists():
            return  # script tidak ada, skip tanpa notifikasi

        self._status("Memeriksa update otomatis…")

        def _run():
            try:
                proc = subprocess.run(
                    ["bash", str(update_sh)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    timeout=60,
                )
                out = proc.stdout or ""
                if proc.returncode == 0 and "already up to date" not in out.lower():
                    # Ada update baru — tampilkan popup
                    self.root.after(0, lambda: self._show_auto_update_result(True))
                else:
                    self.root.after(0, lambda: self._status("Aplikasi sudah up-to-date."))
            except subprocess.TimeoutExpired:
                self.root.after(0, lambda: self._status("Auto-update: timeout."))
            except Exception as e:
                self.root.after(0, lambda: self._status(f"Auto-update: {e}"))

        threading.Thread(target=_run, daemon=True).start()

    def _show_auto_update_result(self, has_update: bool):
        """Tampilkan notifikasi kecil bila auto-update mendeteksi versi baru."""
        if not has_update:
            return
        f = self._font
        win = tk.Toplevel(self.root)
        win.title("Update Tersedia")
        win.configure(bg=BG)
        win.geometry("400x160")
        win.resizable(False, False)
        win.attributes("-topmost", True)
        win.update_idletasks()
        rx = self.root.winfo_x() + self.root.winfo_width()  // 2 - 200
        ry = self.root.winfo_y() + self.root.winfo_height() // 2 - 80
        win.geometry(f"400x160+{rx}+{ry}")
        win.deiconify()
        win.lift()
        win.focus_force()

        body = tk.Frame(win, bg=BG, padx=28, pady=20)
        body.pack(fill="both", expand=True)

        tk.Label(body, text="↺", bg=BG, fg=ACCENT3,
                 font=(f, 22)).grid(row=0, column=0, rowspan=2, padx=(0,16), sticky="n")
        tk.Label(body, text="Update berhasil dipasang!",
                 bg=BG, fg=FG, font=(f, 11, "bold"), anchor="w").grid(row=0, column=1, sticky="w")
        tk.Label(body, text="Restart aplikasi untuk menerapkan perubahan.",
                 bg=BG, fg=FG2, font=(f, 9), anchor="w").grid(row=1, column=1, sticky="w", pady=(4,0))

        tk.Frame(win, bg=BORDER, height=1).pack(fill="x")
        foot = tk.Frame(win, bg=BG2, height=44)
        foot.pack(fill="x")
        foot.pack_propagate(False)
        foot_inner = tk.Frame(foot, bg=BG2, padx=12)
        foot_inner.pack(fill="both", expand=True)

        def _restart():
            win.destroy()
            import sys, os
            os.execv(sys.executable, [sys.executable] + sys.argv)

        r_h, _ = make_pill_btn(foot_inner, "↻  Restart Aplikasi", _restart,
                               bg=ACCENT_DIM, fg=ACCENT, hover_bg="#1d2b36",
                               font_size=9, padx=20, pady=6, radius=7)
        r_h.pack(side="right", pady=8, padx=(0, 6))

        ok_h, _ = make_pill_btn(foot_inner, "Nanti", win.destroy,
                               bg=BG3, fg=FG, hover_bg=BG4,
                               font_size=9, padx=20, pady=6, radius=7)
        ok_h.pack(side="right", pady=8)

        self._status("Update baru tersedia — restart untuk menerapkan.")

    # ── Shared helpers: resolve exe path & wine launcher ─────────────────────
    def _find_exe(self, t: dict, mt4_name: str, mt5_name: str):
        """Cari file exe untuk terminal t.  MT4 pakai install_path, MT5 pakai path langsung."""
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

    def _wine_launch(self, exe_path, label: str):
        """Jalankan exe_path via wine di background thread."""
        self._status(f"Membuka {label}…")
        def _do():
            try:
                subprocess.Popen(["wine", str(exe_path)],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                self.root.after(0, lambda: self._status(f"{label} sedang dibuka."))
            except FileNotFoundError:
                self.root.after(0, lambda: _themed_popup(self.root, "error",
                    "Wine tidak ditemukan",
                    "Perintah 'wine' tidak tersedia.\n"
                    "Install wine terlebih dahulu:\n  sudo apt install wine"))
            except Exception as e:
                self.root.after(0, lambda err=e: _themed_popup(self.root, "error",
                    "Gagal", f"Tidak dapat membuka {label}:\n{err}"))
        threading.Thread(target=_do, daemon=True).start()

    # ── Uninstall MT (jalankan Uninstall.exe) ─────────────────────────────────
    def uninstall_ea_exe(self):
        t = self._terminal()
        if not t:
            return

        terminal_path = Path(t["path"])
        uninstall_exe = None

        if t["type"] == "MT4":
            # Gunakan install_path yang sudah diparse saat scan
            install_path = t.get("install_path")
            if install_path:
                candidate = Path(install_path) / "uninstall.exe"
                if candidate.exists():
                    uninstall_exe = candidate
            if uninstall_exe is None:
                # Fallback: coba di folder AppData terminal
                candidate = terminal_path / "uninstall.exe"
                if candidate.exists():
                    uninstall_exe = candidate
            if uninstall_exe is None:
                ip_str = str(install_path) if install_path else "(gagal parse origin.txt)"
                _themed_popup(self.root, "error",
                    "Uninstall.exe tidak ditemukan",
                    f"File Uninstall.exe tidak dapat ditemukan untuk terminal:\n"
                    f"{t['name']} (MT4)\n\n"
                    f"Path instalasi dari origin.txt:\n{ip_str}\n\n"
                    f"Folder AppData:\n{terminal_path}"
                )
                return

        else:
            # MT5: Uninstall.exe ada langsung di folder MT
            candidate = terminal_path / "uninstall.exe"
            if candidate.exists():
                uninstall_exe = candidate

        if uninstall_exe is None:
            _themed_popup(self.root, "error",
                "Uninstall.exe tidak ditemukan",
                f"File Uninstall.exe tidak dapat ditemukan untuk terminal:\n"
                f"{t['name']} ({t['type']})\n\n"
                f"Folder yang diperiksa:\n{terminal_path}"
            )
            return

        # ── Konfirmasi popup custom ──────────────────────────────────────────
        f = self._font
        win = tk.Toplevel(self.root)
        win.title("Konfirmasi Uninstall MT")
        win.configure(bg=BG)
        win.resizable(False, False)
        win.attributes("-topmost", True)
        win.update_idletasks()

        body = tk.Frame(win, bg=BG, padx=28, pady=22)
        body.pack(fill="both", expand=True)

        # Icon + judul
        hdr = tk.Frame(body, bg=BG)
        hdr.pack(fill="x", pady=(0, 14))
        tk.Label(hdr, text="⚠", bg=BG, fg="#e07b00",
                 font=(f, 22)).pack(side="left", padx=(0, 14))
        title_col = tk.Frame(hdr, bg=BG)
        title_col.pack(side="left", fill="x", expand=True)
        tk.Label(title_col, text="Uninstall MT",
                 bg=BG, fg=FG, font=(f, 12, "bold"), anchor="w").pack(anchor="w")
        tk.Label(title_col, text=f"{t['name']}  ·  {t['type']}",
                 bg=BG, fg=FG3, font=(f, 9), anchor="w").pack(anchor="w")

        # Info path
        info_box = tk.Frame(body, bg=BG3, padx=12, pady=10)
        info_box.pack(fill="x", pady=(0, 14))
        tk.Label(info_box, text="FILE", bg=BG3, fg=FG3,
                 font=(f, 8), anchor="w").pack(anchor="w")
        exe_path_str = str(uninstall_exe)
        home_str = str(Path.home())
        if exe_path_str.startswith(home_str):
            exe_path_str = "~" + exe_path_str[len(home_str):]
        tk.Label(info_box, text=exe_path_str, bg=BG3, fg=ACCENT2,
                 font=(self._font_mono, 9), anchor="w",
                 wraplength=420, justify="left").pack(anchor="w")

        tk.Label(body,
                 text="Proses uninstall akan dijalankan via Wine.\n"
                      "Pastikan terminal MetaTrader sudah ditutup sebelum melanjutkan.",
                 bg=BG, fg=FG2, font=(f, 9), justify="left", anchor="w",
                 wraplength=440).pack(anchor="w", pady=(0, 4))

        # Footer tombol
        tk.Frame(win, bg=BORDER, height=1).pack(fill="x")
        foot = tk.Frame(win, bg=BG2, height=48)
        foot.pack(fill="x")
        foot.pack_propagate(False)
        fi = tk.Frame(foot, bg=BG2, padx=12)
        fi.pack(fill="both", expand=True)

        def _run_uninstall():
            win.destroy()
            self._run_uninstall_with_progress(uninstall_exe, t)

        run_h, _ = make_pill_btn(fi, "⚠  Lanjutkan Uninstall", _run_uninstall,
                                 bg="#2a1a00", fg="#e07b00", hover_bg="#3d2800",
                                 font_size=9, padx=20, pady=6, radius=7)
        run_h.pack(side="right", pady=8, padx=(0, 6))

        cancel_h, _ = make_pill_btn(fi, "Batal", win.destroy,
                                    bg=BG3, fg=FG, hover_bg=BG4,
                                    font_size=9, padx=20, pady=6, radius=7)
        cancel_h.pack(side="right", pady=8)

        win.update_idletasks()
        rx = self.root.winfo_x() + self.root.winfo_width()  // 2 - win.winfo_reqwidth()  // 2
        ry = self.root.winfo_y() + self.root.winfo_height() // 2 - win.winfo_reqheight() // 2
        win.geometry(f"+{rx}+{ry}")
        win.deiconify()
        win.lift()
        win.focus_force()

    # ── Progress window untuk Uninstall MT ───────────────────────────────────
    def _run_uninstall_with_progress(self, uninstall_exe: Path, t: dict):
        """
        Jalankan uninstall.exe via Wine dengan progress window.
        - Indeterminate progress bar berputar selama proses berjalan
        - Polling setiap 500ms untuk cek apakah proses sudah selesai
        - Setelah selesai: jalankan Scan MT otomatis
        - Hapus xdotool jika terinstall (tidak dipakai saat uninstall)
        """
        import time

        f = self._font

        # ── Progress window ──────────────────────────────────────────────
        pwin = tk.Toplevel(self.root)
        pwin.title("Uninstall MT — Sedang Berjalan")
        pwin.configure(bg=BG)
        pwin.resizable(False, False)
        pwin.attributes("-topmost", True)
        pwin.update_idletasks()
        rx = self.root.winfo_x() + self.root.winfo_width()  // 2 - 240
        ry = self.root.winfo_y() + self.root.winfo_height() // 2 - 130
        pwin.geometry(f"480x260+{rx}+{ry}")
        pwin.deiconify()

        # Header
        hdr = tk.Frame(pwin, bg=BG2, height=48)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        hdr_inner = tk.Frame(hdr, bg=BG2, padx=20)
        hdr_inner.pack(fill="both", expand=True)
        tk.Label(hdr_inner, text="\u26d4  Uninstall MT",
                 bg=BG2, fg="#e07b00", font=(f, 12, "bold")).pack(side="left", fill="y")
        tk.Frame(pwin, bg=BORDER, height=1).pack(fill="x")

        # Body
        body = tk.Frame(pwin, bg=BG, padx=28, pady=20)
        body.pack(fill="both", expand=True)

        icon_lbl = tk.Label(body, text="\u23f3", bg=BG, fg="#e07b00", font=(f, 22))
        icon_lbl.grid(row=0, column=0, rowspan=3, padx=(0, 16), sticky="n")

        title_lbl = tk.Label(body,
            text=f"Menjalankan uninstall {t['name']}…",
            bg=BG, fg=FG, font=(f, 11, "bold"), anchor="w")
        title_lbl.grid(row=0, column=1, sticky="w")

        sub_lbl = tk.Label(body,
            text=f"{t['type']}  ·  harap tunggu, jangan tutup window ini",
            bg=BG, fg=FG2, font=(f, 9), anchor="w")
        sub_lbl.grid(row=1, column=1, sticky="w", pady=(3, 8))

        # Progress bar (indeterminate menggunakan animasi manual)
        prog_frame = tk.Frame(body, bg=BG)
        prog_frame.grid(row=2, column=1, sticky="ew")
        body.columnconfigure(1, weight=1)

        progress = ProgressBar(prog_frame, height=6, bg=BG4, fill="#e07b00")
        progress.pack(fill="x")

        pct_var = tk.StringVar(value="")
        pct_lbl = tk.Label(prog_frame, textvariable=pct_var,
                           bg=BG, fg=FG3, font=(f, 8))
        pct_lbl.pack(anchor="e", pady=(3, 0))

        # Footer
        tk.Frame(pwin, bg=BORDER, height=1).pack(fill="x")
        foot = tk.Frame(pwin, bg=BG2, height=44); foot.pack(fill="x")
        foot.pack_propagate(False)
        fi = tk.Frame(foot, bg=BG2, padx=12); fi.pack(fill="both", expand=True)

        close_h, _ = make_pill_btn(fi, "Tutup", pwin.destroy,
                                   bg=BG3, fg=FG, hover_bg=BG4,
                                   font_size=9, padx=20, pady=6, radius=7)
        # Tombol tutup hanya muncul setelah selesai

        _state = {"proc": None, "done": False, "anim_pct": 0.0, "anim_dir": 1}

        # ── Animasi indeterminate progress bar ──────────────────────────
        def _animate():
            if _state["done"]:
                return
            p = _state["anim_pct"]
            d = _state["anim_dir"]
            p += d * 0.03
            if p >= 1.0:
                p = 1.0; _state["anim_dir"] = -1
            elif p <= 0.0:
                p = 0.0; _state["anim_dir"] = 1
            _state["anim_pct"] = p
            progress.set(p)
            pwin.after(60, _animate)

        # ── Polling: cek apakah proses wine sudah selesai ────────────────
        def _poll():
            proc = _state["proc"]
            if proc is None:
                pwin.after(300, _poll)
                return
            if proc.poll() is None:
                # Masih berjalan
                pwin.after(500, _poll)
                return
            # Proses selesai
            _state["done"] = True
            _on_uninstall_done(proc.returncode)

        def _on_uninstall_done(returncode: int):
            progress.set(1.0)
            pct_var.set("")

            # ── Hapus xdotool jika terinstall ────────────────────────────
            xdotool_removed = False
            try:
                if shutil.which("xdotool"):
                    result = subprocess.run(
                        ["sudo", "apt-get", "remove", "-y", "xdotool"],
                        capture_output=True, text=True, timeout=30
                    )
                    xdotool_removed = (result.returncode == 0)
            except Exception:
                pass

            if returncode == 0:
                icon_lbl.config(text="\u2713", fg="#5ecf3e")
                title_lbl.config(text="Uninstall selesai!", fg="#5ecf3e")
                extra = "\nxdotool berhasil dihapus." if xdotool_removed else ""
                sub_lbl.config(
                    text=f"Proses uninstall {t['name']} selesai.{extra}\n"
                          "Scan MT dijalankan otomatis…",
                    fg=FG2)
            else:
                icon_lbl.config(text="\u26a0", fg=WARN)
                title_lbl.config(
                    text=f"Uninstall selesai (kode: {returncode})", fg=WARN)
                sub_lbl.config(
                    text="Proses wine sudah berhenti. Cek apakah uninstall berhasil.",
                    fg=FG2)

            close_h.pack(side="right", pady=8)
            self._status(
                f"Uninstall {t['name']} selesai (rc={returncode}).")
            # Scan MT otomatis setelah uninstall selesai
            self.root.after(800, self.scan_terminals)

        # ── Jalankan wine di thread background ──────────────────────────
        def _do():
            try:
                proc = subprocess.Popen(
                    ["wine", str(uninstall_exe)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                _state["proc"] = proc
            except FileNotFoundError:
                pwin.after(0, lambda: (
                    icon_lbl.config(text="\u2715", fg=DANGER),
                    title_lbl.config(text="Wine tidak ditemukan", fg=DANGER),
                    sub_lbl.config(
                        text="Perintah 'wine' tidak tersedia.\n"
                             "Install wine: sudo apt install wine",
                        fg=DANGER),
                    close_h.pack(side="right", pady=8),
                ))
                _state["done"] = True
            except Exception as e:
                pwin.after(0, lambda err=e: (
                    icon_lbl.config(text="\u2715", fg=DANGER),
                    title_lbl.config(text="Gagal menjalankan uninstall", fg=DANGER),
                    sub_lbl.config(text=str(err), fg=DANGER),
                    close_h.pack(side="right", pady=8),
                ))
                _state["done"] = True

        threading.Thread(target=_do, daemon=True).start()
        pwin.after(100, _poll)
        _animate()

    # ── Open MT (jalankan terminal.exe / terminal64.exe) ──────────────────────
    def open_mt(self):
        t = self._terminal()
        if not t:
            return
        exe = self._find_exe(t, "terminal.exe", "terminal64.exe")
        if exe is None:
            name = "terminal64.exe" if t["type"] == "MT5" else "terminal.exe"
            _themed_popup(self.root, "error", f"{name} tidak ditemukan",
                f"File {name} tidak ditemukan untuk {t['name']} ({t['type']})\n"
                f"Folder: {t['path']}")
            return
        self._wine_launch(exe, f"{t['name']} ({t['type']})")

    # ── Open MetaEditor ────────────────────────────────────────────────────────
    def open_metaeditor(self):
        t = self._terminal()
        if not t:
            return
        exe = self._find_exe(t, "metaeditor.exe", "MetaEditor64.exe")
        if exe is None:
            name = "MetaEditor64.exe" if t["type"] == "MT5" else "metaeditor.exe"
            _themed_popup(self.root, "error", f"{name} tidak ditemukan",
                f"File {name} tidak ditemukan untuk {t['name']} ({t['type']})\n"
                f"Folder: {t['path']}")
            return
        self._wine_launch(exe, f"MetaEditor {t['name']} ({t['type']})")

    # ── Install MT (dari file .exe installer) ─────────────────────────────────
    def install_mt(self):
        """Pilih file installer MT (.exe), lalu langsung jalankan via Wine."""
        f  = self._font
        fm = self._font_mono

        win = tk.Toplevel(self.root)
        win.title("Install MetaTrader")
        win.configure(bg=BG)
        win.resizable(False, False)
        win.attributes("-topmost", True)
        win.update_idletasks()
        rx = self.root.winfo_x() + self.root.winfo_width()  // 2 - 270
        ry = self.root.winfo_y() + self.root.winfo_height() // 2 - 130
        win.geometry(f"540x260+{rx}+{ry}")
        win.deiconify()

        # Header
        hdr = tk.Frame(win, bg=BG2, height=48)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        hdr_inner = tk.Frame(hdr, bg=BG2, padx=20)
        hdr_inner.pack(fill="both", expand=True)
        tk.Label(hdr_inner, text="\u2b07  Install MetaTrader",
                 bg=BG2, fg=FG, font=(f, 12, "bold")).pack(side="left", fill="y")
        tk.Frame(win, bg=BORDER, height=1).pack(fill="x")

        # Body
        body = tk.Frame(win, bg=BG, padx=24, pady=20)
        body.pack(fill="both", expand=True)

        tk.Label(body, text="FILE INSTALLER (.EXE)",
                 bg=BG, fg=FG3, font=(f, 8), anchor="w").pack(fill="x")

        file_row = tk.Frame(body, bg=BG)
        file_row.pack(fill="x", pady=(4, 0))

        installer_var = tk.StringVar(value="")

        entry_border = tk.Frame(file_row, bg=BORDER2, padx=1, pady=1)
        entry_border.pack(side="left", fill="x", expand=True, padx=(0, 8))
        installer_entry = tk.Entry(
            entry_border, textvariable=installer_var,
            bg=BG3, fg=FG2, insertbackground=ACCENT,
            relief="flat", font=(fm, 9), highlightthickness=0,
            state="readonly",
        )
        installer_entry.pack(fill="x", ipady=7, padx=1)

        def _pick_file():
            try:
                win.grab_release()
            except Exception:
                pass

            def _do_yad():
                result = yad_pick_file(
                    title="Pilih File Installer MT",
                    filetypes=["*.exe"],
                    start_dir=DOCS_DIR,
                    root_widget=self.root,
                )
                def _back():
                    if result:
                        installer_var.set(result)
                        entry_border.config(bg=ACCENT)
                        win.after(200, lambda: entry_border.config(bg=BORDER2))
                    try:
                        win.grab_set()
                    except Exception:
                        pass
                win.after(0, _back)

            threading.Thread(target=_do_yad, daemon=True).start()

        bh, _ = make_pill_btn(file_row, "\u25a6 Browse",
                              _pick_file,
                              bg=BG3, fg=FG, hover_bg=BG4,
                              font_size=10, padx=12, pady=7, radius=7)
        bh.pack(side="left")

        # Status mini
        status_var = tk.StringVar(value="")
        status_lbl = tk.Label(body, textvariable=status_var,
                              bg=BG, fg=FG3, font=(f, 9), anchor="w")
        status_lbl.pack(fill="x", pady=(12, 0))

        # Footer
        tk.Frame(win, bg=BORDER, height=1).pack(fill="x")
        foot = tk.Frame(win, bg=BG2, height=50)
        foot.pack(fill="x")
        foot.pack_propagate(False)
        fi = tk.Frame(foot, bg=BG2, padx=14)
        fi.pack(fill="both", expand=True)

        def _run_install():
            path = installer_var.get().strip()
            if not path:
                status_var.set("\u26a0  Pilih file installer terlebih dahulu.")
                status_lbl.config(fg=WARN)
                return
            if not Path(path).exists():
                status_var.set("\u26a0  File tidak ditemukan.")
                status_lbl.config(fg=DANGER)
                return
            win.destroy()
            self._run_mt_installer(Path(path), 1)

        run_h, _ = make_pill_btn(fi, "\u2b07  Mulai Install", _run_install,
                                 bg="#0a1f0a", fg="#5ecf3e", hover_bg="#152e15",
                                 font_size=10, padx=20, pady=7, radius=7)
        run_h.pack(side="right", pady=8, padx=(0, 6))

        cancel_h, _ = make_pill_btn(fi, "Batal", win.destroy,
                                    bg=BG3, fg=FG, hover_bg=BG4,
                                    font_size=9, padx=20, pady=6, radius=7)
        cancel_h.pack(side="right", pady=8)

    # ── helpers: deteksi tipe installer & silent install ────────────────────
    @staticmethod
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

    @staticmethod
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

    @staticmethod
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
        # "C:\Program Files (x86)\MT4 Broker 1"
        #   → ~/.wine/drive_c/Program Files (x86)/MT4 Broker 1
        try:
            wp = install_dir_win.replace("\\", "/").strip()
            if len(wp) >= 3 and wp[1] == ":":
                wp = wp[3:]
            linux_path = Path.home() / ".wine/drive_c" / wp.lstrip("/")
            return linux_path.exists()
        except Exception:
            return proc.returncode == 0

    @staticmethod
    def _xdotool_fill_installer(win_id: str, dir_val: str, group_val: str,
                                 log_fn=None) -> bool:
        """
        Isi field "Installation folder" dan "Program group" di window installer
        Wine/Inno Setup menggunakan xdotool.

        Strategi (robust):
          1. Fokus & raise window, tunggu fully painted
          2. Dapatkan geometri window (posisi + ukuran)
          3. Klik langsung ke koordinat field pertama (Installation folder)
             berdasarkan rasio posisi relatif window — lebih reliable dari Tab
          4. Ctrl+A + Delete untuk clear, lalu type nilai baru karakter per karakter
          5. Ulangi untuk field "Program group" (di bawah field pertama)
          6. Klik tombol Next (pojok kanan bawah) atau tekan Alt+N
        """
        import time

        def _run(cmd, timeout=5):
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
                if log_fn:
                    log_fn(f"xdotool {' '.join(str(c) for c in cmd[1:])}: rc={r.returncode}"
                           + (f" out={r.stdout.strip()}" if r.stdout.strip() else ""))
                return r
            except Exception as e:
                if log_fn:
                    log_fn(f"xdotool error: {e}")
                return None

        def _ok(cmd, timeout=5):
            r = _run(cmd, timeout)
            return r is not None and r.returncode == 0

        def _type_field(value: str):
            """Ketik nilai ke field yang sedang fokus, pakai xdotool type dengan delay."""
            # Gunakan --clearmodifiers agar Caps Lock / Shift tidak interfere
            # --delay 30ms antar karakter agar Wine buffer tidak overflow
            _ok(["xdotool", "key", "--window", win_id, "--clearmodifiers", "ctrl+a"])
            time.sleep(0.08)
            _ok(["xdotool", "key", "--window", win_id, "--clearmodifiers", "Delete"])
            time.sleep(0.08)
            # Type nilai — pecah per 20 karakter untuk hindari buffer drop
            chunk = 20
            for start in range(0, len(value), chunk):
                part = value[start:start + chunk]
                _ok(["xdotool", "type", "--window", win_id,
                     "--clearmodifiers", "--delay", "30", part])
                time.sleep(0.05)

        # ── 1. Fokus & raise ────────────────────────────────────────────
        _ok(["xdotool", "windowfocus", "--sync", win_id])
        time.sleep(0.4)
        _ok(["xdotool", "windowraise", win_id])
        time.sleep(0.3)

        # ── 2. Dapatkan geometri window ─────────────────────────────────
        geo_r = _run(["xdotool", "getwindowgeometry", "--shell", win_id])
        win_x, win_y, win_w, win_h = 0, 0, 500, 400
        if geo_r and geo_r.returncode == 0:
            for line in geo_r.stdout.splitlines():
                line = line.strip()
                if line.startswith("X="):
                    try: win_x = int(line.split("=")[1])
                    except ValueError: pass
                elif line.startswith("Y="):
                    try: win_y = int(line.split("=")[1])
                    except ValueError: pass
                elif line.startswith("WIDTH="):
                    try: win_w = int(line.split("=")[1])
                    except ValueError: pass
                elif line.startswith("HEIGHT="):
                    try: win_h = int(line.split("=")[1])
                    except ValueError: pass

        if log_fn:
            log_fn(f"Window geo: {win_x},{win_y} {win_w}x{win_h}")

        # ── 3. Klik ke field "Installation folder" ──────────────────────
        # Inno Setup layout (Weltrade/MT4/MT5):
        #   • Field pertama  ≈ 45% dari atas, 40% dari kiri (area teks entry)
        #   • Field kedua    ≈ 65% dari atas (Program group)
        # Koordinat absolut = win_x + offset_x, win_y + offset_y
        field1_abs_x = win_x + int(win_w * 0.40)
        field1_abs_y = win_y + int(win_h * 0.45)
        field2_abs_x = win_x + int(win_w * 0.40)
        field2_abs_y = win_y + int(win_h * 0.64)

        # Klik field 1 (Installation folder)
        _ok(["xdotool", "mousemove", "--sync",
             str(field1_abs_x), str(field1_abs_y)])
        time.sleep(0.1)
        _ok(["xdotool", "click", "1"])
        time.sleep(0.2)
        _ok(["xdotool", "click", "1"])   # double-click = select all text
        time.sleep(0.15)

        _type_field(dir_val)
        time.sleep(0.25)

        # ── 4. Klik ke field "Program group" ────────────────────────────
        _ok(["xdotool", "mousemove", "--sync",
             str(field2_abs_x), str(field2_abs_y)])
        time.sleep(0.1)
        _ok(["xdotool", "click", "1"])
        time.sleep(0.2)
        _ok(["xdotool", "click", "1"])
        time.sleep(0.15)

        _type_field(group_val)
        time.sleep(0.25)

        # ── 5. Klik Next ─────────────────────────────────────────────────
        # Tombol Next di Inno Setup ada di kanan bawah, sekitar 75% x, 90% y
        # Fallback: Alt+N (shortcut default Inno Setup untuk &Next)
        next_abs_x = win_x + int(win_w * 0.76)
        next_abs_y = win_y + int(win_h * 0.91)
        _ok(["xdotool", "mousemove", "--sync",
             str(next_abs_x), str(next_abs_y)])
        time.sleep(0.1)
        _ok(["xdotool", "click", "1"])
        time.sleep(0.4)

        # Fallback: jika Next belum terpencet (window masih sama), kirim Alt+N
        _ok(["xdotool", "key", "--window", win_id,
             "--clearmodifiers", "alt+n"])
        time.sleep(0.3)

        return True

    def _run_mt_installer(self, installer_path: Path, qty: int, base_name: str = ""):
        """Jalankan installer sebanyak qty kali via Wine, satu per satu.

        - Deteksi tipe installer (NSIS / Inno Setup / unknown)
        - NSIS: coba /S /D= /GROUP= (silent)
        - Inno Setup / unknown: jalankan normal, lalu pakai xdotool untuk
          auto-fill field "Installation folder" & "Program group"
        - Setiap instance mendapat suffix angka: "Nama 1", "Nama 2", dst.
        """
        f = self._font

        base_stem    = base_name.strip() if base_name.strip() else installer_path.stem
        inst_type    = self._detect_installer_type(installer_path)
        has_xdotool  = bool(shutil.which("xdotool"))

        # ── Progress window ──────────────────────────────────────────────
        win = tk.Toplevel(self.root)
        win.title("Menjalankan Installer")
        win.configure(bg=BG)
        win.resizable(False, False)
        win.update_idletasks()
        rx = self.root.winfo_x() + self.root.winfo_width()  // 2 - 240
        ry = self.root.winfo_y() + self.root.winfo_height() // 2 - 140
        win.geometry(f"480x280+{rx}+{ry}")
        win.deiconify()

        body = tk.Frame(win, bg=BG, padx=28, pady=20)
        body.pack(fill="both", expand=True)

        icon_lbl = tk.Label(body, text="\u2b07", bg=BG, fg="#5ecf3e",
                            font=(f, 22))
        icon_lbl.grid(row=0, column=0, rowspan=4, padx=(0, 16), sticky="n")

        title_lbl = tk.Label(body, text="Memulai installer\u2026",
                             bg=BG, fg=FG, font=(f, 11, "bold"), anchor="w")
        title_lbl.grid(row=0, column=1, sticky="w")

        sub_lbl = tk.Label(body, text=installer_path.name,
                           bg=BG, fg=FG2, font=(f, 9), anchor="w")
        sub_lbl.grid(row=1, column=1, sticky="w", pady=(2, 0))

        dir_var = tk.StringVar(value="")
        dir_lbl = tk.Label(body, textvariable=dir_var,
                           bg=BG, fg=FG3, font=(f, 8), anchor="w")
        dir_lbl.grid(row=2, column=1, sticky="w", pady=(2, 6))

        prog_frame = tk.Frame(body, bg=BG)
        prog_frame.grid(row=3, column=1, sticky="ew")
        body.columnconfigure(1, weight=1)

        progress = ProgressBar(prog_frame, height=3, bg=BG4, fill="#5ecf3e")
        progress.pack(fill="x")

        count_var = tk.StringVar(value=f"0 / {qty}")
        tk.Label(prog_frame, textvariable=count_var,
                 bg=BG, fg=FG3, font=(f, 8)).pack(anchor="e", pady=(3, 0))

        # method label (NSIS silent / xdotool / manual)
        method_var = tk.StringVar(value="")
        tk.Label(body, textvariable=method_var,
                 bg=BG, fg=FG3, font=(f, 8), anchor="w").grid(
                 row=4, column=1, sticky="w", pady=(4, 0))

        tk.Frame(win, bg=BORDER, height=1).pack(fill="x")
        foot = tk.Frame(win, bg=BG2, height=44)
        foot.pack(fill="x")
        foot.pack_propagate(False)
        fi = tk.Frame(foot, bg=BG2, padx=12)
        fi.pack(fill="both", expand=True)

        close_h, _ = make_pill_btn(fi, "Tutup", win.destroy,
                                   bg=BG3, fg=FG, hover_bg=BG4,
                                   font_size=9, padx=20, pady=6, radius=7)

        _cancelled    = [False]
        _current_proc = [None]

        def _do_cancel():
            _cancelled[0] = True
            proc = _current_proc[0]
            if proc and proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(timeout=3)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
            icon_lbl.config(text="\u23f9", fg=WARN)
            title_lbl.config(text="Instalasi dibatalkan.", fg=WARN)
            sub_lbl.config(text="Proses yang sedang berjalan dihentikan.", fg=FG2)
            dir_var.set("")
            method_var.set("")
            cancel_h.pack_forget()
            close_h.pack(side="right", pady=8)

        cancel_h, _ = make_pill_btn(fi, "\u2715  Cancel", _do_cancel,
                                    bg="#2a0f0f", fg=DANGER, hover_bg="#3d1212",
                                    font_size=9, padx=20, pady=6, radius=7)
        cancel_h.pack(side="right", pady=8, padx=(0, 6))

        def _do():
            import time
            errors   = []
            done_cnt = [0]

            for i in range(qty):
                if _cancelled[0]:
                    break

                suffix     = f" {i + 1}" if qty > 1 else ""
                # Nilai yang akan diisi di installer
                dir_value  = f"{base_stem}{suffix}"   # nama folder (tanpa path lengkap)
                group_value = f"{base_stem}{suffix}"  # nama program group
                # Wine full path untuk NSIS /D=
                win_path   = f"C:\\Program Files (x86)\\{dir_value}"

                def _upd(idx=i, dv=dir_value):
                    title_lbl.config(text=f"Installer {idx + 1} dari {qty}\u2026")
                    count_var.set(f"{idx} / {qty}")
                    progress.set(idx / qty if qty > 1 else 0.05)
                    dir_var.set(f"\u2192 {dv}")
                win.after(0, _upd)

                # ── Tahap 1: Coba silent install ────────────────────────
                silent_ok = False
                if inst_type in ("inno", "nsis"):
                    mode_label = (
                        "Mode: Inno Setup silent (/VERYSILENT)"
                        if inst_type == "inno"
                        else "Mode: NSIS silent (/S)"
                    )
                    win.after(0, lambda ml=mode_label: method_var.set(ml))
                    try:
                        proc = self._try_silent_install(
                            installer_path, inst_type,
                            win_path, group_value,
                        )
                        if proc:
                            _current_proc[0] = proc
                            silent_ok = self._silent_succeeded(proc, win_path)
                            _current_proc[0] = None
                            if _cancelled[0]:
                                break
                            if silent_ok:
                                done_cnt[0] += 1
                            else:
                                # Silent diluncurkan tapi folder tidak terbuat
                                # → log sebagai warning, lanjut ke fallback
                                errors.append(
                                    f"[{i+1}] Silent gagal (folder tidak terbuat),"
                                    f" fallback ke GUI."
                                )
                    except FileNotFoundError:
                        errors.append(f"[{i+1}] wine tidak ditemukan")
                        break
                    except Exception as e:
                        errors.append(f"[{i+1}] silent error: {e}")

                if _cancelled[0]:
                    break

                # ── Tahap 2: Fallback GUI + xdotool (jika silent gagal) ──
                if not silent_ok:
                    if has_xdotool:
                        win.after(0, lambda: method_var.set(
                            "Fallback: xdotool auto-fill — jangan sentuh keyboard/mouse"))
                    else:
                        win.after(0, lambda: method_var.set(
                            "Fallback: manual — isi folder & group sesuai nama di atas"))

                    try:
                        proc = subprocess.Popen(
                            ["wine", str(installer_path)],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                        )
                        _current_proc[0] = proc

                        if has_xdotool:
                            wine_win_id = None
                            for _ in range(40):
                                if _cancelled[0]:
                                    break
                                time.sleep(0.5)
                                r = subprocess.run(
                                    ["xdotool", "search", "--onlyvisible",
                                     "--pid", str(proc.pid), "--name", ""],
                                    capture_output=True, text=True, timeout=5,
                                )
                                ids = r.stdout.strip().splitlines()
                                if not ids:
                                    continue
                                best_id   = None
                                best_area = 0
                                for wid in ids:
                                    wid = wid.strip()
                                    if not wid:
                                        continue
                                    gr = subprocess.run(
                                        ["xdotool", "getwindowgeometry",
                                         "--shell", wid],
                                        capture_output=True, text=True, timeout=3,
                                    )
                                    if gr.returncode != 0:
                                        continue
                                    ww = wh = 0
                                    for gl in gr.stdout.splitlines():
                                        gl = gl.strip()
                                        if gl.startswith("WIDTH="):
                                            try: ww = int(gl.split("=")[1])
                                            except ValueError: pass
                                        elif gl.startswith("HEIGHT="):
                                            try: wh = int(gl.split("=")[1])
                                            except ValueError: pass
                                    area = ww * wh
                                    if area > best_area and ww >= 200 and wh >= 200:
                                        best_area = area
                                        best_id   = wid
                                if best_id:
                                    wine_win_id = best_id
                                    break

                            if wine_win_id and not _cancelled[0]:
                                time.sleep(2.0)
                                self._xdotool_fill_installer(
                                    wine_win_id, dir_value, group_value)

                        proc.wait()
                        _current_proc[0] = None
                        if not _cancelled[0]:
                            done_cnt[0] += 1

                    except FileNotFoundError:
                        errors.append(f"[{i+1}] wine tidak ditemukan")
                        break
                    except Exception as e:
                        errors.append(f"[{i+1}] {e}")

            def _done():
                if _cancelled[0]:
                    return
                progress.set(1.0)
                count_var.set(f"{done_cnt[0]} / {qty}")
                dir_var.set("")
                method_var.set("")
                if errors:
                    icon_lbl.config(text="\u26a0", fg=WARN)
                    title_lbl.config(text=f"Selesai dengan {len(errors)} error.", fg=WARN)
                    sub_lbl.config(text="\n".join(errors[:3]), fg=DANGER)
                else:
                    icon_lbl.config(text="\u2713", fg="#5ecf3e")
                    title_lbl.config(
                        text=f"{done_cnt[0]} installer selesai dijalankan.", fg=FG)
                    sub_lbl.config(
                        text="Scan otomatis dijalankan.", fg=FG2)
                cancel_h.pack_forget()
                close_h.pack(side="right", pady=8)
                self._status(
                    f"Install MT selesai: {done_cnt[0]}/{qty} dari {installer_path.name}")
                self.root.after(800, self.scan_terminals)

            win.after(0, _done)

        threading.Thread(target=_do, daemon=True).start()

    def _install_menu(self):
        """Dropdown menu install — popup ditutup SEBELUM yad dibuka."""
        f = self._font

        if getattr(self, "_install_popup_open", False):
            return
        self._install_popup_open = True

        popup = tk.Toplevel(self.root)
        popup.wm_overrideredirect(True)
        popup.attributes("-topmost", True)

        outer = tk.Frame(popup, bg=BORDER2, padx=1, pady=1)
        outer.pack()
        inner = tk.Frame(outer, bg=BG3)
        inner.pack()

        items = [
            ("\u2191  Install Expert Advisor", self.install_ea),
            ("\u2191  Install Indicator",       self.install_indicator),
        ]

        _closed = [False]

        def _close_popup():
            if _closed[0]:
                return
            _closed[0] = True
            self._install_popup_open = False
            try:
                popup.destroy()
            except Exception:
                pass

        def _make_item(text, cmd):
            row = tk.Frame(inner, bg=BG3, cursor="hand2")
            row.pack(fill="x")
            lbl = tk.Label(row, text=text, bg=BG3, fg=FG,
                           font=(f, 10), anchor="w", padx=16, pady=8)
            lbl.pack(fill="x")

            def _enter(_): row.config(bg=BG4); lbl.config(bg=BG4, fg=ACCENT)
            def _leave(_): row.config(bg=BG3); lbl.config(bg=BG3, fg=FG)
            def _click(_):
                # tutup dropdown DULU, baru buka yad — tidak ada overlap
                _close_popup()
                self.root.update()          # flush destroy ke X11
                self.root.after(50, cmd)    # jalankan setelah frame berikutnya

            for w in (row, lbl):
                w.bind("<Enter>",    _enter)
                w.bind("<Leave>",    _leave)
                w.bind("<Button-1>", _click)

        for text, cmd in items:
            _make_item(text, cmd)

        popup.update_idletasks()
        btn = self._install_btn_holder
        bx  = btn.winfo_rootx()
        by  = btn.winfo_rooty()
        bh  = btn.winfo_height()
        popup.wm_geometry(f"+{bx}+{by + bh + 2}")

        # Tutup bila klik di luar area popup (di dalam jendela Tk)
        def _on_press_outside(event):
            if _closed[0]:
                return
            try:
                wx = popup.winfo_rootx(); wy = popup.winfo_rooty()
                ww = popup.winfo_width(); wh = popup.winfo_height()
                if not (wx <= event.x_root <= wx + ww
                        and wy <= event.y_root <= wy + wh):
                    _close_popup()
            except Exception:
                _close_popup()

        self.root.bind_all("<ButtonPress-1>", _on_press_outside, add=True)

        # Tutup juga bila mouse bergerak jauh dari popup (fallback untuk klik
        # ke window non-Tk seperti yad file picker)
        def _poll():
            if _closed[0]:
                return
            try:
                mx = self.root.winfo_pointerx()
                my = self.root.winfo_pointery()
                wx = popup.winfo_rootx(); wy = popup.winfo_rooty()
                ww = popup.winfo_width(); wh = popup.winfo_height()
                # margin 80px — kalau pointer jauh dari popup, anggap sudah pindah
                margin = 80
                if not (wx - margin <= mx <= wx + ww + margin
                        and wy - margin <= my <= wy + wh + margin):
                    _close_popup()
                    return
                popup.after(150, _poll)
            except Exception:
                _close_popup()

        popup.after(300, _poll)   # mulai poll 300ms setelah popup muncul

        def _cleanup(_=None):
            try:
                self.root.unbind_all("<ButtonPress-1>")
            except Exception:
                pass
            self._install_popup_open = False

        popup.bind("<Destroy>", _cleanup)

    # ── Install MT dropdown menu ───────────────────────────────────────────────
    def _install_mt_menu(self):
        """Dropdown: ⬇ Install MT  /  ⎘ Duplikat MT."""
        f = self._font

        if getattr(self, "_install_mt_popup_open", False):
            return
        self._install_mt_popup_open = True

        popup = tk.Toplevel(self.root)
        popup.wm_overrideredirect(True)
        popup.attributes("-topmost", True)

        outer = tk.Frame(popup, bg=BORDER2, padx=1, pady=1)
        outer.pack()
        inner = tk.Frame(outer, bg=BG3)
        inner.pack()

        items = [
            ("\u2b07  Install MT",  self.install_mt),
            ("\u2398  Duplikat MT", self.duplicate_mt),
        ]

        _closed = [False]

        def _close_popup():
            if _closed[0]:
                return
            _closed[0] = True
            self._install_mt_popup_open = False
            try:
                popup.destroy()
            except Exception:
                pass

        def _make_item(text, cmd):
            row = tk.Frame(inner, bg=BG3, cursor="hand2")
            row.pack(fill="x")
            lbl = tk.Label(row, text=text, bg=BG3, fg=FG,
                           font=(f, 10), anchor="w", padx=16, pady=8)
            lbl.pack(fill="x")

            def _enter(_): row.config(bg=BG4); lbl.config(bg=BG4, fg=ACCENT)
            def _leave(_): row.config(bg=BG3); lbl.config(bg=BG3, fg=FG)
            def _click(_):
                _close_popup()
                self.root.update()
                self.root.after(50, cmd)

            for w in (row, lbl):
                w.bind("<Enter>",    _enter)
                w.bind("<Leave>",    _leave)
                w.bind("<Button-1>", _click)

        for text, cmd in items:
            _make_item(text, cmd)

        popup.update_idletasks()
        btn = self._install_mt_btn_holder
        bx  = btn.winfo_rootx()
        by  = btn.winfo_rooty()
        bh  = btn.winfo_height()
        popup.wm_geometry(f"+{bx}+{by + bh + 2}")

        def _on_press_outside(event):
            if _closed[0]:
                return
            try:
                wx = popup.winfo_rootx(); wy = popup.winfo_rooty()
                ww = popup.winfo_width(); wh = popup.winfo_height()
                if not (wx <= event.x_root <= wx + ww
                        and wy <= event.y_root <= wy + wh):
                    _close_popup()
            except Exception:
                _close_popup()

        self.root.bind_all("<ButtonPress-1>", _on_press_outside, add=True)

        def _poll():
            if _closed[0]:
                return
            try:
                mx = self.root.winfo_pointerx()
                my = self.root.winfo_pointery()
                wx = popup.winfo_rootx(); wy = popup.winfo_rooty()
                ww = popup.winfo_width(); wh = popup.winfo_height()
                margin = 80
                if not (wx - margin <= mx <= wx + ww + margin
                        and wy - margin <= my <= wy + wh + margin):
                    _close_popup()
                    return
                popup.after(150, _poll)
            except Exception:
                _close_popup()

        popup.after(300, _poll)

        def _cleanup(_=None):
            try:
                self.root.unbind_all("<ButtonPress-1>")
            except Exception:
                pass
            self._install_mt_popup_open = False

        popup.bind("<Destroy>", _cleanup)

    # ── Duplikat MT ────────────────────────────────────────────────────────────
    def duplicate_mt(self):
        """Duplikat folder instalasi MT yang dipilih di tabel, dimulai dari nomor 2."""
        t = self._terminal(silent=False)
        if not t:
            return

        f  = self._font
        fm = self._font_mono

        mt_type = t.get("type", "MT4")

        # Folder sumber & base path tujuan sesuai tipe MT
        if mt_type == "MT4":
            src_root_str = t.get("install_path", "")
            linux_base   = Path.home() / ".wine/drive_c/Program Files (x86)"
        else:
            src_root_str = t.get("path", "")
            linux_base   = Path.home() / ".wine/drive_c/Program Files"

        src_folder: Path | None = None
        if src_root_str:
            candidate = Path(src_root_str)
            if candidate.exists():
                src_folder = candidate

        if src_folder is None:
            terminal_path = Path(t.get("path", ""))
            for candidate in [terminal_path, terminal_path.parent]:
                if candidate.exists() and candidate.is_dir():
                    src_folder = candidate
                    break

        if src_folder is None or not src_folder.exists():
            _themed_popup(self.root, "error", "Folder tidak ditemukan",
                f"Folder instalasi MT tidak dapat ditemukan untuk terminal:\n{t['name']}")
            return

        base_name = src_folder.name

        # ── Popup ──────────────────────────────────────────────────────────────
        win = tk.Toplevel(self.root)
        win.title("Duplikat MT")
        win.configure(bg=BG)
        win.resizable(False, False)
        win.attributes("-topmost", True)
        win.update_idletasks()
        rx = self.root.winfo_x() + self.root.winfo_width()  // 2 - 270
        ry = self.root.winfo_y() + self.root.winfo_height() // 2 - 170
        win.geometry(f"540x340+{rx}+{ry}")
        win.deiconify()

        # Header
        hdr = tk.Frame(win, bg=BG2, height=48)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        hdr_inner = tk.Frame(hdr, bg=BG2, padx=20)
        hdr_inner.pack(fill="both", expand=True)
        tk.Label(hdr_inner, text="\u2398  Duplikat MetaTrader",
                 bg=BG2, fg=FG, font=(f, 12, "bold")).pack(side="left", fill="y")
        tk.Frame(win, bg=BORDER, height=1).pack(fill="x")

        body = tk.Frame(win, bg=BG, padx=24, pady=18)
        body.pack(fill="both", expand=True)

        # Info sumber
        tk.Label(body, text="SUMBER",
                 bg=BG, fg=FG3, font=(f, 8), anchor="w").pack(fill="x")
        src_border = tk.Frame(body, bg=BORDER2, padx=1, pady=1)
        src_border.pack(fill="x", pady=(4, 14))
        tk.Label(src_border,
                 text=f"  {t['name']}  [{mt_type}]  \u2192  {src_folder}",
                 bg=BG3, fg=FG2, font=(fm, 9), anchor="w").pack(
                 fill="x", ipady=7, padx=1)

        # Jumlah duplikat
        tk.Label(body, text="JUMLAH DUPLIKAT  (maks. 19)",
                 bg=BG, fg=FG3, font=(f, 8), anchor="w").pack(fill="x")

        qty_row = tk.Frame(body, bg=BG)
        qty_row.pack(fill="x", pady=(4, 6))

        qty_var = tk.IntVar(value=1)

        def _set_qty(v):
            try:
                qty_var.set(max(1, min(19, int(v))))
            except (ValueError, tk.TclError):
                pass

        def _dec(): _set_qty(qty_var.get() - 1)
        def _inc(): _set_qty(qty_var.get() + 1)

        dec_h, _ = make_pill_btn(qty_row, "\u2212", _dec,
                                 bg=BG3, fg=FG, hover_bg=BG4,
                                 font_size=12, padx=10, pady=6, radius=7)
        dec_h.pack(side="left", padx=(0, 6))

        qty_border = tk.Frame(qty_row, bg=BORDER2, padx=1, pady=1)
        qty_border.pack(side="left", padx=(0, 6))
        qty_entry = tk.Entry(
            qty_border, textvariable=qty_var,
            bg=BG3, fg=FG, insertbackground=ACCENT,
            relief="flat", font=(f, 11, "bold"),
            width=4, justify="center", highlightthickness=0,
        )
        qty_entry.pack(ipady=6, padx=1)
        qty_entry.bind("<FocusOut>", lambda _: _set_qty(qty_var.get()))

        inc_h, _ = make_pill_btn(qty_row, "+", _inc,
                                 bg=BG3, fg=FG, hover_bg=BG4,
                                 font_size=12, padx=10, pady=6, radius=7)
        inc_h.pack(side="left")

        # Preview nama folder
        hint_var = tk.StringVar(value="")
        tk.Label(body, textvariable=hint_var,
                 bg=BG, fg=FG3, font=(f, 8), anchor="w",
                 wraplength=480).pack(fill="x", pady=(4, 8))

        def _update_hint(*_):
            q = qty_var.get()
            names = [f"{base_name} {n}" for n in range(2, 2 + q)]
            preview = ", ".join(names[:3])
            if q > 3:
                preview += ", \u2026"
            hint_var.set(f"\u2192 folder: {preview}")

        qty_var.trace_add("write", _update_hint)
        _update_hint()

        # Status
        status_var = tk.StringVar(value="")
        status_lbl = tk.Label(body, textvariable=status_var,
                              bg=BG, fg=FG3, font=(f, 9), anchor="w")
        status_lbl.pack(fill="x")

        # Footer
        tk.Frame(win, bg=BORDER, height=1).pack(fill="x")
        foot = tk.Frame(win, bg=BG2, height=50)
        foot.pack(fill="x")
        foot.pack_propagate(False)
        fi = tk.Frame(foot, bg=BG2, padx=14)
        fi.pack(fill="both", expand=True)

        def _run_duplicate():
            qty = qty_var.get()
            win.destroy()
            self._run_mt_duplicate(src_folder, base_name, linux_base, qty, mt_type)

        run_h, _ = make_pill_btn(fi, "\u2398  Mulai Duplikat", _run_duplicate,
                                 bg="#1a1400", fg=WARN, hover_bg="#2a2000",
                                 font_size=10, padx=20, pady=7, radius=7)
        run_h.pack(side="right", pady=8, padx=(0, 6))

        cancel_h, _ = make_pill_btn(fi, "Batal", win.destroy,
                                    bg=BG3, fg=FG, hover_bg=BG4,
                                    font_size=9, padx=20, pady=6, radius=7)
        cancel_h.pack(side="right", pady=8)

    # ── _run_mt_duplicate ──────────────────────────────────────────────────────
    def _run_mt_duplicate(self, src_folder: Path, base_name: str,
                          linux_base: Path, qty: int, mt_type: str):
        """Copy src_folder ke linux_base/<base_name> 2, 3, … qty+1 di background thread."""
        f = self._font

        win = tk.Toplevel(self.root)
        win.title("Menduplikat MT")
        win.configure(bg=BG)
        win.resizable(False, False)
        win.update_idletasks()
        rx = self.root.winfo_x() + self.root.winfo_width()  // 2 - 240
        ry = self.root.winfo_y() + self.root.winfo_height() // 2 - 120
        win.geometry(f"480x240+{rx}+{ry}")
        win.deiconify()

        body = tk.Frame(win, bg=BG, padx=28, pady=20)
        body.pack(fill="both", expand=True)

        icon_lbl = tk.Label(body, text="\u2398", bg=BG, fg=WARN, font=(f, 22))
        icon_lbl.grid(row=0, column=0, rowspan=3, padx=(0, 16), sticky="n")

        title_lbl = tk.Label(body, text="Memulai duplikat\u2026",
                             bg=BG, fg=FG, font=(f, 11, "bold"), anchor="w")
        title_lbl.grid(row=0, column=1, sticky="w")

        dir_var = tk.StringVar(value="")
        dir_lbl = tk.Label(body, textvariable=dir_var,
                           bg=BG, fg=FG3, font=(f, 8), anchor="w")
        dir_lbl.grid(row=1, column=1, sticky="w", pady=(2, 6))

        prog_frame = tk.Frame(body, bg=BG)
        prog_frame.grid(row=2, column=1, sticky="ew")
        body.columnconfigure(1, weight=1)

        progress = ProgressBar(prog_frame, height=3, bg=BG4, fill=WARN)
        progress.pack(fill="x")

        count_var = tk.StringVar(value=f"0 / {qty}")
        tk.Label(prog_frame, textvariable=count_var,
                 bg=BG, fg=FG3, font=(f, 8)).pack(anchor="e", pady=(3, 0))

        tk.Frame(win, bg=BORDER, height=1).pack(fill="x")
        foot = tk.Frame(win, bg=BG2, height=44)
        foot.pack(fill="x")
        foot.pack_propagate(False)
        fi = tk.Frame(foot, bg=BG2, padx=12)
        fi.pack(fill="both", expand=True)

        close_h, _ = make_pill_btn(fi, "Tutup", win.destroy,
                                   bg=BG3, fg=FG, hover_bg=BG4,
                                   font_size=9, padx=20, pady=6, radius=7)

        _cancelled = [False]

        def _do_cancel():
            _cancelled[0] = True
            icon_lbl.config(text="\u23f9", fg=WARN)
            title_lbl.config(text="Duplikat dibatalkan.", fg=WARN)
            dir_var.set("")
            cancel_h.pack_forget()
            close_h.pack(side="right", pady=8)

        cancel_h, _ = make_pill_btn(fi, "\u2715  Cancel", _do_cancel,
                                    bg="#2a0f0f", fg=DANGER, hover_bg="#3d1212",
                                    font_size=9, padx=20, pady=6, radius=7)
        cancel_h.pack(side="right", pady=8, padx=(0, 6))

        def _do():
            import time
            errors    = []
            done_cnt  = [0]
            launched  = []   # list Path folder yang berhasil dicopy

            # ── Fase 1: Copy ────────────────────────────────────────────────
            for i in range(qty):
                if _cancelled[0]:
                    break
                num      = i + 2
                dst_name = f"{base_name} {num}"
                dst_path = linux_base / dst_name

                def _upd(dn=dst_name, idx=i):
                    title_lbl.config(text=f"Menduplikat {idx + 1} dari {qty}\u2026")
                    count_var.set(f"{idx} / {qty}")
                    progress.set((idx / qty) * 0.5 if qty > 1 else 0.05)
                    dir_var.set(f"\u2192 {dn}")
                win.after(0, _upd)

                try:
                    # Cari nama yang belum ada — tambah suffix jika konflik
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
                    errors.append(f"[{num}] Copy gagal: {e}")

            if _cancelled[0]:
                return

            # ── Fase 2: Launch terminal.exe / terminal64.exe ─────────────
            exe_name = "terminal64.exe" if mt_type == "MT5" else "terminal.exe"
            launch_errors = []

            for j, dst_path in enumerate(launched):
                if _cancelled[0]:
                    break
                exe_path = dst_path / exe_name

                def _upd_launch(dn=dst_path.name, idx=j, total=len(launched)):
                    title_lbl.config(
                        text=f"Menjalankan MT {idx + 1} dari {total}\u2026")
                    count_var.set(f"{idx + 1} / {total}")
                    progress.set(0.5 + (idx / max(total, 1)) * 0.5)
                    dir_var.set(f"\u25b6 {dn}\\{exe_name}")
                win.after(0, _upd_launch)

                if not exe_path.exists():
                    launch_errors.append(
                        f"[{dst_path.name}] {exe_name} tidak ditemukan")
                else:
                    try:
                        subprocess.Popen(
                            ["wine", str(exe_path)],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                        )
                    except Exception as e:
                        launch_errors.append(f"[{dst_path.name}] {e}")

                # Delay 5 detik sebelum launch berikutnya (kecuali yang terakhir)
                if j < len(launched) - 1:
                    for _ in range(50):   # 50 × 0.1s = 5s, bisa dicancel
                        if _cancelled[0]:
                            break
                        time.sleep(0.1)

            all_errors = errors + launch_errors

            def _done():
                if _cancelled[0]:
                    return
                progress.set(1.0)
                count_var.set(f"{done_cnt[0]} / {qty}")
                dir_var.set("")
                if all_errors:
                    icon_lbl.config(text="\u26a0", fg=WARN)
                    title_lbl.config(
                        text=f"Selesai dengan {len(all_errors)} error.", fg=WARN)
                    dir_lbl.config(text="\n".join(all_errors[:3]), fg=DANGER)
                else:
                    icon_lbl.config(text="\u2713", fg=WARN)
                    title_lbl.config(
                        text=f"{done_cnt[0]} duplikat dibuat & dijalankan.", fg=FG)
                    dir_lbl.config(
                        text="Scan otomatis dijalankan.", fg=FG2)
                cancel_h.pack_forget()
                close_h.pack(side="right", pady=8)
                self._status(
                    f"Duplikat MT selesai: {done_cnt[0]}/{qty} dari {src_folder.name}")
                self.root.after(800, self.scan_terminals)

            win.after(0, _done)

        threading.Thread(target=_do, daemon=True).start()
    def _term_yview(self, *args):
        self.term_tree.yview(*args)
        self._draw_as_canvas()

    def _on_side_scroll(self, first, last):
        """Dipanggil saat term_tree scroll — redraw canvas + scrollbar."""
        self._sb_side_ref.set(first, last)
        self._draw_as_canvas()

    def _side_wheel(self, e):
        """Sync wheel scroll di sidebar."""
        delta = -3 if (e.num == 4 or e.delta > 0) else 3
        self.term_tree.yview_scroll(delta, "units")
        self._draw_as_canvas()
        return "break"

    def _file_yview(self, *args):
        """Scroll ketiga treeview (chk + cat + data) bersama."""
        self.chk_tree.yview(*args)
        self.cat_tree.yview(*args)
        self.file_tree.yview(*args)

    def _on_any_scroll(self, first, last):
        """Dipanggil saat salah satu treeview scroll — sync semua + scrollbar."""
        first = float(first)
        self.chk_tree.yview_moveto(first)
        self.cat_tree.yview_moveto(first)
        self.file_tree.yview_moveto(first)
        self._sb_file.set(first, last)

    # aliases agar binding lama tetap valid
    _on_file_scroll = _on_any_scroll
    _on_chk_scroll  = _on_any_scroll
    _on_cat_scroll  = _on_any_scroll

    # ── Handlers ───────────────────────────────────────────────────────────────
    def _on_select(self, _=None):
        t = self._terminal(silent=True)
        if not t:
            return
        self._reload_files(t)
        # update info bar
        self._info_fields["terminal"][0].set(t["name"])
        self._info_fields["type"][0].set(t["type"])
        # warna TYPE: MT4 = hijau (ACCENT3), MT5 = kuning (WARN)
        type_color = ACCENT3 if t["type"] == "MT4" else WARN
        self._info_fields["type"][1].config(fg=type_color)
        # truncate long path for display
        path_str = t["path"]
        home = str(Path.home())
        if path_str.startswith(home):
            path_str = "~" + path_str[len(home):]
        self._info_fields["path"][0].set(path_str)
        self._status(f"Path: {t['path']}")

    def _reload_files(self, t):
        # Hapus semua baris sekaligus — lebih cepat daripada delete per-iid
        for tree in (self.chk_tree, self.cat_tree, self.file_tree):
            tree.delete(*tree.get_children())
        self._checked.clear()
        self._all_checked = False
        self.chk_tree.heading("chk", text=CHK_CHAR_OFF)
        _fmt_date = datetime.datetime.fromtimestamp
        row = 0
        for key, label in (("experts","Expert"),("indicators","Indicator"),
                            ("scripts","Script"),("logs","Log")):
            folder = t.get(key)
            if not (folder and folder.exists()):
                continue
            # Satu os.scandir — lebih cepat dari iterdir() + stat per file
            try:
                entries = sorted(
                    (e for e in folder.iterdir() if e.is_file()),
                    key=lambda e: e.name
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
                mtime = _fmt_date(st.st_mtime).strftime("%Y-%m-%d")
                stripe = "row_even" if row % 2 == 0 else "row_odd"
                iid = f"r{row}"
                self.chk_tree.insert("", "end", iid=iid,
                    values=(CHK_CHAR_OFF,), tags=(stripe,))
                self.cat_tree.insert("", "end", iid=iid,
                    values=(label,), tags=(label, stripe))
                self.file_tree.insert("", "end", iid=iid,
                    values=(f.name, f.suffix.lower(), sz, mtime),
                    tags=(stripe,))
                row += 1

    def _status(self, msg):
        self.status_var.set(msg)

    def _terminal(self, silent=False):
        sel = self.term_tree.selection()
        if not sel:
            if not silent:
                _themed_popup(self.root, "warning", "Perhatian",
                              "Pilih terminal terlebih dahulu.")
            return None
        iid = sel[0]
        item = self.term_tree.item(iid)
        if "group" in item.get("tags", ()):
            if not silent:
                _themed_popup(self.root, "warning", "Perhatian",
                              "Pilih terminal, bukan grup.")
            return None
        t = getattr(self, "_iid_to_terminal", {}).get(iid)
        if t is None:
            return None
        return t

    def _on_chk_click(self, event):
        """Toggle checkbox saat klik di chk_tree."""
        iid = self.chk_tree.identify_row(event.y)
        if iid:
            self._toggle_row(iid)

    def _on_file_click(self, event):
        """Sync selection dari file_tree / cat_tree ke semua tree."""
        widget = event.widget
        iid = widget.identify_row(event.y)
        if iid:
            self.chk_tree.selection_set(iid)
            self.cat_tree.selection_set(iid)
            self.file_tree.selection_set(iid)

    def _toggle_row(self, iid):
        trees = (self.chk_tree, self.cat_tree, self.file_tree)
        if iid in self._checked:
            self._checked.discard(iid)
            self.chk_tree.set(iid, "chk", CHK_CHAR_OFF)
            for tree in trees:
                tree.item(iid, tags=[tg for tg in tree.item(iid, "tags") if tg != "checked"])
        else:
            self._checked.add(iid)
            self.chk_tree.set(iid, "chk", CHK_CHAR_ON)
            for tree in trees:
                cur = tree.item(iid, "tags")
                if "checked" not in cur:
                    tree.item(iid, tags=(*cur, "checked"))
        self._update_header_chk()

    def _toggle_all(self):
        all_iids = self.file_tree.get_children()
        if not all_iids:
            return
        self._all_checked = not self._all_checked
        self.chk_tree.heading("chk", text=CHK_CHAR_ON if self._all_checked else CHK_CHAR_OFF)
        trees = (self.chk_tree, self.cat_tree, self.file_tree)
        if self._all_checked:
            self._checked = set(all_iids)
            for i, iid in enumerate(all_iids):
                self.chk_tree.set(iid, "chk", CHK_CHAR_ON)
                for tree in trees:
                    cur = tree.item(iid, "tags")
                    if "checked" not in cur:
                        tree.item(iid, tags=(*cur, "checked"))
                if i % 60 == 59:
                    self.root.update_idletasks()
        else:
            self._checked.clear()
            for i, iid in enumerate(all_iids):
                self.chk_tree.set(iid, "chk", CHK_CHAR_OFF)
                for tree in trees:
                    tree.item(iid, tags=[tg for tg in tree.item(iid, "tags") if tg != "checked"])
                if i % 60 == 59:
                    self.root.update_idletasks()

    def _update_header_chk(self):
        all_iids = self.file_tree.get_children()
        if all_iids and len(self._checked) == len(all_iids):
            self._all_checked = True
            self.chk_tree.heading("chk", text=CHK_CHAR_ON)
        else:
            self._all_checked = False
            self.chk_tree.heading("chk", text=CHK_CHAR_OFF)

    def _file_info(self):
        sel = self.file_tree.selection()
        if not sel:
            return None, None
        iid = sel[0]
        v   = self.file_tree.item(iid, "values")
        # file_tree values: (name[0], type[1], size[2], modified[3])
        # kategori diambil dari cat_tree
        cat = self.cat_tree.item(iid, "values")[0] if self.cat_tree.exists(iid) else None
        return cat, v[0]   # category, filename

    def _folder_for(self, t, label):
        return t.get({"Expert":"experts","Indicator":"indicators",
                      "Script":"scripts","Log":"logs"}.get(label,"experts"))

    # ── Install ────────────────────────────────────────────────────────────────
    def _install(self, key, label):
        t = self._terminal()
        if not t:
            return
        DOCS_DIR.mkdir(exist_ok=True)
        fp = yad_pick_file(title=f"Pilih file {label}",
                           filetypes=["*.ex4","*.ex5","*.mq4","*.mq5"],
                           start_dir=DOCS_DIR,
                           root_widget=self.root)
        if not fp:
            return
        dst = t[key]
        dst.mkdir(parents=True, exist_ok=True)
        dest = dst / Path(fp).name
        shutil.copy(fp, dest)
        self._reload_files(t)
        self._status(f"'{dest.name}' berhasil diinstall \u2192 {dst}")
        # ── Popup hasil install EA/Indicator ─────────────────────────
        _f = self._font
        _fm = self._font_mono
        res = tk.Toplevel(self.root)
        res.title("Install Berhasil"); res.configure(bg=BG)
        res.resizable(False, False); res.attributes("-topmost", True)
        hdr_r = tk.Frame(res, bg=BG2, height=48)
        hdr_r.pack(fill="x"); hdr_r.pack_propagate(False)
        hdr_ri = tk.Frame(hdr_r, bg=BG2, padx=20)
        hdr_ri.pack(fill="both", expand=True)
        tk.Label(hdr_ri, text="\u2713  Install Berhasil",
                 bg=BG2, fg="#5ecf3e", font=(_f, 12, "bold")).pack(side="left", fill="y")
        tk.Frame(res, bg=BORDER, height=1).pack(fill="x")
        body_r = tk.Frame(res, bg=BG, padx=24, pady=18)
        body_r.pack(fill="both", expand=True)
        ico = tk.Label(body_r, text="\u2713", bg=BG, fg="#5ecf3e", font=(_f, 22))
        ico.grid(row=0, column=0, rowspan=2, padx=(0, 16), sticky="n")
        tk.Label(body_r, text=f"{label} berhasil diinstall.",
                 bg=BG, fg=FG, font=(_f, 11, "bold"), anchor="w").grid(row=0, column=1, sticky="w")
        tk.Label(body_r, text=str(dst),
                 bg=BG, fg=FG3, font=(_fm, 8), anchor="w", wraplength=340).grid(
                 row=1, column=1, sticky="w", pady=(4, 0))
        body_r.columnconfigure(1, weight=1)
        tk.Frame(res, bg=BORDER, height=1).pack(fill="x")
        foot_r = tk.Frame(res, bg=BG2, height=44); foot_r.pack(fill="x")
        foot_r.pack_propagate(False)
        fi_r = tk.Frame(foot_r, bg=BG2, padx=12); fi_r.pack(fill="both", expand=True)
        oh_r, _ = make_pill_btn(fi_r, "OK", res.destroy,
                                bg=BG3, fg=FG, hover_bg=BG4,
                                font_size=9, padx=20, pady=6, radius=7)
        oh_r.pack(side="right", pady=8)
        res.update_idletasks()
        _rx = self.root.winfo_x() + self.root.winfo_width()  // 2 - res.winfo_reqwidth()  // 2
        _ry = self.root.winfo_y() + self.root.winfo_height() // 2 - res.winfo_reqheight() // 2
        res.geometry(f"+{_rx}+{_ry}"); res.deiconify(); res.lift(); res.focus_force()

    def install_ea(self):
        self._install("experts", "EA")

    def install_indicator(self):
        self._install("indicators", "Indicator")

    # ── Uninstall ──────────────────────────────────────────────────────────────
    def uninstall_file(self):
        t = self._terminal()
        if not t:
            return
        f  = self._font
        fm = self._font_mono

        def _confirm_delete_popup(title, items_label, item_count, detail_lines, on_confirm):
            dlg = tk.Toplevel(self.root)
            dlg.title(title); dlg.configure(bg=BG)
            dlg.resizable(False, False); dlg.attributes("-topmost", True)
            hdr = tk.Frame(dlg, bg=BG2, height=48)
            hdr.pack(fill="x"); hdr.pack_propagate(False)
            hdr_inner = tk.Frame(hdr, bg=BG2, padx=20)
            hdr_inner.pack(fill="both", expand=True)
            tk.Label(hdr_inner, text=f"\u232b  {title}",
                     bg=BG2, fg=DANGER, font=(f, 12, "bold")).pack(side="left", fill="y")
            tk.Frame(dlg, bg=BORDER, height=1).pack(fill="x")
            body = tk.Frame(dlg, bg=BG, padx=24, pady=18)
            body.pack(fill="both", expand=True)
            info_box = tk.Frame(body, bg=BG3, padx=14, pady=10)
            info_box.pack(fill="x", pady=(0, 10))
            tk.Label(info_box, text=items_label, bg=BG3, fg=FG2,
                     font=(f, 10, "bold"), anchor="w").pack(anchor="w", pady=(0, 6))
            for line in detail_lines[:8]:
                tk.Label(info_box, text=f"  {line}", bg=BG3, fg=FG3,
                         font=(fm, 8), anchor="w").pack(anchor="w")
            if len(detail_lines) > 8:
                tk.Label(info_box, text=f"  \u2026 dan {len(detail_lines)-8} file lainnya",
                         bg=BG3, fg=FG3, font=(f, 8), anchor="w").pack(anchor="w")
            tk.Label(body, text="Tindakan ini tidak dapat dibatalkan.",
                     bg=BG, fg=FG2, font=(f, 9), anchor="w").pack(anchor="w", pady=(0, 4))
            tk.Frame(dlg, bg=BORDER, height=1).pack(fill="x")
            foot = tk.Frame(dlg, bg=BG2, height=50); foot.pack(fill="x")
            foot.pack_propagate(False)
            fi_f = tk.Frame(foot, bg=BG2, padx=14); fi_f.pack(fill="both", expand=True)
            def _do():
                dlg.destroy()
                on_confirm()
            del_h, _ = make_pill_btn(fi_f, f"\u232b  Hapus {item_count} File", _do,
                                     bg="#2a0f0f", fg=DANGER, hover_bg="#3d1212",
                                     font_size=10, padx=20, pady=7, radius=7)
            del_h.pack(side="right", pady=8, padx=(0, 6))
            can_h, _ = make_pill_btn(fi_f, "Batal", dlg.destroy,
                                     bg=BG3, fg=FG, hover_bg=BG4,
                                     font_size=9, padx=20, pady=6, radius=7)
            can_h.pack(side="right", pady=8)
            dlg.update_idletasks()
            rx = self.root.winfo_x() + self.root.winfo_width()  // 2 - dlg.winfo_reqwidth()  // 2
            ry = self.root.winfo_y() + self.root.winfo_height() // 2 - dlg.winfo_reqheight() // 2
            dlg.geometry(f"+{rx}+{ry}"); dlg.deiconify(); dlg.lift(); dlg.focus_force()

        def _result_popup(deleted, errors):
            res = tk.Toplevel(self.root)
            res.title("File Dihapus"); res.configure(bg=BG)
            res.resizable(False, False); res.attributes("-topmost", True)
            ok_icon = "\u2713" if not errors else "\u26a0"
            ok_fg   = "#5ecf3e" if not errors else WARN
            hdr2 = tk.Frame(res, bg=BG2, height=48)
            hdr2.pack(fill="x"); hdr2.pack_propagate(False)
            hdr2i = tk.Frame(hdr2, bg=BG2, padx=20)
            hdr2i.pack(fill="both", expand=True)
            tk.Label(hdr2i, text=f"{ok_icon}  File Dihapus",
                     bg=BG2, fg=ok_fg, font=(f, 12, "bold")).pack(side="left", fill="y")
            tk.Frame(res, bg=BORDER, height=1).pack(fill="x")
            body2 = tk.Frame(res, bg=BG, padx=24, pady=18)
            body2.pack(fill="both", expand=True)
            icon_lbl = tk.Label(body2, text=ok_icon, bg=BG, fg=ok_fg, font=(f, 22))
            icon_lbl.grid(row=0, column=0, rowspan=2, padx=(0, 16), sticky="n")
            tk.Label(body2, text=f"{deleted} file berhasil dihapus.",
                     bg=BG, fg=FG, font=(f, 11, "bold"), anchor="w").grid(row=0, column=1, sticky="w")
            if errors:
                tk.Label(body2, text="\n".join(errors[:3]),
                         bg=BG, fg=DANGER, font=(f, 9), anchor="w", wraplength=340).grid(
                         row=1, column=1, sticky="w", pady=(4, 0))
            body2.columnconfigure(1, weight=1)
            tk.Frame(res, bg=BORDER, height=1).pack(fill="x")
            foot2 = tk.Frame(res, bg=BG2, height=44); foot2.pack(fill="x")
            foot2.pack_propagate(False)
            fi2 = tk.Frame(foot2, bg=BG2, padx=12); fi2.pack(fill="both", expand=True)
            oh, _ = make_pill_btn(fi2, "OK", res.destroy,
                                  bg=BG3, fg=FG, hover_bg=BG4,
                                  font_size=9, padx=20, pady=6, radius=7)
            oh.pack(side="right", pady=8)
            res.update_idletasks()
            rx2 = self.root.winfo_x() + self.root.winfo_width()  // 2 - res.winfo_reqwidth()  // 2
            ry2 = self.root.winfo_y() + self.root.winfo_height() // 2 - res.winfo_reqheight() // 2
            res.geometry(f"+{rx2}+{ry2}"); res.deiconify(); res.lift(); res.focus_force()

        # ── Multi-delete ──────────────────────────────────────────────────
        if self._checked:
            targets = []
            for iid in list(self._checked):
                try:
                    v     = self.file_tree.item(iid, "values")
                    fname = v[0]
                    cat   = self.cat_tree.item(iid, "values")[0]
                    path  = self._folder_for(t, cat) / fname
                    targets.append((fname, path))
                except Exception:
                    pass
            if not targets:
                self._status("Perhatian: file yang dipilih tidak valid.")
                return
            def _do_multi():
                deleted, errors = 0, []
                for fname, path in targets:
                    try:
                        if path.exists():
                            path.unlink(); deleted += 1
                        else:
                            errors.append(f"{fname}: tidak ditemukan")
                    except Exception as e:
                        errors.append(f"{fname}: {e}")
                self._reload_files(t)
                self._status(f"{deleted} file dihapus.")
                _result_popup(deleted, errors)
            _confirm_delete_popup(
                "Konfirmasi Hapus",
                f"Hapus {len(targets)} file berikut?",
                len(targets),
                [n for n, _ in targets],
                _do_multi,
            )
            return

        # ── Single-delete ─────────────────────────────────────────────────
        cat, fname = self._file_info()
        if not fname:
            self._status("Centang file yang ingin dihapus, atau pilih satu baris dari tabel.")
            return
        target = self._folder_for(t, cat) / fname
        if not target.exists():
            self._status(f"File tidak ditemukan: {target}")
            return
        def _do_single():
            target.unlink()
            self._reload_files(t)
            self._status(f"\'{fname}\' dihapus.")
        _confirm_delete_popup(
            "Konfirmasi Hapus", "Hapus file ini?", 1, [str(target)], _do_single)


    # ── Clear Logs ─────────────────────────────────────────────────────────────
    def clear_logs(self):
        t = self._terminal()
        if not t:
            return
        f  = self._font
        fm = self._font_mono
        logs_dir = t.get("logs")

        # ── Helper: popup info ringan (tanpa tombol konfirmasi) ──────────
        def _info_popup(title, msg, icon="\u2139", icon_fg=ACCENT):
            w = tk.Toplevel(self.root)
            w.title(title)
            w.configure(bg=BG)
            w.resizable(False, False)
            w.attributes("-topmost", True)
            hdr = tk.Frame(w, bg=BG2, height=48)
            hdr.pack(fill="x"); hdr.pack_propagate(False)
            tk.Label(tk.Frame(hdr, bg=BG2, padx=20),
                     text=f"{icon}  {title}", bg=BG2, fg=FG,
                     font=(f, 12, "bold")).pack(side="left", fill="y")
            list(hdr.winfo_children())[0].pack(fill="both", expand=True)
            tk.Frame(w, bg=BORDER, height=1).pack(fill="x")
            body = tk.Frame(w, bg=BG, padx=24, pady=18)
            body.pack(fill="both", expand=True)
            tk.Label(body, text=msg, bg=BG, fg=FG2, font=(f, 10),
                     justify="left", anchor="w", wraplength=380).pack(anchor="w")
            tk.Frame(w, bg=BORDER, height=1).pack(fill="x")
            foot = tk.Frame(w, bg=BG2, height=44); foot.pack(fill="x")
            foot.pack_propagate(False)
            fi = tk.Frame(foot, bg=BG2, padx=12); fi.pack(fill="both", expand=True)
            oh, _ = make_pill_btn(fi, "OK", w.destroy,
                                  bg=BG3, fg=FG, hover_bg=BG4,
                                  font_size=9, padx=20, pady=6, radius=7)
            oh.pack(side="right", pady=8)
            w.update_idletasks()
            rx = self.root.winfo_x() + self.root.winfo_width()  // 2 - w.winfo_reqwidth()  // 2
            ry = self.root.winfo_y() + self.root.winfo_height() // 2 - w.winfo_reqheight() // 2
            w.geometry(f"+{rx}+{ry}"); w.deiconify(); w.lift(); w.focus_force()

        if not logs_dir or not logs_dir.exists():
            _info_popup("Logs Tidak Ditemukan",
                f"Folder logs tidak ditemukan:\n{logs_dir}\n\n"
                "Pastikan MT pernah dijalankan minimal sekali.",
                icon="\u26a0", icon_fg=WARN)
            return

        log_files = [lf for lf in logs_dir.iterdir() if lf.is_file()]
        if not log_files:
            _info_popup("Logs Kosong", "Tidak ada file log di terminal ini.",
                        icon="\u2139", icon_fg=ACCENT)
            return

        total_kb  = sum(lf.stat().st_size for lf in log_files) / 1024
        total_str = f"{total_kb:.1f} KB" if total_kb < 1024 else f"{total_kb/1024:.2f} MB"

        # ── Popup konfirmasi custom ───────────────────────────────────────
        dlg = tk.Toplevel(self.root)
        dlg.title("Hapus Logs")
        dlg.configure(bg=BG)
        dlg.resizable(False, False)
        dlg.attributes("-topmost", True)

        # Header
        hdr = tk.Frame(dlg, bg=BG2, height=48)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        hdr_inner = tk.Frame(hdr, bg=BG2, padx=20)
        hdr_inner.pack(fill="both", expand=True)
        tk.Label(hdr_inner, text="\u2015  Hapus Logs",
                 bg=BG2, fg=WARN, font=(f, 12, "bold")).pack(side="left", fill="y")
        tk.Frame(dlg, bg=BORDER, height=1).pack(fill="x")

        body = tk.Frame(dlg, bg=BG, padx=24, pady=18)
        body.pack(fill="both", expand=True)

        # Info box
        info_box = tk.Frame(body, bg=BG3, padx=14, pady=10)
        info_box.pack(fill="x", pady=(0, 14))
        rows = [
            ("Terminal",   f"{t['type']} — {t['name']}"),
            ("Folder",     str(logs_dir)),
            ("Jumlah",     f"{len(log_files)} file"),
            ("Total size", total_str),
        ]
        for label, val in rows:
            row = tk.Frame(info_box, bg=BG3)
            row.pack(fill="x", pady=1)
            tk.Label(row, text=f"{label:<12}", bg=BG3, fg=FG3,
                     font=(f, 9), anchor="w", width=12).pack(side="left")
            tk.Label(row, text=val, bg=BG3, fg=FG2,
                     font=(fm, 9), anchor="w").pack(side="left")

        tk.Label(body,
                 text="Semua file log akan dihapus permanen.\nTindakan ini tidak dapat dibatalkan.",
                 bg=BG, fg=FG2, font=(f, 9), justify="left",
                 anchor="w").pack(anchor="w", pady=(0, 4))

        # Footer
        tk.Frame(dlg, bg=BORDER, height=1).pack(fill="x")
        foot = tk.Frame(dlg, bg=BG2, height=50); foot.pack(fill="x")
        foot.pack_propagate(False)
        fi = tk.Frame(foot, bg=BG2, padx=14); fi.pack(fill="both", expand=True)

        def _confirm():
            dlg.destroy()
            deleted, errors = 0, []
            for lf in log_files:
                try:
                    lf.unlink(); deleted += 1
                except Exception as e:
                    errors.append(f"{lf.name}: {e}")
            t_ref = self._terminal(silent=True)
            if t_ref:
                self._reload_files(t_ref)
            self._status(f"{deleted} file log dihapus dari {t['name']}.")

            # ── Popup hasil ──────────────────────────────────────────────
            res = tk.Toplevel(self.root)
            res.title("Logs Dihapus")
            res.configure(bg=BG)
            res.resizable(False, False)
            res.attributes("-topmost", True)
            hdr2 = tk.Frame(res, bg=BG2, height=48)
            hdr2.pack(fill="x"); hdr2.pack_propagate(False)
            hdr2i = tk.Frame(hdr2, bg=BG2, padx=20)
            hdr2i.pack(fill="both", expand=True)
            ok_icon = "\u2713" if not errors else "\u26a0"
            ok_fg   = "#5ecf3e" if not errors else WARN
            tk.Label(hdr2i, text=f"{ok_icon}  Logs Dihapus",
                     bg=BG2, fg=ok_fg, font=(f, 12, "bold")).pack(side="left", fill="y")
            tk.Frame(res, bg=BORDER, height=1).pack(fill="x")
            body2 = tk.Frame(res, bg=BG, padx=24, pady=18)
            body2.pack(fill="both", expand=True)

            icon_lbl = tk.Label(body2, text=ok_icon, bg=BG, fg=ok_fg, font=(f, 22))
            icon_lbl.grid(row=0, column=0, rowspan=2, padx=(0, 16), sticky="n")
            msg_text = f"{deleted} file log berhasil dihapus."
            tk.Label(body2, text=msg_text, bg=BG, fg=FG,
                     font=(f, 11, "bold"), anchor="w").grid(row=0, column=1, sticky="w")
            err_text = ("\n".join(errors[:3]) if errors
                        else f"Dari terminal: {t['name']}")
            tk.Label(body2, text=err_text, bg=BG, fg=FG2 if not errors else DANGER,
                     font=(f, 9), anchor="w", wraplength=340).grid(
                     row=1, column=1, sticky="w", pady=(4, 0))
            body2.columnconfigure(1, weight=1)

            tk.Frame(res, bg=BORDER, height=1).pack(fill="x")
            foot2 = tk.Frame(res, bg=BG2, height=44); foot2.pack(fill="x")
            foot2.pack_propagate(False)
            fi2 = tk.Frame(foot2, bg=BG2, padx=12); fi2.pack(fill="both", expand=True)
            oh, _ = make_pill_btn(fi2, "OK", res.destroy,
                                  bg=BG3, fg=FG, hover_bg=BG4,
                                  font_size=9, padx=20, pady=6, radius=7)
            oh.pack(side="right", pady=8)
            res.update_idletasks()
            rx2 = self.root.winfo_x() + self.root.winfo_width()  // 2 - res.winfo_reqwidth()  // 2
            ry2 = self.root.winfo_y() + self.root.winfo_height() // 2 - res.winfo_reqheight() // 2
            res.geometry(f"+{rx2}+{ry2}"); res.deiconify(); res.lift(); res.focus_force()

        confirm_h, _ = make_pill_btn(fi, "\u2015  Hapus Semua Log", _confirm,
                                     bg="#261a05", fg=WARN, hover_bg="#3d2a08",
                                     font_size=10, padx=20, pady=7, radius=7)
        confirm_h.pack(side="right", pady=8, padx=(0, 6))
        cancel_h, _ = make_pill_btn(fi, "Batal", dlg.destroy,
                                    bg=BG3, fg=FG, hover_bg=BG4,
                                    font_size=9, padx=20, pady=6, radius=7)
        cancel_h.pack(side="right", pady=8)

        dlg.update_idletasks()
        rx = self.root.winfo_x() + self.root.winfo_width()  // 2 - dlg.winfo_reqwidth()  // 2
        ry = self.root.winfo_y() + self.root.winfo_height() // 2 - dlg.winfo_reqheight() // 2
        dlg.geometry(f"+{rx}+{ry}"); dlg.deiconify(); dlg.lift(); dlg.focus_force()

    # ── Browse ─────────────────────────────────────────────────────────────────
    def browse_files(self):
        t = self._terminal()
        if not t:
            return
        target = Path(t["path"])
        try:
            if shutil.which("pcmanfm"):
                subprocess.Popen(["pcmanfm", str(target)])
            elif shutil.which("xdg-open"):
                subprocess.Popen(["xdg-open", str(target)])
            else:
                _themed_popup(self.root, "info", "Path Terminal", str(target))
        except Exception as e:
            _themed_popup(self.root, "error", "Error", str(e))

    # ── wget Download ──────────────────────────────────────────────────────────
    def wget_download(self):
        if not shutil.which("wget"):
            _themed_popup(self.root, "error", "wget tidak ditemukan",
                "wget belum terinstall.\n\nJalankan:\n  sudo apt install wget")
            return
        PLACEHOLDER = self._wget_placeholder
        raw = self.wget_var.get().strip()
        if not raw or raw == PLACEHOLDER or raw == PLACEHOLDER.strip():
            self.wget_status_var.set("Paste URL dulu.")
            return
        url_match = re.search(r"https?://[^\s\"']+", raw)
        if not url_match:
            self.wget_status_var.set("URL tidak ditemukan.")
            return
        url = url_match.group(0).strip("\"' ")
        DOCS_DIR.mkdir(exist_ok=True)
        self.wget_status_var.set("Mengunduh\u2026")
        self._wget_pct_var.set("")
        self._progress.set(0.0)

        auto_extract = self.auto_extract_var.get()

        def _run():
            try:
                result = subprocess.run(
                    ["wget", "-P", str(DOCS_DIR), "--content-disposition", url],
                    capture_output=True, text=True, timeout=120,
                )
                if result.returncode != 0:
                    err_lines = result.stderr.strip().splitlines()
                    err = err_lines[-1] if err_lines else "Unknown error"
                    self.root.after(0, lambda: (
                        self.wget_status_var.set(f"Gagal: {err[:55]}"),
                        self._progress.set(0.0),
                    ))
                    return
                files_after = sorted(DOCS_DIR.iterdir(),
                                      key=lambda f: f.stat().st_mtime, reverse=True)
                downloaded = next((f for f in files_after if f.is_file()), None)

                def _finish():
                    self.wget_var.set("")
                    self._progress.set(1.0)
                    self._wget_pct_var.set("100%")
                    if downloaded and auto_extract and is_archive(downloaded):
                        self.wget_status_var.set(f"Mengekstrak {downloaded.name}\u2026")
                        ok, msg = extract_file(downloaded, DOCS_DIR)
                        if ok:
                            self.wget_status_var.set("Selesai + diekstrak \u2192 Documents/")
                            self._status(f"wget + ekstrak selesai: {downloaded.name}")
                            _themed_popup(self.root, "success", "Selesai",
                                f"File diunduh dan diekstrak ke:\n{DOCS_DIR}\n\nFile: {downloaded.name}")
                        else:
                            self.wget_status_var.set("Unduh OK, ekstrak gagal.")
                            _themed_popup(self.root, "warning", "Ekstrak Gagal",
                                f"File berhasil diunduh ke {DOCS_DIR}\n\nTapi ekstrak gagal:\n{msg}")
                    else:
                        fname = downloaded.name if downloaded else ""
                        self.wget_status_var.set(f"Selesai \u2192 Documents/{fname}")
                        self._status(f"wget selesai \u2192 {DOCS_DIR}")
                        _themed_popup(self.root, "success", "Download Selesai",
                            f"File berhasil diunduh ke:\n{DOCS_DIR}")

                self.root.after(0, _finish)
            except subprocess.TimeoutExpired:
                self.root.after(0, lambda: self.wget_status_var.set("Timeout \u2014 >120 detik."))
            except Exception as e:
                self.root.after(0, lambda: self.wget_status_var.set(f"Error: {e}"))

        threading.Thread(target=_run, daemon=True).start()

    # ── Scan ───────────────────────────────────────────────────────────────────
    # ── AutoStart helpers ─────────────────────────────────────────────────────
    def _autostart_desktop_path(self, t: dict) -> Path:
        safe = t["name"].replace(" ", "_").replace("/", "_")
        return AUTOSTART_DIR / f"{safe}.desktop"

    def _autostart_is_on(self, t: dict) -> bool:
        return self._autostart_desktop_path(t).exists()

    def _autostart_set(self, t: dict, enable: bool) -> bool:
        dst = self._autostart_desktop_path(t)
        if enable:
            AUTOSTART_DIR.mkdir(parents=True, exist_ok=True)
            exe = self._find_exe(t, "terminal.exe", "terminal64.exe")
            if exe is None:
                _themed_popup(self.root, "error", "Autostart Gagal",
                    f"File terminal.exe / terminal64.exe tidak ditemukan\n"
                    f"untuk {t['name']} ({t['type']}).\n\nAutostart tidak dapat dibuat.")
                return False
            dst.write_text(
                "[Desktop Entry]\n"
                "Type=Application\n"
                f"Name={t['name']}\n"
                f"Exec=wine \"{exe}\"\n"
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

    # ── Canvas slider drawing ──────────────────────────────────────────────────
    def _draw_as_canvas(self):
        """Render semua slider pill (debounced, cached rows, polygon pill)."""
        # Debounce: batalkan jadwal sebelumnya
        if getattr(self, "_as_draw_id", None):
            self._as_canvas.after_cancel(self._as_draw_id)
        self._as_draw_id = self._as_canvas.after(8, self._do_draw_as_canvas)

    def _do_draw_as_canvas(self):
        self._as_draw_id = None
        c  = self._as_canvas
        cw = c.winfo_width()
        ch = c.winfo_height()
        if cw < 4 or ch < 4:
            return
        c.delete("all")
        rh      = 44
        iid_map = getattr(self, "_iid_to_terminal", {})
        # Pakai cache dari scan — tidak memanggil get_children() setiap frame
        all_rows = getattr(self, "_all_term_rows", None) or self.term_tree.get_children()
        if not all_rows:
            return
        yview        = self.term_tree.yview()
        scroll_offset = int(yview[0] * len(all_rows) * rh)
        cx    = cw // 2
        tw    = AS_TRACK_W
        th    = AS_TRACK_H
        tr    = th >> 1          # th // 2, bitshift lebih cepat
        thumb_r = AS_THUMB_R
        hover = getattr(self, "_as_hover_iid", None)
        # Pre-compute x coords (sama untuk semua baris)
        tx1 = cx - (tw >> 1)
        tx2 = cx + (tw >> 1)
        # Pre-compute autostart state cache untuk batch ini (hindari Path.exists per frame)
        as_cache = self._as_state_cache

        for idx, iid in enumerate(all_rows):
            if iid not in iid_map:
                continue   # grup header
            y_center = idx * rh + (rh >> 1) - scroll_offset
            if y_center < -rh or y_center > ch + rh:
                continue
            on = as_cache.get(iid)
            if on is None:       # cache miss — baca filesystem
                on = self._autostart_is_on(iid_map[iid])
                as_cache[iid] = on
            is_hover  = (iid == hover)
            ty1 = y_center - (th >> 1)
            ty2 = y_center + (th >> 1)
            track_col = (AS_COLOR_ON if on else AS_COLOR_OFF)
            if is_hover:
                track_col = "#00e6ac" if on else "#3a5570"
            # Pill track: 1 polygon (8 titik) menggantikan 3 arc/rect panggilan
            r   = tr
            pts = [tx1+r, ty1,  tx2-r, ty1,
                   tx2,   ty1,  tx2,   ty1+r,
                   tx2,   ty2-r, tx2,  ty2,
                   tx2-r, ty2,  tx1+r, ty2,
                   tx1,   ty2,  tx1,   ty2-r,
                   tx1,   ty1+r, tx1,  ty1,
                   tx1+r, ty1]
            c.create_polygon(pts, smooth=True, fill=track_col, outline="")
            # Thumb
            thumb_cx = (tx2 - r) if on else (tx1 + r)
            c.create_oval(
                thumb_cx - thumb_r, y_center - thumb_r,
                thumb_cx + thumb_r, y_center + thumb_r,
                fill=AS_THUMB_COL, outline="",
            )

    def _as_y_to_iid(self, y: int):
        """Konversi koordinat y di canvas ke iid terminal (atau None jika grup/miss)."""
        rh       = 44
        all_rows = getattr(self, "_all_term_rows", None) or self.term_tree.get_children()
        if not all_rows:
            return None
        yview        = self.term_tree.yview()
        scroll_offset = int(yview[0] * len(all_rows) * rh)
        idx = (y + scroll_offset) // rh
        if idx < 0 or idx >= len(all_rows):
            return None
        iid = all_rows[idx]
        return iid if iid in getattr(self, "_iid_to_terminal", {}) else None

    def _on_as_click(self, event):
        """Toggle autostart saat slider diklik."""
        iid = self._as_y_to_iid(event.y)
        if iid is None:
            return
        t = self._iid_to_terminal[iid]
        new_state = not self._autostart_is_on(t)
        ok = self._autostart_set(t, new_state)
        if new_state and not ok:
            return
        # Invalidate cache untuk baris ini saja
        self._as_state_cache[iid] = new_state
        self._draw_as_canvas()
        self._status(f"Autostart {t['name']} → {'ON' if new_state else 'OFF'}")

    def _on_as_motion(self, event):
        """Hover highlight + tooltip."""
        iid = self._as_y_to_iid(event.y)
        if iid != self._as_hover_iid:
            self._as_hover_iid = iid
            self._draw_as_canvas()
            self._as_cancel_tooltip()
            if iid is not None:
                self._as_tooltip_id = self._as_canvas.after(
                    280, lambda: self._as_show_tooltip(event.x_root, event.y_root)
                )

    def _on_as_leave(self, _=None):
        if self._as_hover_iid is not None:
            self._as_hover_iid = None
            self._draw_as_canvas()
        self._as_cancel_tooltip()

    def _as_cancel_tooltip(self):
        if self._as_tooltip_id:
            self._as_canvas.after_cancel(self._as_tooltip_id)
            self._as_tooltip_id = None
        if self._as_tooltip_win:
            try:
                self._as_tooltip_win.destroy()
            except Exception:
                pass
            self._as_tooltip_win = None

    def _as_show_tooltip(self, rx, ry):
        """Tampilkan tooltip autostart."""
        if self._as_tooltip_win:
            return
        tw = tk.Toplevel(self.root)
        tw.wm_overrideredirect(True)
        tw.configure(bg=BORDER2)
        tw.attributes("-topmost", True)
        outer = tk.Frame(tw, bg=BORDER2, padx=1, pady=1)
        outer.pack()
        inner = tk.Frame(outer, bg=BG3, padx=12, pady=7)
        inner.pack()
        f = self._font
        tk.Label(inner, text="Aktifkan/Nonaktifkan autostart MT saat VPS restart",
                 bg=BG3, fg=FG2, font=(f, 9), wraplength=260, justify="left").pack()
        tw.update_idletasks()
        tw_ = tw.winfo_reqwidth()
        th_ = tw.winfo_reqheight()
        x   = rx + 14
        y   = ry + 18
        sw  = tw.winfo_screenwidth()
        sh  = tw.winfo_screenheight()
        if x + tw_ > sw: x = rx - tw_ - 6
        if y + th_ > sh: y = ry - th_ - 6
        tw.wm_geometry(f"+{x}+{y}")
        self._as_tooltip_win = tw

    def _refresh_as_canvas(self):
        """Alias publik — redraw canvas setelah scan."""
        self._draw_as_canvas()

    def scan_terminals(self, silent=False):
        self.term_tree.delete(*self.term_tree.get_children())
        self.file_tree.delete(*self.file_tree.get_children())
        self.terminals.clear()
        self._as_state_cache.clear()
        home = Path.home()

        for base in [home / ".wine/drive_c/Program Files",
                     home / ".wine/drive_c/Program Files (x86)"]:
            if not base.exists():
                continue
            for exe in base.rglob("terminal64.exe"):
                mt_dir = exe.parent
                mql5 = mt_dir / "MQL5"
                if mql5.exists():
                    self.terminals.append({
                        "type": "MT5", "name": mt_dir.name, "path": str(mt_dir),
                        "experts": mql5 / "Experts", "indicators": mql5 / "Indicators",
                        "scripts": mql5 / "Scripts",  "logs": mt_dir / "logs",
                    })

        def _parse_origin(folder):
            """Baca origin.txt SEKALI → return (name, install_path).  Sebelumnya dibaca 2x."""
            origin = folder / "origin.txt"
            if not origin.exists():
                return folder.name[:22], None
            try:
                raw_bytes = origin.read_bytes()
            except OSError:
                return folder.name[:22], None
            # Decode dengan beberapa encoding
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
            # Baris pertama = path Windows instalasi
            line = raw.splitlines()[0].strip()
            # Nama folder dari bagian akhir path
            name = (line.replace("\\", "/").rstrip("/").split("/")[-1].strip()
                    or folder.name[:22])
            # Konversi ke path Linux/Wine
            install = None
            try:
                wp = line.replace("\\", "/").strip().rstrip("/")
                if len(wp) >= 3 and wp[1] == ":":
                    wp = wp[3:]
                if wp:
                    _h = Path.home()
                    for wc in (_h / ".wine/drive_c", _h / "Games/drive_c"):
                        c = wc / wp
                        if c.exists():
                            install = c; break
            except Exception:
                pass
            return name, install

        users_dir = home / ".wine/drive_c/users"
        if users_dir.exists():
            for userdir in users_dir.iterdir():
                tb = userdir / "AppData/Roaming/MetaQuotes/Terminal"
                if not tb.exists():
                    continue
                for folder in tb.iterdir():
                    mql4 = folder / "MQL4"
                    if mql4.exists():
                        _n4, _ip4 = _parse_origin(folder)
                        self.terminals.append({
                            "type": "MT4", "name": _n4, "path": str(folder),
                            "install_path": _ip4,
                            "experts": mql4 / "Experts", "indicators": mql4 / "Indicators",
                            "scripts": mql4 / "Scripts",  "logs": folder / "logs",
                        })

        def _nat_key(item):
            parts = re.split(r"(\d+)", item["name"].lower())
            return [int(p) if p.isdigit() else p for p in parts]

        self.terminals.sort(key=lambda x: (0 if x["type"] == "MT4" else 1, _nat_key(x)))

        # Insert into sidebar treeview with group headers
        f = self._font
        cur_type = None
        self._iid_to_terminal = {}
        for item in self.terminals:
            if item["type"] != cur_type:
                cur_type = item["type"]
                label = f"METATRADER {'4' if cur_type == 'MT4' else '5'}"
                self.term_tree.insert("", "end",
                    values=("", label, ""),
                    tags=("group",))
            iid = self.term_tree.insert("", "end",
                values=("MT4" if item["type"] == "MT4" else "MT5",
                    item["name"],
                    item["type"]),
                tags=(item["type"],))
            self._iid_to_terminal[iid] = item
        # Cache urutan baris untuk _draw_as_canvas + _as_y_to_iid
        self._all_term_rows = self.term_tree.get_children()
        # Redraw slider canvas setelah semua baris diisi
        self.root.after(50, self._draw_as_canvas)

        n = len(self.terminals)
        if hasattr(self, "_term_count_var"):
            self._term_count_var.set(f"{n} terminal terdeteksi")
        self._status(f"{n} terminal ditemukan.")


if __name__ == "__main__":
    root = tk.Tk()
    try:
        _icon_path = Path(__file__).parent / "mt_manager.png"
        _icon = tk.PhotoImage(file=str(_icon_path))
        root.iconphoto(True, _icon)
    except Exception:
        pass
    app = MTManager(root)
    root.mainloop()

