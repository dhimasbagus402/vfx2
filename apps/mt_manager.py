import re
import shutil
import subprocess
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox
__version__ = "1.1"

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

# Legacy aliases (button hovers)
GREEN       = ACCENT
GREEN_LIGHT = ACCENT_DIM
ORANGE      = WARN
ORANGE_LIGHT= "#2e1e05"
RED         = DANGER
RED_LIGHT   = "#2e0d0d"
YELLOW      = WARN
YELLOW_LIGHT= "#2e1e05"
BLUE        = ACCENT2
BLUE_LIGHT  = ACCENT_DIM
BLUE_DARK   = "#007acc"
CARD        = BG3
CARD2       = BG4
SIDEBAR_BG  = BG2

ALLOWED_ROOT = Path.home()
DOCS_DIR     = Path.home() / "Documents"

EXTRACT_EXTS = {".zip", ".rar", ".tar", ".gz", ".bz2", ".xz", ".7z",
                ".tar.gz", ".tar.bz2", ".tar.xz"}

# Font: JetBrains Mono dengan fallback DejaVu Sans Mono
FONT        = "San Francisco"
FONT_MONO   = "San Francisco"
SIDEBAR_W   = 210


# ── Font resolver ──────────────────────────────────────────────────────────────
def resolve_font(preferred, fallback="DejaVu Sans Mono"):
    try:
        import tkinter.font as tkf
        fams = tkf.families()
        return preferred if preferred in fams else fallback
    except Exception:
        return fallback


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
                               fill=self.TRACK_COL, outline="")
        ty1, ty2 = self._thumb_rect()
        tc = self.THUMB_HOV if self._hover_zone == "thumb" else self.THUMB_COL
        self._draw_rounded_rect(2, ty1+1, w-2, ty2-1, self.THUMB_R, tc)
        bu = self.BTN_HOV if self._hover_zone == "up" else self.BTN_COL
        self.create_rectangle(0, 0, w, self.ARROW_H, fill=bu, outline="")
        ac = self.ARROW_HOV if self._hover_zone == "up" else self.ARROW_COL
        self._draw_arrow(w//2, self.ARROW_H//2, "up", ac)
        bd = self.BTN_HOV if self._hover_zone == "down" else self.BTN_COL
        self.create_rectangle(0, h-self.ARROW_H, w, h, fill=bd, outline="")
        ac2 = self.ARROW_HOV if self._hover_zone == "down" else self.ARROW_COL
        self._draw_arrow(w//2, h - self.ARROW_H//2, "down", ac2)

    def _draw_rounded_rect(self, x1, y1, x2, y2, r, color):
        r = min(r, (x2-x1)//2, max(1,(y2-y1)//2))
        pts = [x1+r,y1, x2-r,y1, x2,y1, x2,y1+r,
               x2,y2-r, x2,y2, x2-r,y2, x1+r,y2,
               x1,y2, x1,y2-r, x1,y1+r, x1,y1, x1+r,y1]
        self.create_polygon(pts, smooth=True, fill=color, outline="")

    def _draw_arrow(self, cx, cy, direction, color):
        s = 3
        if direction == "up":
            pts = [cx, cy-s, cx+s, cy+s, cx-s, cy+s]
        else:
            pts = [cx, cy+s, cx+s, cy-s, cx-s, cy-s]
        self.create_polygon(pts, fill=color, outline="")

    def _on_motion(self, e):
        zone = self._zone(e.y)
        if zone != self._hover_zone:
            self._hover_zone = zone
            self._redraw()

    def _on_leave(self, _=None):
        self._hover_zone = None
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
    def __init__(self, widget, text, delay=280, position="below"):
        self.widget   = widget
        self.text     = text
        self.delay    = delay
        self.position = position  # kept for compat, tooltip follows cursor
        self._id      = None
        self._win     = None
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
            self._win.destroy()
            self._win = None

    def _show(self):
        tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.configure(bg=BORDER2)
        tw.attributes("-topmost", True)
        outer = tk.Frame(tw, bg=BORDER2, padx=1, pady=1)
        outer.pack()
        inner = tk.Frame(outer, bg=BG3, padx=12, pady=7)
        inner.pack()
        _f = resolve_font(FONT)
        tk.Label(inner, text=self.text, bg=BG3, fg=FG2,
                 font=(_f, 9), justify="left", wraplength=380).pack()
        tw.update_idletasks()
        tw_ = tw.winfo_reqwidth()
        th_ = tw.winfo_reqheight()
        x = self._cx + 14
        y = self._cy + 18
        sw = tw.winfo_screenwidth()
        sh = tw.winfo_screenheight()
        if x + tw_ > sw:
            x = self._cx - tw_ - 6
        if y + th_ > sh:
            y = self._cy - th_ - 6
        tw.wm_geometry(f"+{x}+{y}")
        self._win = tw


# ── Helpers ────────────────────────────────────────────────────────────────────
def yad_pick_file(title="Pilih File", filetypes=None, start_dir=None):
    if not shutil.which("yad"):
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
            messagebox.showerror("Akses Ditolak",
                f"File harus berada di dalam:\n{ALLOWED_ROOT}\n\nFile dipilih:\n{selected}")
            return None
        return str(selected) if selected.is_file() else None
    except Exception as e:
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
    _f = resolve_font(FONT)

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
        canvas.create_text(w//2, h//2, text=text, fill=fg,
                           font=(_f, font_size, "bold"))

    def _enter(_=None): _state["bg"] = hover_bg; _draw(hover_bg)
    def _leave(_=None): _state["bg"] = bg;       _draw(bg)
    def _click(_=None): cmd()

    canvas.bind("<Configure>", lambda e: _draw())
    canvas.bind("<Enter>",     _enter)
    canvas.bind("<Leave>",     _leave)
    canvas.bind("<Button-1>",  _click)

    tmp = tk.Label(parent, text=text, font=(_f, font_size, "bold"),
                   padx=padx, pady=pady)
    tmp.update_idletasks()
    rw = tmp.winfo_reqwidth()
    rh = tmp.winfo_reqheight()
    tmp.destroy()
    canvas.config(height=rh, width=rw if not fill_x else 1)
    return holder, canvas

# legacy alias
make_rounded_btn = make_pill_btn


# ── Badge canvas widget (MT4 / MT5) ───────────────────────────────────────────
class Badge(tk.Canvas):
    """Small pill badge — e.g. 'MT4' in blue, 'MT5' in teal."""
    def __init__(self, parent, text, bg_color, fg_color, radius=4, **kw):
        _f = resolve_font(FONT)
        # measure text
        tmp = tk.Label(parent, text=text, font=(_f, 8, "bold"), padx=5, pady=2)
        tmp.update_idletasks()
        w = tmp.winfo_reqwidth() + 2
        h = tmp.winfo_reqheight()
        tmp.destroy()
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
        self.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        if w < 2:
            return
        # track
        self.create_rectangle(0, 0, w, h, fill=self._track, outline="")
        # fill
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
        self.terminals   = []
        self._font       = resolve_font(FONT)
        self._font_mono  = resolve_font(FONT_MONO)
        self._build_styles()
        self._build_ui()
        self.scan_terminals()

    # ── Styles ─────────────────────────────────────────────────────────────────
    def _build_styles(self):
        s = ttk.Style()
        s.theme_use("clam")
        f = self._font

        s.configure("App.Treeview",
            background=BG3, foreground=FG, fieldbackground=BG3,
            rowheight=29, font=(f, 10), borderwidth=0, relief="flat",
            highlightthickness=0, highlightbackground=BG3, highlightcolor=BG3)
        s.configure("App.Treeview.Heading",
            background=BG4, foreground=FG3,
            font=(f, 9), relief="flat", borderwidth=0, padding=(10, 6))
        s.map("App.Treeview",
            background=[("selected", ACCENT_DIM)],
            foreground=[("selected", ACCENT)])
        s.map("App.Treeview.Heading",
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
        tk.Label(title_frame, text=" Manager \u2014 digiOS",
                 bg=BG2, fg=FG2, font=(f, 11)).pack(side="left")
        tk.Label(title_frame, text=f"  v{__version__}", bg=BG2, fg=FG3,
                 font=(f, 9)).pack(side="left", pady=(3, 0))

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

        self.term_tree = ttk.Treeview(
            tlist_box.inner,
            columns=("badge", "name", "sub"),
            show="",          # no headings
            selectmode="browse",
            style="Side.Treeview",
            yscrollcommand=sb_side.set,
        )
        self.term_tree.config(style="Side.Treeview")
        self.term_tree.column("badge", width=38, anchor="center", stretch=False)
        self.term_tree.column("name",  stretch=True, anchor="w")
        self.term_tree.column("sub",   width=80, anchor="w", stretch=False)
        self.term_tree.pack(side="left", fill="both", expand=True)
        self.term_tree.bind("<<TreeviewSelect>>", self._on_select)
        self.term_tree.tag_configure("MT4", foreground=WHITE)
        self.term_tree.tag_configure("MT5", foreground=WHITE)
        self.term_tree.tag_configure("group", foreground=FG3,
                                     font=(f, 8))

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
                               font_size=9, padx=12, pady=7, radius=10)
        h1.pack(side="left", pady=8, padx=(0, 4))
        self._install_btn_holder = h1
        self._install_btn_canvas = c1

        # Separator
        tk.Frame(tb, bg=BORDER2, width=1).pack(side="left", fill="y", padx=6, pady=8)

        # Browse
        h2, c2 = make_pill_btn(tb, "\u25a6 Browse", self.browse_files,
                               bg=BG3, fg=FG, hover_bg=BG4,
                               font_size=9, padx=12, pady=7, radius=10)
        h2.pack(side="left", pady=8, padx=2)
        Tooltip(c2, "Buka data Folder MT")

        # Clear Logs
        h3, c3 = make_pill_btn(tb, "\u2015 Clear Logs", self.clear_logs,
                               bg="#261a05", fg=WARN, hover_bg="#3d2a08",
                               font_size=9, padx=12, pady=7, radius=10)
        h3.pack(side="left", pady=8, padx=2)
        Tooltip(c3, "Hapus semua Logs pada MT")

        # Uninstall
        h4, c4 = make_pill_btn(tb, "\u232b Uninstall", self.uninstall_file,
                               bg="#2a0f0f", fg=DANGER, hover_bg="#3d1212",
                               font_size=9, padx=12, pady=7, radius=10)
        h4.pack(side="left", pady=8, padx=2)
        Tooltip(c4, "Hapus EA atau Indikator pada MT")


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
            color = ACCENT3 if key in ("type", "status") else (ACCENT if key == "path" else FG)
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

        self.file_tree = ttk.Treeview(
            tbl_box.inner,
            columns=("name", "type", "cat", "size", "modified"),
            show="headings", selectmode="browse",
            style="App.Treeview",
            yscrollcommand=sb_file.set,
        )
        for col, lbl, w, anc, stretch in [
            ("name",     "NAME",     0,   "w", True),
            ("type",     "TYPE",     70,  "center", False),
            ("cat",      "CATEGORY", 100, "w",      False),
            ("size",     "SIZE",     80,  "e",      False),
            ("modified", "MODIFIED", 100, "w",      False),
        ]:
            self.file_tree.heading(col, text=lbl)
            self.file_tree.column(col, width=w, anchor=anc, stretch=stretch)
        self.file_tree.pack(side="left", fill="both", expand=True)

        self.file_tree.tag_configure("Expert",    foreground=ACCENT2)
        self.file_tree.tag_configure("Indicator", foreground=ACCENT2)
        self.file_tree.tag_configure("Script",    foreground=ACCENT2)
        self.file_tree.tag_configure("Log",       foreground=ACCENT2)
        self.file_tree.tag_configure("row_even",  background=BG3)
        self.file_tree.tag_configure("row_odd",   background=BG4)

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
                                 font_size=9, padx=14, pady=7, radius=7)
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
        tk.Frame(self.root, bg=BORDER, height=1).pack(fill="x", side="bottom")
        status_bar = tk.Frame(self.root, bg=BG2, height=28)
        status_bar.pack(fill="x", side="bottom")
        status_bar.pack_propagate(False)

        sb_inner = tk.Frame(status_bar, bg=BG2, padx=10)
        sb_inner.pack(fill="both", expand=True)

        self.status_var = tk.StringVar(value="Tekan Scan untuk mendeteksi terminal.")

        # Left dots + status items
        self._mk_status_item(sb_inner, "0 terminal",     ACCENT,  dot=True, varname="_term_count_var")

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

    def _scroll_to_wget(self):
        # Scroll diganti scroll-into-view ke wget entry
        self.wget_entry.focus_set()

    def _install_menu(self):
        """Custom popup dropdown - single click, no border, Linux-safe."""
        f = self._font

        popup = tk.Toplevel(self.root)
        popup.wm_overrideredirect(True)
        popup.attributes("-topmost", True)

        # Outer border frame (1px BORDER2)
        outer = tk.Frame(popup, bg=BORDER2, padx=1, pady=1)
        outer.pack()

        inner = tk.Frame(outer, bg=BG3)
        inner.pack()

        items = [
            ("\u2191  Install Expert Advisor", self.install_ea),
            ("\u2191  Install Indicator",       self.install_indicator),
        ]

        def _make_item(text, cmd):
            row = tk.Frame(inner, bg=BG3, cursor="hand2")
            row.pack(fill="x")
            lbl = tk.Label(row, text=text, bg=BG3, fg=FG,
                           font=(f, 10), anchor="w",
                           padx=16, pady=8)
            lbl.pack(fill="x")

            def _enter(_):
                row.config(bg=BG4)
                lbl.config(bg=BG4, fg=ACCENT)
            def _leave(_):
                row.config(bg=BG3)
                lbl.config(bg=BG3, fg=FG)
            def _click(_):
                popup.destroy()
                cmd()

            for w in (row, lbl):
                w.bind("<Enter>",    _enter)
                w.bind("<Leave>",    _leave)
                w.bind("<Button-1>", _click)

        for text, cmd in items:
            _make_item(text, cmd)

        # Position below the Install button (aligned to button, not cursor)
        popup.update_idletasks()
        btn = self._install_btn_holder
        bx  = btn.winfo_rootx()
        by  = btn.winfo_rooty()
        bh  = btn.winfo_height()
        popup.wm_geometry(f"+{bx}+{by + bh + 2}")

        # Close when clicking outside
        popup.bind("<FocusOut>", lambda e: popup.destroy())
        popup.focus_set()

    # ── Scrollbar proxies ──────────────────────────────────────────────────────
    def _term_yview(self, *args):
        self.term_tree.yview(*args)

    def _file_yview(self, *args):
        self.file_tree.yview(*args)

    # ── Handlers ───────────────────────────────────────────────────────────────
    def _on_select(self, _=None):
        t = self._terminal(silent=True)
        if not t:
            return
        self._reload_files(t)
        # update info bar
        self._info_fields["terminal"][0].set(t["name"])
        self._info_fields["type"][0].set(t["type"])
        # truncate long path for display
        path_str = t["path"]
        home = str(Path.home())
        if path_str.startswith(home):
            path_str = "~" + path_str[len(home):]
        self._info_fields["path"][0].set(path_str)
        self._status(f"Path: {t['path']}")

    def _reload_files(self, t):
        self.file_tree.delete(*self.file_tree.get_children())
        import datetime
        row = 0
        for key, label in [("experts","Expert"),("indicators","Indicator"),
                            ("scripts","Script"),("logs","Log")]:
            folder = t.get(key)
            if folder and folder.exists():
                for f in sorted(folder.iterdir()):
                    if not f.is_file():
                        continue
                    kb = f.stat().st_size / 1024
                    sz = f"{kb:.1f} KB" if kb < 1024 else f"{kb/1024:.2f} MB"
                    mtime = datetime.datetime.fromtimestamp(
                        f.stat().st_mtime).strftime("%Y-%m-%d")
                    ext = f.suffix.lower()
                    stripe = "row_even" if row % 2 == 0 else "row_odd"
                    self.file_tree.insert("", "end",
                        values=(f.name, ext, label, sz, mtime),
                        tags=(label, stripe))
                    row += 1

    def _status(self, msg):
        self.status_var.set(msg)

    def _terminal(self, silent=False):
        sel = self.term_tree.selection()
        if not sel:
            if not silent:
                messagebox.showwarning("Perhatian", "Pilih terminal terlebih dahulu.")
            return None
        idx = self.term_tree.index(sel[0])
        # items include group-label rows (no terminal data); skip them
        item = self.term_tree.item(sel[0])
        if "group" in item.get("tags", ()):
            if not silent:
                messagebox.showwarning("Perhatian", "Pilih terminal, bukan grup.")
            return None
        # map visible index to terminals list — skip group rows
        t_idx = 0
        for iid in self.term_tree.get_children():
            tags = self.term_tree.item(iid, "tags")
            if "group" in tags:
                continue
            if iid == sel[0]:
                break
            t_idx += 1
        if t_idx >= len(self.terminals):
            return None
        return self.terminals[t_idx]

    def _file_info(self):
        sel = self.file_tree.selection()
        if not sel:
            return None, None
        v = self.file_tree.item(sel[0], "values")
        return v[2], v[0]   # category, filename

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
                           start_dir=DOCS_DIR)
        if not fp:
            return
        dst = t[key]
        dst.mkdir(parents=True, exist_ok=True)
        dest = dst / Path(fp).name
        shutil.copy(fp, dest)
        self._reload_files(t)
        self._status(f"'{dest.name}' berhasil diinstall \u2192 {dst}")
        messagebox.showinfo("Berhasil", f"{label} diinstall ke:\n{dst}")

    def install_ea(self):
        self._install("experts", "EA")

    def install_indicator(self):
        self._install("indicators", "Indicator")

    # ── Uninstall ──────────────────────────────────────────────────────────────
    def uninstall_file(self):
        t = self._terminal()
        if not t:
            return
        cat, fname = self._file_info()
        if not fname:
            messagebox.showwarning("Perhatian", "Pilih file dari tabel.")
            return
        target = self._folder_for(t, cat) / fname
        if not target.exists():
            messagebox.showerror("Error", f"File tidak ditemukan:\n{target}")
            return
        if messagebox.askyesno("Konfirmasi Hapus", f"Hapus file ini?\n\n{target}"):
            target.unlink()
            self._reload_files(t)
            self._status(f"'{fname}' dihapus.")

    # ── Clear Logs ─────────────────────────────────────────────────────────────
    def clear_logs(self):
        t = self._terminal()
        if not t:
            return
        logs_dir = t.get("logs")
        if not logs_dir or not logs_dir.exists():
            messagebox.showinfo("Logs Tidak Ditemukan",
                f"Folder logs tidak ditemukan:\n{logs_dir}\n\n"
                "Pastikan MT pernah dijalankan minimal sekali.")
            return
        log_files = [f for f in logs_dir.iterdir() if f.is_file()]
        if not log_files:
            messagebox.showinfo("Logs Kosong", "Tidak ada file log di terminal ini.")
            return
        total_kb  = sum(f.stat().st_size for f in log_files) / 1024
        total_str = f"{total_kb:.1f} KB" if total_kb < 1024 else f"{total_kb/1024:.2f} MB"
        if not messagebox.askyesno("Konfirmasi Hapus Logs",
                f"Hapus semua log?\n\nTerminal  : {t['type']} \u2014 {t['name']}\n"
                f"Jumlah    : {len(log_files)} file\nTotal size: {total_str}\n\n"
                "Tindakan ini tidak dapat dibatalkan."):
            return
        deleted, errors = 0, []
        for f in log_files:
            try:
                f.unlink(); deleted += 1
            except Exception as e:
                errors.append(f"{f.name}: {e}")
        t_ref = self._terminal(silent=True)
        if t_ref:
            self._reload_files(t_ref)
        msg = f"{deleted} file log berhasil dihapus."
        if errors:
            msg += f"\n\nGagal ({len(errors)}):\n" + "\n".join(errors)
        self._status(msg.split("\n")[0])
        messagebox.showinfo("Selesai", msg)

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
                messagebox.showinfo("Path Terminal", str(target))
        except Exception as e:
            messagebox.showerror("Error", str(e))

    # ── wget Download ──────────────────────────────────────────────────────────
    def wget_download(self):
        if not shutil.which("wget"):
            messagebox.showerror("wget tidak ditemukan",
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
        self.root.update()
        try:
            result = subprocess.run(
                ["wget", "-P", str(DOCS_DIR), "--content-disposition", url],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode != 0:
                err_lines = result.stderr.strip().splitlines()
                err = err_lines[-1] if err_lines else "Unknown error"
                self.wget_status_var.set(f"Gagal: {err[:55]}")
                self._progress.set(0.0)
                return
            files_after = sorted(DOCS_DIR.iterdir(),
                                  key=lambda f: f.stat().st_mtime, reverse=True)
            downloaded = next((f for f in files_after if f.is_file()), None)
            self.wget_var.set("")
            self._progress.set(1.0)
            self._wget_pct_var.set("100%")
            if downloaded and self.auto_extract_var.get() and is_archive(downloaded):
                self.wget_status_var.set(f"Mengekstrak {downloaded.name}\u2026")
                self.root.update()
                ok, msg = extract_file(downloaded, DOCS_DIR)
                if ok:
                    self.wget_status_var.set("Selesai + diekstrak \u2192 Documents/")
                    self._status(f"wget + ekstrak selesai: {downloaded.name}")
                    messagebox.showinfo("Selesai",
                        f"File diunduh dan diekstrak ke:\n{DOCS_DIR}\n\nFile: {downloaded.name}")
                else:
                    self.wget_status_var.set("Unduh OK, ekstrak gagal.")
                    messagebox.showwarning("Ekstrak Gagal",
                        f"File berhasil diunduh ke {DOCS_DIR}\n\nTapi ekstrak gagal:\n{msg}")
            else:
                fname = downloaded.name if downloaded else ""
                self.wget_status_var.set(f"Selesai \u2192 Documents/{fname}")
                self._status(f"wget selesai \u2192 {DOCS_DIR}")
                messagebox.showinfo("Download Selesai",
                    f"File berhasil diunduh ke:\n{DOCS_DIR}")
        except subprocess.TimeoutExpired:
            self.wget_status_var.set("Timeout \u2014 >120 detik.")
        except Exception as e:
            self.wget_status_var.set(f"Error: {e}")

    # ── Scan ───────────────────────────────────────────────────────────────────
    def scan_terminals(self):
        self.term_tree.delete(*self.term_tree.get_children())
        self.file_tree.delete(*self.file_tree.get_children())
        self.terminals.clear()
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

        def _mt4_name(folder):
            origin = folder / "origin.txt"
            if origin.exists():
                try:
                    raw = origin.read_bytes().decode("utf-16", errors="ignore").strip()
                    name = raw.split("\\")[-1].strip()
                    if name:
                        return name
                except Exception:
                    pass
            return folder.name[:22]

        users_dir = home / ".wine/drive_c/users"
        if users_dir.exists():
            for userdir in users_dir.iterdir():
                tb = userdir / "AppData/Roaming/MetaQuotes/Terminal"
                if not tb.exists():
                    continue
                for folder in tb.iterdir():
                    mql4 = folder / "MQL4"
                    if mql4.exists():
                        self.terminals.append({
                            "type": "MT4", "name": _mt4_name(folder), "path": str(folder),
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
        for item in self.terminals:
            if item["type"] != cur_type:
                cur_type = item["type"]
                label = f"METATRADER {'4' if cur_type == 'MT4' else '5'}"
                self.term_tree.insert("", "end",
                    values=("", label, ""),
                    tags=("group",))
            badge = "MT4" if item["type"] == "MT4" else "MT5"
            self.term_tree.insert("", "end",
                values=("MT4" if item["type"] == "MT4" else "MT5",
                    item["name"],
                    item["type"]),
                tags=(item["type"],))

        n = len(self.terminals)
        if hasattr(self, "_term_count_var"):
            self._term_count_var.set(f"{n} terminal terdeteksi")
        self._status(f"{n} terminal ditemukan.")
        messagebox.showinfo("Scan Selesai", f"Ditemukan {n} instalasi MetaTrader.")


if __name__ == "__main__":
    root = tk.Tk()
    app = MTManager(root)
    root.mainloop()
