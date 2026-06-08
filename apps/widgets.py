"""
widgets.py — MT Manager
Semua custom tkinter widget yang reusable:
  RoundedBox, RoundScrollbar, Tooltip, Badge, ProgressBar, make_pill_btn
"""

import tkinter as tk
import tkinter.font as tkf
from system import (
    BG, BG2, BG3, BG4, BORDER, BORDER2, ACCENT, ACCENT2, ACCENT3,
    FG, FG2, FG3, DANGER, WARN, FONT, FONT_MONO,
)

# ── Font cache ────────────────────────────────────────────────────────────────
_FONT_CACHE: dict     = {}
_FONT_OBJ_CACHE: dict = {}


def resolve_font(preferred, fallback=None) -> str:
    """preferred: nama font tunggal ATAU daftar kandidat (yang pertama
    tersedia dipakai). Bila tak ada yang cocok: pakai `fallback`, atau
    kandidat terakhir (untuk daftar), atau `preferred` apa adanya."""
    key = tuple(preferred) if isinstance(preferred, (list, tuple)) else preferred
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    try:
        fams = set(tkf.families())
    except Exception:
        fams = set()
    candidates = list(preferred) if isinstance(preferred, (list, tuple)) else [preferred]
    result = next((c for c in candidates if c in fams), None)
    if result is None:
        result = fallback if fallback is not None else candidates[-1]
    _FONT_CACHE[key] = result
    return result


def get_font_obj(family, size, weight="normal") -> tkf.Font:
    """Return cached tkf.Font — satu object per (family, size, weight)."""
    key = (family, size, weight)
    if key not in _FONT_OBJ_CACHE:
        _FONT_OBJ_CACHE[key] = tkf.Font(family=family, size=size, weight=weight)
    return _FONT_OBJ_CACHE[key]


# ── RoundedBox ────────────────────────────────────────────────────────────────
class RoundedBox(tk.Canvas):
    """Canvas dengan border rounded + inner Frame."""

    def __init__(self, parent, radius=8, bg=BG3,
                 border_color=BORDER2, border_w=1, **kw):
        outer = parent.cget("bg") if hasattr(parent, "cget") else BG
        super().__init__(parent, bg=outer, highlightthickness=0, **kw)
        self._r, self._bg, self._bc, self._bw = radius, bg, border_color, border_w
        self._redraw_id = None
        self.inner = tk.Frame(self, bg=bg)
        self.bind("<Configure>", self._redraw)

    def _redraw(self, _=None):
        if self._redraw_id:
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


# ── RoundScrollbar ────────────────────────────────────────────────────────────
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
        self._cmd        = command
        self._first      = 0.0
        self._last       = 1.0
        self._drag       = None
        self._repeat_id  = None
        self._hover_zone = None
        self._set_id     = None   # debounce id untuk set()
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
        # Debounce: batalkan pending redraw, jadwalkan baru dalam 12 ms
        if self._set_id:
            self.after_cancel(self._set_id)
        self._set_id = self.after(12, self._do_set)

    def _do_set(self):
        self._set_id = None
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
        if y < self.ARROW_H:      return "up"
        if y > h - self.ARROW_H:  return "down"
        ty1, ty2 = self._thumb_rect()
        if ty1 <= y <= ty2:        return "thumb"
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
        tc = self.THUMB_HOV if self._hover_zone == "thumb" else self.THUMB_COL
        self.itemconfig("thumb_shape", fill=tc)
        bu = self.BTN_HOV if self._hover_zone == "up" else self.BTN_COL
        self.itemconfig("btn_up", fill=bu)
        ac = self.ARROW_HOV if self._hover_zone == "up" else self.ARROW_COL
        self.itemconfig("arrow_up", fill=ac)
        bd = self.BTN_HOV if self._hover_zone == "down" else self.BTN_COL
        self.itemconfig("btn_down", fill=bd)
        ac2 = self.ARROW_HOV if self._hover_zone == "down" else self.ARROW_COL
        self.itemconfig("arrow_down", fill=ac2)

    def _draw_rounded_rect(self, x1, y1, x2, y2, r, color):
        r   = min(r, (x2-x1)//2, max(1, (y2-y1)//2))
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
        frac   = (new_y1 - t) / (span - thumb_h)
        frac   = max(0.0, min(1.0, frac))
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


# ── Tooltip ───────────────────────────────────────────────────────────────────
class Tooltip:
    """Tooltip ringan: satu Toplevel di-reuse (withdraw/deiconify) bukan destroy/recreate."""

    def __init__(self, widget, text, delay=650, position="below"):
        self.widget   = widget
        self.text     = text
        self.delay    = delay
        self._id      = None
        self._win     = None
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

    def _show(self):
        self._id = None
        if self._win is None:
            self._win = tk.Toplevel(self.widget)
            self._win.wm_overrideredirect(True)
            self._win.attributes("-topmost", True)
            outer = tk.Frame(self._win, bg=BORDER2, padx=1, pady=1)
            outer.pack()
            inner = tk.Frame(outer, bg=BG3, padx=10, pady=5)
            inner.pack()
            _f = resolve_font(FONT)
            self._lbl = tk.Label(inner, text=self.text, bg=BG3, fg=FG2,
                                  font=(_f, 9), justify="left")
            self._lbl.pack()
        else:
            self._lbl.config(text=self.text)
            self._win.deiconify()
        self._win.update_idletasks()
        tw = self._win.winfo_reqwidth()
        th = self._win.winfo_reqheight()
        x  = self._cx + 12
        y  = self._cy + 20
        sw = self._win.winfo_screenwidth()
        sh = self._win.winfo_screenheight()
        if x + tw > sw:
            x = self._cx - tw - 4
        if y + th > sh:
            y = self._cy - th - 4
        self._win.wm_geometry(f"+{x}+{y}")

    def _cancel(self, _=None):
        if self._id:
            self.widget.after_cancel(self._id)
            self._id = None
        if self._win:
            self._win.withdraw()

    def update_text(self, text):
        self.text = text
        if self._lbl:
            self._lbl.config(text=text)


# ── make_pill_btn ─────────────────────────────────────────────────────────────
def make_pill_btn(parent, text, cmd, bg=BG3, fg=FG, hover_bg=BG4,
                  font_size=10, padx=12, pady=6, radius=10,
                  fill_x=False) -> tuple:
    """Buat tombol pill rounded. Return (holder_frame, canvas)."""
    _f   = resolve_font(FONT)
    _fnt = get_font_obj(_f, font_size, "bold")

    holder = tk.Frame(parent, bg=parent.cget("bg") if hasattr(parent, "cget") else BG)
    canvas = tk.Canvas(holder, bg=holder.cget("bg"),
                       highlightthickness=0, cursor="hand2")
    canvas.pack(fill="x" if fill_x else "none")

    _state    = {"bg": bg, "lw": 0, "lh": 0}
    _ftuple   = (_f, font_size, "bold")
    _pts_cache = [None]

    def _draw(b=None):
        bcolor = b or _state["bg"]
        w = canvas.winfo_width()
        h = canvas.winfo_height()
        if w < 2 or h < 2:
            return
        if w != _state["lw"] or h != _state["lh"]:
            r = radius
            _pts_cache[0] = [r,0, w-r,0, w,0, w,r, w,h-r, w,h, w-r,h, r,h,
                              0,h, 0,h-r, 0,r, 0,0, r,0]
            _state["lw"] = w
            _state["lh"] = h
        canvas.delete("all")
        canvas.create_polygon(_pts_cache[0], smooth=True, fill=bcolor, outline="")
        canvas.create_text(w//2, h//2, text=text, fill=fg, font=_ftuple)

    def _enter(_=None): _state["bg"] = hover_bg; _draw(hover_bg)
    def _leave(_=None): _state["bg"] = bg;        _draw(bg)
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


# ── Badge ─────────────────────────────────────────────────────────────────────
class Badge(tk.Canvas):
    """Small pill badge — e.g. 'MT4' in blue, 'MT5' in teal."""

    def __init__(self, parent, text, bg_color, fg_color, radius=4, **kw):
        _f   = resolve_font(FONT)
        _fnt = get_font_obj(_f, 8, "bold")
        w    = _fnt.measure(text) + 5 * 2 + 2
        h    = _fnt.metrics("linespace") + 2 * 2
        outer = parent.cget("bg") if hasattr(parent, "cget") else BG2
        super().__init__(parent, width=w, height=h,
                         bg=outer, highlightthickness=0, **kw)
        r   = radius
        pts = [r,0, w-r,0, w,0, w,r, w,h-r, w,h, w-r,h, r,h,
               0,h, 0,h-r, 0,r, 0,0, r,0]
        self.create_polygon(pts, smooth=True, fill=bg_color, outline="")
        self.create_text(w//2, h//2, text=text, fill=fg_color,
                         font=(_f, 8, "bold"))


# ── ProgressBar ───────────────────────────────────────────────────────────────
class ProgressBar(tk.Canvas):
    def __init__(self, parent, height=3, bg=BG4, fill=ACCENT, **kw):
        outer = parent.cget("bg") if hasattr(parent, "cget") else BG
        super().__init__(parent, height=height, bg=outer,
                         highlightthickness=0, **kw)
        self._fill      = fill
        self._track     = bg
        self._pct       = 0.0
        self._last_pct  = -1.0   # sentinel: paksa redraw pertama kali
        self._redraw_id = None
        self.bind("<Configure>", self._on_configure)

    def set(self, pct):
        pct = max(0.0, min(1.0, pct))
        if pct == self._pct:
            return                # nilai sama, tidak perlu redraw
        self._pct = pct
        self._schedule_redraw()

    def _on_configure(self, _=None):
        self._last_pct = -1.0    # ukuran berubah, paksa redraw
        self._schedule_redraw()

    def _schedule_redraw(self):
        if self._redraw_id:
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
        self._last_pct = self._pct


# ── Popup helper ──────────────────────────────────────────────────────────────
def themed_popup(root, kind: str, title: str, message: str):
    """Tampilkan popup bertemakan dark dengan icon sesuai kind."""
    from system import POPUP_ICONS, BG, BG2, BG3, BG4, BORDER, FG, FG2, FG3
    icon_char, icon_color = POPUP_ICONS.get(kind, ("\u2139", ACCENT))
    _f  = resolve_font(FONT)
    _fm = resolve_font(FONT_MONO)

    dlg = tk.Toplevel(root)
    dlg.title(title)
    dlg.configure(bg=BG)
    dlg.resizable(False, False)
    dlg.attributes("-topmost", True)

    hdr = tk.Frame(dlg, bg=BG2, height=48)
    hdr.pack(fill="x")
    hdr.pack_propagate(False)
    hdr_i = tk.Frame(hdr, bg=BG2, padx=20)
    hdr_i.pack(fill="both", expand=True)
    tk.Label(hdr_i, text=f"{icon_char}  {title}",
             bg=BG2, fg=icon_color, font=(_f, 12, "bold")).pack(side="left", fill="y")
    tk.Frame(dlg, bg=BORDER, height=1).pack(fill="x")

    body = tk.Frame(dlg, bg=BG, padx=24, pady=18)
    body.pack(fill="both", expand=True)
    tk.Label(body, text=message, bg=BG, fg=FG2, font=(_f, 10),
             justify="left", anchor="w", wraplength=380).pack(anchor="w")
    tk.Frame(dlg, bg=BORDER, height=1).pack(fill="x")

    foot = tk.Frame(dlg, bg=BG2, height=44)
    foot.pack(fill="x")
    foot.pack_propagate(False)
    fi = tk.Frame(foot, bg=BG2, padx=12)
    fi.pack(fill="both", expand=True)
    oh, _ = make_pill_btn(fi, "OK", dlg.destroy,
                          bg=BG3, fg=FG, hover_bg=BG4,
                          font_size=9, padx=20, pady=6, radius=7)
    oh.pack(side="right", pady=8)

    dlg.update_idletasks()
    rx = root.winfo_x() + root.winfo_width()  // 2 - dlg.winfo_reqwidth()  // 2
    ry = root.winfo_y() + root.winfo_height() // 2 - dlg.winfo_reqheight() // 2
    dlg.geometry(f"+{rx}+{ry}")
    dlg.deiconify()
    dlg.lift()
    dlg.focus_force()
