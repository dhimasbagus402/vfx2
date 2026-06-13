"""
ui.py — MT Manager
Kelas MTManager: membangun UI tkinter dan menangani event.
Semua logika bisnis didelegasikan ke system.py.
Semua widget custom diimport dari widgets.py.
"""

import tkinter as tk
import tkinter.font as tkf
from tkinter import ttk
from pathlib import Path
import shutil
import os

import system as be
import update as upd
from widgets import (
    RoundedBox, RoundScrollbar, Tooltip, Badge, ProgressBar,
    make_pill_btn, themed_popup, resolve_font, get_font_obj,
)
from system import (
    __version__,
    BG, BG2, BG3, BG4, ACCENT, ACCENT2, ACCENT3, ACCENT_DIM,
    BORDER, BORDER2, DANGER, WARN, FG, FG2, FG3, WHITE, PURPLE,
    FONT, FONT_MONO, SIDEBAR_W,
    TABLE_FONT_SIZE, TABLE_HEADING_SIZE, TABLE_COLUMNS,
    CAT_COL_WIDTH, CAT_COLORS,
    AS_COL_WIDTH, AS_TRACK_W, AS_TRACK_H, AS_THUMB_R,
    AS_COLOR_ON, AS_COLOR_OFF, AS_THUMB_COL,
    CHK_COL_WIDTH, CHK_FONT_SIZE, CHK_CHAR_OFF, CHK_CHAR_ON,
    TABLE_ROW_HEIGHT, DOCS_DIR,
)


class MTManager:
    def __init__(self, root):
        self.root = root
        self.root.title("MetaTrader Manager")
        self.root.geometry("1180x700")
        self.root.configure(bg=BG)
        self.root.resizable(True, True)
        self.root.minsize(900, 520)
        self.root.after(0, lambda: self.root.attributes("-zoomed", True))

        self.terminals              = []
        self._font                  = resolve_font(FONT)
        self._font_mono             = resolve_font(FONT_MONO)
        self._cfg                   = be.load_config()
        self._as_state_cache        = {}
        self._all_term_rows         = ()
        self._select_after_id       = None
        self._last_selected_path    = None

        # Clipboard: list of (src_path, fname, cat) + mode "copy"|"cut"
        self._clipboard: list       = []
        self._clipboard_mode: str   = ""   # "copy" | "cut"

        self._build_styles()
        self._build_ui()
        self.scan_terminals(silent=True)
        self.root.after(400, self._disk_poll)
        self.root.after(2000, self._autostart_sync_poll)
        if self.auto_update_var.get():
            self.root.after(800, self._auto_update_check)

    # ── Styles ────────────────────────────────────────────────────────────────
    def _build_styles(self):
        s = ttk.Style()
        s.theme_use("clam")
        f = self._font

        _rh_data = TABLE_FONT_SIZE * 2 + 6
        _rh_chk  = CHK_FONT_SIZE  * 2 + 6
        _rh = TABLE_ROW_HEIGHT if TABLE_ROW_HEIGHT > 0 else max(_rh_data, _rh_chk)
        self._shared_row_height = _rh

        _tv_base = dict(background=BG3, foreground=FG, fieldbackground=BG3,
                        rowheight=_rh, borderwidth=0, relief="flat",
                        highlightthickness=0, highlightbackground=BG3, highlightcolor=BG3)
        _th_base = dict(background=BG4, foreground=FG3, relief="flat",
                        borderwidth=0, font=(f, TABLE_HEADING_SIZE))
        _sel_map = [("selected", ACCENT_DIM)]
        _fg_map  = [("selected", ACCENT)]
        _th_map  = [("active", BG4)]

        for style, font_sz in (("App", TABLE_FONT_SIZE), ("Chk", CHK_FONT_SIZE), ("Cat", TABLE_FONT_SIZE)):
            s.configure(f"{style}.Treeview", **_tv_base, font=(f, font_sz))
            s.configure(f"{style}.Treeview.Heading", **_th_base, padding=(10, 6))
            s.map(f"{style}.Treeview",
                  background=_sel_map, foreground=_fg_map)
            s.map(f"{style}.Treeview.Heading",
                  background=_th_map, relief=[("active", "flat")])
            s.layout(f"{style}.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])

        s.configure("Chk.Treeview.Heading", padding=(0, 6))

        s.configure("Side.Treeview",
                    background=BG2, foreground=FG, fieldbackground=BG2,
                    rowheight=44, font=(f, 10), borderwidth=0, relief="flat",
                    highlightthickness=0, highlightbackground=BG2, highlightcolor=BG2)
        s.map("Side.Treeview",
              background=[("selected", BG3)], foreground=[("selected", ACCENT)])
        s.layout("Side.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])

        s.layout("Vertical.TScrollbar", [])
        s.layout("Horizontal.TScrollbar", [])

    # ── UI ────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        f  = self._font
        fm = self._font_mono

        # ── TITLEBAR ──────────────────────────────────────────────────────────
        titlebar = tk.Frame(self.root, bg=BG2, height=36)
        titlebar.pack(fill="x", side="top")
        titlebar.pack_propagate(False)
        tk.Frame(self.root, bg=BORDER, height=1).pack(fill="x", side="top")

        tb_inner = tk.Frame(titlebar, bg=BG2)
        tb_inner.pack(fill="both", expand=True, padx=14)

        dots = tk.Frame(tb_inner, bg=BG2)
        dots.pack(side="left", fill="y")
        for col in ("#ff5f57", "#febc2e", "#28c840"):
            c = tk.Canvas(dots, width=11, height=11, bg=BG2, highlightthickness=0)
            c.pack(side="left", padx=(0, 5), pady=0)
            c.create_oval(1, 1, 10, 10, fill=col, outline="")
        dots.pack(side="left", pady=12)

        title_frame = tk.Frame(tb_inner, bg=BG2)
        title_frame.pack(side="left", padx=10, fill="y")
        tk.Label(title_frame, text="MetaTrader", bg=BG2, fg=ACCENT,
                 font=(f, 11, "bold")).pack(side="left")
        tk.Label(title_frame, text=" Manager \u2014 digiOS Edition",
                 bg=BG2, fg=FG2, font=(f, 11)).pack(side="left")
        tk.Label(title_frame, text=f"  v{__version__}",
                 bg=BG2, fg=FG3, font=(f, 9)).pack(side="left", pady=(2, 0))

        # ── BODY ──────────────────────────────────────────────────────────────
        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True)

        # ── SIDEBAR ───────────────────────────────────────────────────────────
        sidebar = tk.Frame(body, bg=BG2, width=SIDEBAR_W)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        tk.Frame(body, bg=BORDER, width=1).pack(side="left", fill="y")

        tk.Label(sidebar, text="TERMINALS", bg=BG2, fg=FG3,
                 font=(f, 8), anchor="w", padx=14, pady=10).pack(fill="x")

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

        tlist_outer = tk.Frame(sidebar, bg=BG2, padx=8)
        tlist_outer.pack(fill="both", expand=True, pady=(0, 6))

        tlist_box = RoundedBox(tlist_outer, radius=7, bg=BG2,
                               border_color=BORDER2, border_w=1)
        tlist_box.pack(fill="both", expand=True)

        sb_side = RoundScrollbar(tlist_box.inner, command=self._term_yview)
        sb_side.pack(side="right", fill="y", padx=(0, 2), pady=3)
        self._sb_side_ref = sb_side

        self._as_canvas = tk.Canvas(
            tlist_box.inner, width=AS_COL_WIDTH, bg=BG2,
            highlightthickness=0, cursor="hand2")
        self._as_canvas.pack(side="left", fill="y")
        self._as_canvas.bind("<Button-1>",  self._on_as_click)
        self._as_canvas.bind("<Motion>",    self._on_as_motion)
        self._as_canvas.bind("<Leave>",     self._on_as_leave)
        self._as_canvas.bind("<Configure>", lambda e: self._draw_as_canvas())
        self._as_hover_iid   = None
        self._as_tooltip_id  = None
        self._as_tooltip_win = None

        self.term_tree = ttk.Treeview(
            tlist_box.inner, columns=("badge", "name", "sub"),
            show="", selectmode="browse", style="Side.Treeview",
            yscrollcommand=self._on_side_scroll)
        self.term_tree.config(style="Side.Treeview")
        self.term_tree.column("badge", width=38, anchor="center", stretch=False)
        self.term_tree.column("name",  stretch=True, anchor="w")
        self.term_tree.column("sub",   width=80, anchor="w", stretch=False)
        self.term_tree.pack(side="left", fill="both", expand=True)
        self.term_tree.bind("<<TreeviewSelect>>", self._on_select)
        for ev in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.term_tree.bind(ev, lambda e: self._side_wheel(e))
            self._as_canvas.bind(ev, lambda e: self._side_wheel(e))
        self.term_tree.tag_configure("MT4",   foreground=WHITE)
        self.term_tree.tag_configure("MT5",   foreground=WHITE)
        self.term_tree.tag_configure("group", foreground=FG3, font=(f, 8))

        # ── MANAGE MT (dasar sidebar) ─────────────────────────────────────────
        tk.Label(sidebar, text="MANAGE", bg=BG2, fg=FG3,
                 font=(f, 8), anchor="w", padx=14, pady=4).pack(fill="x", pady=(2, 0))
        mt_wrap = tk.Frame(sidebar, bg=BG2, padx=10)
        mt_wrap.pack(fill="x", pady=(0, 12))
        mt_holder, _mt_canvas = make_pill_btn(
            mt_wrap, "\u2699  Add / Remove MT", self._manage_mt_menu,
            bg=BG3, fg="#5ecf3e", hover_bg=BG4,
            font_size=10, padx=12, pady=8, radius=8, fill_x=True)
        mt_holder.pack(fill="x")
        self._manage_mt_btn_holder = mt_holder
        self._install_mt_btn_holder = mt_holder   # legacy alias
        Tooltip(_mt_canvas, "Install, Duplicate, or Uninstall MetaTrader",
                position="above")

        # ── MAIN PANEL ────────────────────────────────────────────────────────
        main = tk.Frame(body, bg=BG)
        main.pack(side="left", fill="both", expand=True)

        # ── TOOLBAR ───────────────────────────────────────────────────────────
        toolbar = tk.Frame(main, bg=BG2, height=46)
        toolbar.pack(fill="x")
        toolbar.pack_propagate(False)
        tk.Frame(main, bg=BORDER, height=1).pack(fill="x")
        tb = tk.Frame(toolbar, bg=BG2, padx=12)
        tb.pack(fill="both", expand=True)

        _btns = [
            ("\u2699 Manage EA / Indicator", self._manage_ea_menu,
             ACCENT_DIM, ACCENT, "#1d2b36"),
            ("\u2692 Utility", self._utility_menu, "#261a05", WARN, "#3d2a08"),
            None,  # separator
            ("\u25a6 Browse", self.browse_files, BG3, FG, BG4),
            ("\u25b6 Open MT", self.open_mt, "#0d2200", "#5ecf3e", "#1a3a00"),
        ]
        _tooltips = {
            "\u2699 Manage EA / Indicator": "Install or remove EA / Indicator on MT",
            "\u2692 Utility": "Clear Logs and open MetaEditor",
            "\u25a6 Browse": "Open MT data folder",
            "\u25b6 Open MT": "Run the selected MT terminal",
        }

        for item in _btns:
            if item is None:
                tk.Frame(tb, bg=BORDER2, width=1).pack(side="left", fill="y", padx=6, pady=8)
                continue
            lbl, cmd, bg_, fg_, hbg = item
            h, c = make_pill_btn(tb, lbl, cmd, bg=bg_, fg=fg_, hover_bg=hbg,
                                  font_size=10, padx=12, pady=7, radius=10)
            h.pack(side="left", pady=8, padx=2)
            if lbl == "\u2699 Manage EA / Indicator":
                self._manage_ea_btn_holder = h
                self._install_btn_holder = h   # legacy alias
                self._install_btn_canvas = c
            elif lbl == "\u2692 Utility":
                self._utility_btn_holder = h
            if lbl in _tooltips:
                Tooltip(c, _tooltips[lbl])

        # ── CONTENT AREA ──────────────────────────────────────────────────────
        content_main = tk.Frame(main, bg=BG)
        content_main.pack(fill="both", expand=True)
        self._content_canvas = None

        # ── INFO BAR ──
        info_wrap   = tk.Frame(content_main, bg=BG, padx=14, pady=8)
        info_wrap.pack(fill="x")
        info_border = tk.Frame(info_wrap, bg=BORDER2)
        info_border.pack(fill="x")
        info_card   = tk.Frame(info_border, bg=BG2, padx=14, pady=8)
        info_card.pack(fill="x", padx=1, pady=1)

        self._info_fields = {}

        # ── Autostart control (untuk terminal yang sedang dipilih) ──
        as_col = tk.Frame(info_card, bg=BG2)
        as_col.pack(side="right", padx=(28, 0))
        tk.Label(as_col, text="AUTOSTART ON BOOT", bg=BG2, fg=FG3,
                 font=(f, 8), anchor="e").pack(anchor="e")
        as_row = tk.Frame(as_col, bg=BG2)
        as_row.pack(anchor="e", pady=(2, 0))
        self._as_switch = tk.Canvas(as_row, width=38, height=18, bg=BG2,
                                    highlightthickness=0, cursor="hand2")
        self._as_switch.pack(side="left")
        self._as_switch.bind("<Button-1>", self._toggle_selected_autostart)
        self._as_switch_lbl = tk.Label(as_row, text="—", bg=BG2, fg=FG3,
                                       font=(f, 10, "bold"))
        self._as_switch_lbl.pack(side="left", padx=(8, 0))
        Tooltip(self._as_switch,
                "Run this terminal automatically when the system/VPS boots")
        self._draw_as_switch(False, enabled=False)

        for key, label, default in [
            ("terminal", "TERMINAL", "—"),
            ("type",     "TYPE",     "—"),
            ("path",     "PATH",     "—"),
        ]:
            col = tk.Frame(info_card, bg=BG2)
            col.pack(side="left", padx=(0, 28))
            tk.Label(col, text=label, bg=BG2, fg=FG3,
                     font=(f, 8), anchor="w").pack(anchor="w")
            var   = tk.StringVar(value=default)
            color = FG if key == "type" else (ACCENT if key == "path" else FG)
            vfont = (fm, 10) if key == "path" else (f, 10, "bold")
            lbl   = tk.Label(col, textvariable=var, bg=BG2, fg=color,
                             font=vfont, anchor="w")
            lbl.pack(anchor="w")
            self._info_fields[key] = (var, lbl)

        # ── FILE TABLE SECTION ──
        sec_wrap   = tk.Frame(content_main, bg=BG, padx=14)
        sec_wrap.pack(fill="both", expand=True)
        sec_header = tk.Frame(sec_wrap, bg=BG)
        sec_header.pack(fill="x", pady=(0, 4))
        tk.Label(sec_header, text="EXPERT ADVISORS & INDICATORS",
                 bg=BG, fg=FG3, font=(f, 8)).pack(side="left")
        tk.Frame(sec_header, bg=BORDER, height=1).pack(
            side="left", fill="x", expand=True, padx=(10, 0), pady=4)

        tbl_box = RoundedBox(sec_wrap, radius=7, bg=BG3, border_color=BORDER2, border_w=1)
        tbl_box.pack(fill="both", expand=True)
        sb_file = RoundScrollbar(tbl_box.inner, command=self._file_yview)
        sb_file.pack(side="right", fill="y", padx=(0, 2), pady=3)

        self._checked     = set()
        self._all_checked = False

        self.chk_tree = ttk.Treeview(tbl_box.inner, columns=("chk",), show="headings",
                                      selectmode="browse", style="Chk.Treeview",
                                      yscrollcommand=self._on_chk_scroll)
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
        self.chk_tree.tag_configure("row_even", background=BG3)
        self.chk_tree.tag_configure("row_odd",  background=BG4)
        self.chk_tree.tag_configure("checked",  background=ACCENT_DIM, foreground=ACCENT3)
        self.chk_tree.tag_configure("cut_dim",  foreground=FG3)

        self.cat_tree = ttk.Treeview(tbl_box.inner, columns=("cat",), show="headings",
                                      selectmode="browse", style="Cat.Treeview",
                                      yscrollcommand=self._on_cat_scroll)
        self.cat_tree.heading("cat", text="CATEGORY", anchor="w")
        self.cat_tree.column("cat", width=CAT_COL_WIDTH, minwidth=CAT_COL_WIDTH,
                              anchor="w", stretch=False)
        self.cat_tree.pack(side="left", fill="y")
        for label, color in CAT_COLORS.items():
            self.cat_tree.tag_configure(label, foreground=color)
        self.cat_tree.tag_configure("row_even", background=BG3)
        self.cat_tree.tag_configure("row_odd",  background=BG4)
        self.cat_tree.tag_configure("checked",  background=ACCENT_DIM)
        self.cat_tree.tag_configure("cut_dim",  foreground=FG3)

        self.file_tree = ttk.Treeview(tbl_box.inner,
                                       columns=("name", "size", "modified"),
                                       show="headings", selectmode="browse",
                                       style="App.Treeview",
                                       yscrollcommand=self._on_file_scroll)
        for col, lbl, w, anc, stretch in TABLE_COLUMNS:
            self.file_tree.heading(col, text=lbl)
            self.file_tree.column(col, width=w, anchor=anc, stretch=stretch)
        self.file_tree.pack(side="left", fill="both", expand=True)
        self._sb_file = sb_file
        self.file_tree.tag_configure("row_even", background=BG3)
        self.file_tree.tag_configure("row_odd",  background=BG4)
        self.file_tree.tag_configure("checked",  background=ACCENT_DIM)
        self.file_tree.tag_configure("cut_dim",  foreground=FG3)   # dimmed saat Cut

        def _kill_borders():
            for tree in (self.chk_tree, self.cat_tree):
                try:
                    tree.tk.call(tree, "configure",
                                 "-highlightthickness", 0,
                                 "-highlightbackground", BG3,
                                 "-highlightcolor", BG3,
                                 "-borderwidth", 0, "-relief", "flat")
                except Exception:
                    pass
        self.root.after_idle(_kill_borders)

        self.chk_tree.bind("<ButtonRelease-1>", self._on_chk_click)
        self.cat_tree.bind("<ButtonRelease-1>",  self._on_file_click)
        self.file_tree.bind("<ButtonRelease-1>", self._on_file_click)

        # Klik kanan → context menu Copy/Cut/Paste/Delete
        for tree in (self.chk_tree, self.cat_tree, self.file_tree):
            tree.bind("<Button-3>", self._on_file_right_click)

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

        row1         = tk.Frame(wget_card, bg=BG2)
        row1.pack(fill="x")
        entry_frame  = tk.Frame(row1, bg=BORDER2, highlightthickness=0, padx=1, pady=1)
        entry_frame.pack(side="left", fill="x", expand=True, padx=(0, 10))

        self.wget_var   = tk.StringVar()
        self.wget_entry = tk.Entry(
            entry_frame, textvariable=self.wget_var,
            bg=BG3, fg=FG, insertbackground=ACCENT2, relief="flat",
            font=(fm, 9), highlightthickness=0)
        self.wget_entry.pack(fill="x", ipady=7, padx=1)

        PLACEHOLDER = 'wget --content-disposition "https://dropfile.id/xxxxxx"'
        self._wget_placeholder = PLACEHOLDER

        def _focus_in(e):
            if self.wget_var.get() == PLACEHOLDER:
                self.wget_var.set("")
                self.wget_entry.config(fg=FG)

        def _focus_out(e):
            if not self.wget_var.get().strip():
                self.wget_var.set(PLACEHOLDER)
                self.wget_entry.config(fg=FG3)

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
            outer = tk.Frame(popup, bg=BORDER2, padx=1, pady=1); outer.pack()
            inner = tk.Frame(outer, bg=BG3); inner.pack()

            def _do_paste():
                popup.destroy()
                self.wget_entry.focus_set()
                _focus_in(None)
                self.wget_entry.event_generate("<<Paste>>")

            row = tk.Frame(inner, bg=BG3, cursor="hand2"); row.pack(fill="x")
            lbl = tk.Label(row, text="\u29c9  Paste", bg=BG3, fg=FG,
                           font=(fm, 10), anchor="w", padx=12, pady=8)
            lbl.pack(fill="x")

            def _enter(_): row.config(bg=BG4); lbl.config(bg=BG4, fg=ACCENT)
            def _leave(_): row.config(bg=BG3); lbl.config(bg=BG3, fg=FG)
            for w_ in (row, lbl):
                w_.bind("<Enter>",    _enter)
                w_.bind("<Leave>",    _leave)
                w_.bind("<Button-1>", lambda _: _do_paste())

            popup.update_idletasks()
            pw, ph = popup.winfo_reqwidth(), popup.winfo_reqheight()
            sx, sy = e.x_root, e.y_root
            sw = popup.winfo_screenwidth(); sh = popup.winfo_screenheight()
            if sx + pw > sw: sx = sw - pw - 4
            if sy + ph > sh: sy = sy - ph - 4
            popup.wm_geometry(f"+{sx}+{sy}")
            popup.bind("<FocusOut>", lambda _: popup.destroy())
            popup.focus_set()

        self.wget_entry.bind("<Button-3>", _show_context_menu)
        Tooltip(self.wget_entry, 'Enter URL or wget command from dropfile.id',
                delay=200, position="above")

        def _wget_paste():
            """Ambil teks dari clipboard sistem, isi ke entry wget."""
            try:
                text = self.root.clipboard_get().strip()
            except Exception:
                text = ""
            if not text:
                self.wget_status_var.set("Clipboard is empty.")
                return
            # Bersihkan placeholder lalu set teks
            _focus_in(None)
            self.wget_var.set(text)
            self.wget_entry.config(fg=FG)
            # Animasi flash border hijau sebentar
            entry_frame.config(bg=ACCENT3)
            self.root.after(300, lambda: entry_frame.config(bg=BORDER2))
            self.wget_entry.focus_set()
            self.wget_status_var.set("")

        paste_h, paste_c = make_pill_btn(row1, "\u29c9 Paste", _wget_paste,
                                          bg=BG3, fg=FG, hover_bg=BG4,
                                          font_size=10, padx=12, pady=7, radius=7)
        paste_h.pack(side="left", padx=(0, 6))
        Tooltip(paste_c, "Paste URL from clipboard into the input field", position="above")

        dl_h, _ = make_pill_btn(row1, "\u2193 Download", self.wget_download,
                                 bg=ACCENT_DIM, fg=ACCENT, hover_bg="#1d2b36",
                                 font_size=10, padx=14, pady=7, radius=7)
        dl_h.pack(side="left")

        row2 = tk.Frame(wget_card, bg=BG2); row2.pack(fill="x", pady=(8, 0))
        self.wget_status_var = tk.StringVar(value="")
        self._wget_lbl = tk.Label(row2, textvariable=self.wget_status_var,
                                   bg=BG2, fg=FG3, font=(f, 9), anchor="w")
        self._wget_lbl.pack(side="left")
        self._wget_pct_var = tk.StringVar(value="")
        tk.Label(row2, textvariable=self._wget_pct_var,
                 bg=BG2, fg=ACCENT, font=(f, 9)).pack(side="right")

        self._progress = ProgressBar(wget_card, height=2, bg=BG4, fill=ACCENT)
        self._progress.pack(fill="x", pady=(4, 0))

        row3 = tk.Frame(wget_card, bg=BG2); row3.pack(fill="x", pady=(6, 0))
        self.auto_extract_var = tk.BooleanVar(value=True)
        cb = tk.Checkbutton(
            row3, text=" Auto-extract enabled \u2014 ZIP, RAR, 7Z, TAR didukung via xarchiver",
            variable=self.auto_extract_var, bg=BG2, fg=FG3, selectcolor=BG3,
            activebackground=BG2, activeforeground=FG, font=(f, 9),
            relief="flat", borderwidth=0, highlightthickness=0, cursor="hand2")
        cb.pack(side="left")
        Tooltip(cb, "Auto extract if file is ZIP/RAR/7Z", position="above")

        # ── STATUS BAR ──
        tk.Frame(self.root, bg=BG, height=10).pack(fill="x", side="bottom")
        status_bar = tk.Frame(self.root, bg=BG2, height=28)
        status_bar.pack(fill="x", side="bottom")
        status_bar.pack_propagate(False)
        sb_inner = tk.Frame(status_bar, bg=BG2, padx=10)
        sb_inner.pack(fill="both", expand=True)

        self.status_var = tk.StringVar(value="Press Scan to detect terminals.")
        self._mk_status_item(sb_inner, "0 terminal", ACCENT, dot=True, varname="_term_count_var")

        # ── Disk space (drive terminal terpilih, fallback home) ──
        disk_fr = tk.Frame(sb_inner, bg=BG2)
        disk_fr.pack(side="left", padx=(6, 0), fill="y")
        tk.Label(disk_fr, text="DISK", bg=BG2, fg=FG3,
                 font=(self._font, 8)).pack(side="left", padx=(0, 6), pady=10)
        self._disk_bar = ProgressBar(disk_fr, height=6, bg=BORDER2, fill=ACCENT3)
        self._disk_bar.config(width=70)
        self._disk_bar.pack(side="left", pady=11)
        self._disk_var = tk.StringVar(value="—")
        tk.Label(disk_fr, textvariable=self._disk_var, bg=BG2, fg=FG3,
                 font=(self._font_mono, 8)).pack(side="left", padx=(8, 0))
        self._disk_free_bytes  = 0
        self._disk_total_bytes = 0
        # Bind tooltip ke disk_fr + semua child-nya agar area hover lebih luas
        self._disk_tooltips = [Tooltip(disk_fr, "Disk: not measured", delay=150)]
        for _w in disk_fr.winfo_children():
            self._disk_tooltips.append(Tooltip(_w, "Disk: not measured", delay=150))
        # Refresh data disk setiap kali hover agar tooltip selalu up-to-date
        def _on_disk_hover(e=None):
            t = self._terminal(silent=True)
            self._refresh_disk(t["path"] if t else None)
        for _w in [disk_fr] + list(disk_fr.winfo_children()):
            _w.bind("<Enter>", _on_disk_hover, add="+")

        self.auto_update_var = tk.BooleanVar(value=self._cfg.get("auto_update", True))

        def _on_auto_update_toggle():
            self._cfg["auto_update"] = self.auto_update_var.get()
            be.save_config(self._cfg)

        au_frame = tk.Frame(sb_inner, bg=BG2)
        au_frame.pack(side="right", padx=(0, 6), fill="y")
        au_cb = tk.Checkbutton(
            au_frame, text="Auto-update", variable=self.auto_update_var,
            command=_on_auto_update_toggle, bg=BG2, fg=FG3, selectcolor=BG3,
            activebackground=BG2, activeforeground=FG, font=(self._font, 8),
            relief="flat", borderwidth=0, highlightthickness=0, cursor="hand2")
        au_cb.pack(side="left", fill="y")
        Tooltip(au_cb, "Check for updates automatically on app start", position="above")

        update_c = tk.Canvas(sb_inner, bg=BG2, highlightthickness=0,
                              height=10, cursor="hand2")
        update_c.pack(side="right", padx=(0, 4))
        self._update_canvas = update_c

        def _draw_update_btn(hover=False):
            update_c.delete("all")
            w = update_c.winfo_width(); h = update_c.winfo_height()
            if w < 4 or h < 4:
                return
            bg_c = "#1a3a2a" if hover else "#0f2a1e"
            r    = 5
            pts  = [r,0, w-r,0, w,0, w,r, w,h-r, w,h, w-r,h, r,h,
                    0,h, 0,h-r, 0,r, 0,0, r,0]
            update_c.create_polygon(pts, smooth=True, fill=bg_c, outline="")
            update_c.create_text(w//2, h//2, text="\u21ba  Update",
                                 fill=ACCENT3, font=(self._font, 10, "bold"))

        def _run_update(_=None):
            upd.handle_update_click(self)

        update_c.bind("<Configure>", lambda e: _draw_update_btn())
        update_c.bind("<Enter>",     lambda e: _draw_update_btn(hover=True))
        update_c.bind("<Leave>",     lambda e: _draw_update_btn(hover=False))
        update_c.bind("<Button-1>",  _run_update)
        Tooltip(update_c, "Update MT Manager", position="above")

        _fnt2 = tkf.Font(family=self._font, size=11, weight="bold")
        _rw   = _fnt2.measure("\u21ba  Update") + 10 * 2
        _rh2  = _fnt2.metrics("linespace") + 3 * 2
        update_c.config(width=_rw, height=_rh2)

        # \u2500\u2500 Branding: digitalku.com (clickable) \u2500\u2500
        brand = tk.Label(sb_inner, text="digitalku.com", bg=BG2, fg=FG3,
                         font=(self._font, 8), cursor="hand2")
        brand.pack(side="right", padx=(0, 14), fill="y")
        brand.bind("<Button-1>",
                   lambda e: webbrowser.open("https://www.digitalku.com"))
        brand.bind("<Enter>", lambda e: brand.config(fg=ACCENT))
        brand.bind("<Leave>", lambda e: brand.config(fg=FG3))
        Tooltip(brand, "Open https://www.digitalku.com", position="above")

    # ── Status helpers ────────────────────────────────────────────────────────
    def _mk_status_item(self, parent, text, color, dot=False, icon=None,
                        side="left", varname=None):
        f  = self._font
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

    def _status(self, msg):
        self.status_var.set(msg)

    def _refresh_disk(self, path=None):
        free, total = be.disk_usage(path)
        self._disk_free_bytes  = free
        self._disk_total_bytes = total
        if total <= 0:
            self._disk_var.set("—")
            self._disk_bar._fill = BORDER2
            self._disk_bar._pct  = -1.0
            self._disk_bar.set(0.0)
            if hasattr(self, "_disk_tooltips"):
                for _t in self._disk_tooltips:
                    _t.text = "Disk: unavailable"
            return
        free_frac = free / total
        used = total - free
        to_kb = lambda b: f"{b / 1024:,.0f} KB"
        if free_frac < 0.10:
            color = DANGER
        elif free_frac < 0.20:
            color = WARN
        else:
            color = ACCENT3
        self._disk_bar._fill = color
        self._disk_bar._pct  = -1.0          # paksa redraw dengan warna baru
        self._disk_bar.set(1.0 - free_frac)
        self._disk_var.set(f"{be.fmt_disk(free)} free / {be.fmt_disk(total)}")
        if hasattr(self, "_disk_tooltips"):
            _tip = (
                f"Free  : {to_kb(free)}\n"
                f"Used  : {to_kb(used)}\n"
                f"Total : {to_kb(total)}\n"
                f"Usage : {(1 - free_frac) * 100:.1f}% used"
            )
            for _t in self._disk_tooltips:
                _t.text = _tip

    def _disk_poll(self):
        t = self._terminal(silent=True)
        self._refresh_disk(t["path"] if t else None)
        self.root.after(60000, self._disk_poll)

    def _draw_scan_btn(self, _=None, hover=False):
        c = self._scan_canvas
        c.delete("all")
        w = c.winfo_width(); h = c.winfo_height()
        if w < 4 or h < 4:
            return
        bg  = "#1d2b36" if hover else ACCENT_DIM
        bdr = ACCENT; r = 7
        pts  = [r,0, w-r,0, w,0, w,r, w,h-r, w,h, w-r,h, r,h,
                0,h, 0,h-r, 0,r, 0,0, r,0]
        c.create_polygon(pts, smooth=True, fill=bdr, outline="")
        pts2 = [r+1,1, w-r-1,1, w-1,1, w-1,r+1, w-1,h-r-1, w-1,h-1,
                w-r-1,h-1, r+1,h-1, 1,h-1, 1,h-r-1, 1,r+1, 1,1, r+1,1]
        c.create_polygon(pts2, smooth=True, fill=bg, outline="")
        c.create_text(w//2, h//2, text="\u25ce  Scan MetaTrader",
                      fill=ACCENT, font=(self._font, 9, "bold"))

    # ── Scroll sync ───────────────────────────────────────────────────────────
    def _term_yview(self, *args):
        self.term_tree.yview(*args)
        self._draw_as_canvas()

    def _on_side_scroll(self, first, last):
        self._sb_side_ref.set(first, last)
        self._draw_as_canvas()

    def _side_wheel(self, e):
        delta = -3 if (e.num == 4 or e.delta > 0) else 3
        self.term_tree.yview_scroll(delta, "units")
        self._draw_as_canvas()
        return "break"

    def _file_yview(self, *args):
        self.chk_tree.yview(*args)
        self.cat_tree.yview(*args)
        self.file_tree.yview(*args)

    def _on_any_scroll(self, first, last):
        first = float(first)
        last  = float(last)
        self.chk_tree.yview_moveto(first)
        self.cat_tree.yview_moveto(first)
        self.file_tree.yview_moveto(first)
        self._sb_file.set(first, last)

    _on_file_scroll = _on_any_scroll
    _on_chk_scroll  = _on_any_scroll
    _on_cat_scroll  = _on_any_scroll

    # ── Selection handler ─────────────────────────────────────────────────────
    def _on_select(self, _=None):
        if getattr(self, "_select_after_id", None):
            self.root.after_cancel(self._select_after_id)
        self._select_after_id = self.root.after(60, self._do_select)

    def _do_select(self):
        self._select_after_id = None
        t = self._terminal(silent=True)
        if not t:
            return
        if getattr(self, "_last_selected_path", None) == t["path"]:
            return
        self._last_selected_path = t["path"]
        self._reload_files(t)
        self._info_fields["terminal"][0].set(t["name"])
        self._info_fields["type"][0].set(t["type"])
        type_color = ACCENT3 if t["type"] == "MT4" else WARN
        self._info_fields["type"][1].config(fg=type_color)
        path_str = t["path"]
        home = str(Path.home())
        if path_str.startswith(home):
            path_str = "~" + path_str[len(home):]
        self._info_fields["path"][0].set(path_str)
        self._refresh_disk(t["path"])
        self._update_as_switch(t)
        self._status(f"Path: {t['path']}")

    # ── File list ─────────────────────────────────────────────────────────────
    def _reload_files(self, t):
        for tree in (self.chk_tree, self.cat_tree, self.file_tree):
            tree.delete(*tree.get_children())
        self._checked.clear()
        self._all_checked = False
        self.chk_tree.heading("chk", text=CHK_CHAR_OFF)

        rows = be.scan_terminal_files(t)

        # Batch insert: masukkan semua sekaligus lebih cepat dari satu per satu
        for row_idx, (label, fname, sz, mtime) in enumerate(rows):
            stripe = "row_even" if row_idx % 2 == 0 else "row_odd"
            iid    = f"r{row_idx}"
            self.chk_tree.insert("", "end", iid=iid, values=(CHK_CHAR_OFF,), tags=(stripe,))
            self.cat_tree.insert("", "end", iid=iid, values=(label,), tags=(label, stripe))
            self.file_tree.insert("", "end", iid=iid,
                values=(fname, sz, mtime), tags=(stripe,))

    # ── Terminal helper ───────────────────────────────────────────────────────
    def _terminal(self, silent=False):
        sel = self.term_tree.selection()
        if not sel:
            if not silent:
                themed_popup(self.root, "warning", "Notice",
                              "Please select a terminal first.")
            return None
        iid  = sel[0]
        item = self.term_tree.item(iid)
        if "group" in item.get("tags", ()):
            if not silent:
                themed_popup(self.root, "warning", "Notice", "Please select a terminal, not a group.")
            return None
        return getattr(self, "_iid_to_terminal", {}).get(iid)

    # ── Checkbox handlers ─────────────────────────────────────────────────────
    def _on_chk_click(self, event):
        iid = self.chk_tree.identify_row(event.y)
        if iid:
            self._toggle_row(iid)

    def _on_file_click(self, event):
        iid = event.widget.identify_row(event.y)
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
        n = len(all_iids)
        # Hanya perlu yield ke event loop jika ada banyak baris
        yield_every = 100 if n > 200 else 0
        if self._all_checked:
            self._checked = set(all_iids)
            for i, iid in enumerate(all_iids):
                self.chk_tree.set(iid, "chk", CHK_CHAR_ON)
                for tree in trees:
                    cur = tree.item(iid, "tags")
                    if "checked" not in cur:
                        tree.item(iid, tags=(*cur, "checked"))
                if yield_every and i % yield_every == yield_every - 1:
                    self.root.update_idletasks()
        else:
            self._checked.clear()
            for i, iid in enumerate(all_iids):
                self.chk_tree.set(iid, "chk", CHK_CHAR_OFF)
                for tree in trees:
                    tree.item(iid, tags=[tg for tg in tree.item(iid, "tags") if tg != "checked"])
                if yield_every and i % yield_every == yield_every - 1:
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
        cat = self.cat_tree.item(iid, "values")[0] if self.cat_tree.exists(iid) else None
        return cat, v[0]

    def _folder_for(self, t, label):
        return t.get({"Expert":"experts","Indicator":"indicators",
                      "Script":"scripts","Log":"logs"}.get(label, "experts"))

    def _resolve_path(self, t, cat, fname):
        """Resolve path lengkap dari (cat, fname).
        Untuk Log, fname adalah relative path dari terminal root sehingga
        langsung di-join ke t['path']. Untuk kategori lain tetap pakai _folder_for.
        """
        if cat in ("Log", "History"):
            return Path(t["path"]) / fname
        return self._folder_for(t, cat) / fname

    # ── Context Menu (klik kanan tabel file) ──────────────────────────────────
    def _on_file_right_click(self, event):
        """Tampilkan context menu Copy/Cut/Paste/Delete saat klik kanan di tabel."""
        # Seleksi baris yang diklik
        widget = event.widget
        iid    = widget.identify_row(event.y)
        if iid:
            self.chk_tree.selection_set(iid)
            self.cat_tree.selection_set(iid)
            self.file_tree.selection_set(iid)

        t = self._terminal(silent=True)
        f = self._font

        # Kumpulkan target: prioritaskan checked, fallback ke baris terpilih
        targets = self._get_checked_targets(t) or self._get_selected_target(t)

        has_targets     = bool(targets)
        has_clipboard   = bool(self._clipboard)
        paste_label     = ""
        if has_clipboard:
            mode_lbl  = "Cut" if self._clipboard_mode == "cut" else "Copy"
            n         = len(self._clipboard)
            paste_lbl = f"Paste ({mode_lbl} {n} file)"
        else:
            paste_lbl = "Paste"

        popup = tk.Toplevel(self.root)
        popup.wm_overrideredirect(True)
        popup.attributes("-topmost", True)

        outer = tk.Frame(popup, bg=BORDER2, padx=1, pady=1)
        outer.pack()
        inner = tk.Frame(outer, bg=BG3)
        inner.pack(fill="x")

        _closed = [False]

        def _close():
            if _closed[0]: return
            _closed[0] = True
            try: popup.destroy()
            except Exception: pass

        def _sep():
            tk.Frame(inner, bg=BORDER, height=1).pack(fill="x", padx=8, pady=2)

        def _item(icon, label, cmd, fg_color=FG, enabled=True):
            row = tk.Frame(inner, bg=BG3, cursor="hand2" if enabled else "arrow")
            row.pack(fill="x")
            color = fg_color if enabled else FG3
            lbl   = tk.Label(row, text=f"  {icon}  {label}", bg=BG3, fg=color,
                             font=(f, 10), anchor="w", padx=8, pady=7)
            lbl.pack(fill="x")
            if enabled:
                def _enter(_): row.config(bg=BG4); lbl.config(bg=BG4)
                def _leave(_): row.config(bg=BG3); lbl.config(bg=BG3)
                def _click(_):
                    _close()
                    self.root.after(10, cmd)
                for w_ in (row, lbl):
                    w_.bind("<Enter>",    _enter)
                    w_.bind("<Leave>",    _leave)
                    w_.bind("<Button-1>", _click)

        # ── Menu items ──
        n_sel = len(targets) if targets else 0
        sel_suffix = f" ({n_sel} file)" if n_sel > 1 else ""

        _item("\u29c9", f"Copy{sel_suffix}",
              lambda: self._clipboard_copy(targets),
              fg_color=ACCENT, enabled=has_targets)

        _item("\u2702", f"Cut{sel_suffix}",
              lambda: self._clipboard_cut(targets),
              fg_color=WARN, enabled=has_targets)

        _sep()

        _item("\u2398", paste_lbl,
              self._clipboard_paste,
              fg_color=ACCENT3, enabled=has_clipboard and t is not None)

        _sep()

        _item("\u232b", f"Delete{sel_suffix}",
              self.uninstall_file,
              fg_color=DANGER, enabled=has_targets)

        # Posisi popup di dekat kursor
        popup.update_idletasks()
        pw = popup.winfo_reqwidth()
        ph = popup.winfo_reqheight()
        sx, sy = event.x_root, event.y_root
        sw = popup.winfo_screenwidth()
        sh = popup.winfo_screenheight()
        if sx + pw > sw: sx = sw - pw - 4
        if sy + ph > sh: sy = sy - ph - 4
        popup.wm_geometry(f"+{sx}+{sy}")

        # Tutup saat klik di luar
        def _on_outside(e):
            if _closed[0]: return
            try:
                wx, wy = popup.winfo_rootx(), popup.winfo_rooty()
                ww, wh = popup.winfo_width(), popup.winfo_height()
                if not (wx <= e.x_root <= wx + ww and wy <= e.y_root <= wy + wh):
                    _close()
            except Exception:
                _close()

        popup.bind("<FocusOut>", lambda e: _close())
        self.root.bind_all("<ButtonPress-1>", _on_outside, add=True)
        popup.bind("<Destroy>", lambda e: self.root.unbind_all("<ButtonPress-1>"))
        popup.focus_set()

    def _get_checked_targets(self, t):
        """Return list (src_path, fname, cat) dari baris yang di-centang."""
        if not t or not self._checked:
            return []
        targets = []
        for iid in list(self._checked):
            try:
                fname = self.file_tree.item(iid, "values")[0]
                cat   = self.cat_tree.item(iid, "values")[0]
                src   = self._resolve_path(t, cat, fname)
                if src.exists():
                    targets.append((src, fname, cat))
            except Exception:
                pass
        return targets

    def _get_selected_target(self, t):
        """Return list (src_path, fname, cat) dari baris yang terpilih (single)."""
        if not t:
            return []
        cat, fname = self._file_info()
        if not fname:
            return []
        src = self._resolve_path(t, cat, fname)
        if not src.exists():
            return []
        return [(src, fname, cat)]

    def _clipboard_copy(self, targets):
        if not targets:
            return
        self._clipboard      = targets
        self._clipboard_mode = "copy"
        n = len(targets)
        self._status(f"\u29c9 {n} file(s) copied to clipboard.")

    def _clipboard_cut(self, targets):
        if not targets:
            return
        self._clipboard      = targets
        self._clipboard_mode = "cut"
        n = len(targets)
        # Buat set nama file untuk lookup O(1)
        cut_fnames = {fname for _, fname, _ in targets}
        for iid in self.file_tree.get_children():
            vals = self.file_tree.item(iid, "values")
            if vals and vals[0] in cut_fnames:
                for tree in (self.chk_tree, self.cat_tree, self.file_tree):
                    cur = list(tree.item(iid, "tags"))
                    if "cut_dim" not in cur:
                        tree.item(iid, tags=(*cur, "cut_dim"))
        self._status(f"\u2702 {n} file(s) ready to move (Cut).")

    def _clipboard_paste(self):
        """Paste file clipboard ke folder kategori yang sesuai di terminal aktif."""
        if not self._clipboard:
            return
        t = self._terminal()
        if not t:
            return
        f  = self._font
        fm = self._font_mono

        items   = self._clipboard
        mode    = self._clipboard_mode
        errors  = []
        done    = 0
        skipped = []

        for src_path, fname, cat in items:
            dst_folder = self._folder_for(t, cat)
            if dst_folder is None:
                errors.append(f"{fname}: unknown category '{cat}'"); continue
            dst_folder.mkdir(parents=True, exist_ok=True)
            dst = dst_folder / fname

            # Cegah paste ke folder yang sama
            if src_path.parent == dst_folder:
                skipped.append(fname); continue

            # Jika sudah ada, beri suffix angka
            if dst.exists():
                stem = dst.stem; suffix_ = dst.suffix; counter = 2
                while dst.exists():
                    dst = dst_folder / f"{stem} ({counter}){suffix_}"
                    counter += 1

            try:
                if mode == "cut":
                    shutil.move(str(src_path), str(dst))
                else:
                    shutil.copy2(str(src_path), str(dst))
                done += 1
            except Exception as e:
                errors.append(f"{fname}: {e}")

        # Bersihkan clipboard jika Cut
        if mode == "cut":
            self._clipboard      = []
            self._clipboard_mode = ""

        self._reload_files(t)

        # Status
        parts = []
        if done:    parts.append(f"{done} file(s) {'moved' if mode == 'cut' else 'copied'}")
        if skipped: parts.append(f"{len(skipped)} skipped (same folder)")
        if errors:  parts.append(f"{len(errors)} failed")
        self._status(" · ".join(parts) + f" \u2192 {t['name']}")

        # Popup hasil
        if errors or done:
            self._popup_paste_result(done, mode, t["name"], skipped, errors)

    def _popup_paste_result(self, done, mode, terminal_name, skipped, errors):
        f   = self._font
        fm  = self._font_mono
        ok  = not errors
        icon_ch = "\u2713" if ok else "\u26a0"
        icon_fg = "#5ecf3e" if ok else WARN
        action  = "moved" if mode == "cut" else "copied"

        res = tk.Toplevel(self.root)
        res.title("Paste Complete"); res.configure(bg=BG)
        res.resizable(False, False); res.attributes("-topmost", True)

        hdr = tk.Frame(res, bg=BG2, height=48); hdr.pack(fill="x"); hdr.pack_propagate(False)
        hdr_i = tk.Frame(hdr, bg=BG2, padx=20); hdr_i.pack(fill="both", expand=True)
        tk.Label(hdr_i, text=f"{icon_ch}  Paste Complete",
                 bg=BG2, fg=icon_fg, font=(f, 12, "bold")).pack(side="left", fill="y")
        tk.Frame(res, bg=BORDER, height=1).pack(fill="x")

        body = tk.Frame(res, bg=BG, padx=24, pady=18); body.pack(fill="both", expand=True)
        tk.Label(body, text=icon_ch, bg=BG, fg=icon_fg,
                 font=(f, 22)).grid(row=0, column=0, rowspan=2, padx=(0, 16), sticky="n")
        tk.Label(body, text=f"{done} file(s) {action} successfully.",
                 bg=BG, fg=FG, font=(f, 11, "bold"), anchor="w").grid(row=0, column=1, sticky="w")
        detail_lines = []
        if skipped:
            detail_lines.append(f"\u2014 {len(skipped)} skipped (source = destination folder)")
        if errors:
            detail_lines += [f"\u2717 {e}" for e in errors[:4]]
        if detail_lines:
            tk.Label(body, text="\n".join(detail_lines), bg=BG,
                     fg=FG2 if not errors else DANGER,
                     font=(fm, 8), anchor="w", justify="left",
                     wraplength=360).grid(row=1, column=1, sticky="w", pady=(4, 0))
        body.columnconfigure(1, weight=1)

        tk.Frame(res, bg=BORDER, height=1).pack(fill="x")
        foot = tk.Frame(res, bg=BG2, height=44); foot.pack(fill="x"); foot.pack_propagate(False)
        fi   = tk.Frame(foot, bg=BG2, padx=12); fi.pack(fill="both", expand=True)
        oh, _ = make_pill_btn(fi, "OK", res.destroy, bg=BG3, fg=FG, hover_bg=BG4,
                              font_size=9, padx=20, pady=6, radius=7)
        oh.pack(side="right", pady=8)
        res.update_idletasks(); self._center_win(res)
        res.deiconify(); res.lift(); res.focus_force()

    # ── Install EA/Indicator ──────────────────────────────────────────────────
    def _install(self, key, label):
        t = self._terminal()
        if not t:
            return
        DOCS_DIR.mkdir(exist_ok=True)
        fp = be.yad_pick_file(title=f"Select {label} file",
                              filetypes=["*.ex4", "*.ex5", "*.mq4", "*.mq5"],
                              start_dir=DOCS_DIR, root_widget=self.root)
        if not fp:
            return
        dst = t[key]
        dst.mkdir(parents=True, exist_ok=True)
        dest = dst / Path(fp).name
        shutil.copy(fp, dest)
        self._reload_files(t)
        self._status(f"'{dest.name}' installed successfully \u2192 {dst}")
        self._popup_install_result(label, dst)

    def _popup_install_result(self, label, dst):
        f  = self._font
        fm = self._font_mono
        res = tk.Toplevel(self.root)
        res.title("Install Successful"); res.configure(bg=BG)
        res.resizable(False, False); res.attributes("-topmost", True)
        hdr_r = tk.Frame(res, bg=BG2, height=48); hdr_r.pack(fill="x"); hdr_r.pack_propagate(False)
        hdr_ri = tk.Frame(hdr_r, bg=BG2, padx=20); hdr_ri.pack(fill="both", expand=True)
        tk.Label(hdr_ri, text="\u2713  Install Successful",
                 bg=BG2, fg="#5ecf3e", font=(f, 12, "bold")).pack(side="left", fill="y")
        tk.Frame(res, bg=BORDER, height=1).pack(fill="x")
        body_r = tk.Frame(res, bg=BG, padx=24, pady=18); body_r.pack(fill="both", expand=True)
        tk.Label(body_r, text="\u2713", bg=BG, fg="#5ecf3e",
                 font=(f, 22)).grid(row=0, column=0, rowspan=2, padx=(0,16), sticky="n")
        tk.Label(body_r, text=f"{label} installed successfully.",
                 bg=BG, fg=FG, font=(f, 11, "bold"), anchor="w").grid(row=0, column=1, sticky="w")
        tk.Label(body_r, text=str(dst), bg=BG, fg=FG3,
                 font=(fm, 8), anchor="w", wraplength=340).grid(row=1, column=1, sticky="w", pady=(4,0))
        body_r.columnconfigure(1, weight=1)
        tk.Frame(res, bg=BORDER, height=1).pack(fill="x")
        foot_r = tk.Frame(res, bg=BG2, height=44); foot_r.pack(fill="x"); foot_r.pack_propagate(False)
        fi_r = tk.Frame(foot_r, bg=BG2, padx=12); fi_r.pack(fill="both", expand=True)
        oh_r, _ = make_pill_btn(fi_r, "OK", res.destroy,
                                bg=BG3, fg=FG, hover_bg=BG4, font_size=9, padx=20, pady=6, radius=7)
        oh_r.pack(side="right", pady=8)
        res.update_idletasks()
        self._center_win(res); res.deiconify(); res.lift(); res.focus_force()

    def install_ea(self):
        self._install("experts", "EA")

    def install_indicator(self):
        self._install("indicators", "Indicator")

    # ── Delete files ──────────────────────────────────────────────────────────
    def uninstall_file(self):
        t = self._terminal()
        if not t:
            return
        f  = self._font
        fm = self._font_mono

        def _confirm_delete_popup(title, items_label, item_count, detail_lines, on_confirm):
            dlg = tk.Toplevel(self.root); dlg.title(title); dlg.configure(bg=BG)
            dlg.resizable(False, False); dlg.attributes("-topmost", True)
            hdr = tk.Frame(dlg, bg=BG2, height=48); hdr.pack(fill="x"); hdr.pack_propagate(False)
            hdr_inner = tk.Frame(hdr, bg=BG2, padx=20); hdr_inner.pack(fill="both", expand=True)
            tk.Label(hdr_inner, text=f"\u232b  {title}",
                     bg=BG2, fg=DANGER, font=(f, 12, "bold")).pack(side="left", fill="y")
            tk.Frame(dlg, bg=BORDER, height=1).pack(fill="x")
            body = tk.Frame(dlg, bg=BG, padx=24, pady=18); body.pack(fill="both", expand=True)
            info_box = tk.Frame(body, bg=BG3, padx=14, pady=10); info_box.pack(fill="x", pady=(0,10))
            tk.Label(info_box, text=items_label, bg=BG3, fg=FG2,
                     font=(f, 10, "bold"), anchor="w").pack(anchor="w", pady=(0,6))
            for line in detail_lines[:8]:
                tk.Label(info_box, text=f"  {line}", bg=BG3, fg=FG3,
                         font=(fm, 8), anchor="w").pack(anchor="w")
            if len(detail_lines) > 8:
                tk.Label(info_box, text=f"  \u2026 and {len(detail_lines)-8} more file(s)",
                         bg=BG3, fg=FG3, font=(f, 8), anchor="w").pack(anchor="w")
            tk.Label(body, text="This action cannot be undone.",
                     bg=BG, fg=FG2, font=(f, 9), anchor="w").pack(anchor="w", pady=(0,4))
            tk.Frame(dlg, bg=BORDER, height=1).pack(fill="x")
            foot = tk.Frame(dlg, bg=BG2, height=50); foot.pack(fill="x"); foot.pack_propagate(False)
            fi_f = tk.Frame(foot, bg=BG2, padx=14); fi_f.pack(fill="both", expand=True)
            def _do(): dlg.destroy(); on_confirm()
            del_h, _ = make_pill_btn(fi_f, f"\u232b  Delete {item_count} File(s)", _do,
                                     bg="#2a0f0f", fg=DANGER, hover_bg="#3d1212",
                                     font_size=10, padx=20, pady=7, radius=7)
            del_h.pack(side="right", pady=8, padx=(0,6))
            can_h, _ = make_pill_btn(fi_f, "Cancel", dlg.destroy,
                                     bg=BG3, fg=FG, hover_bg=BG4,
                                     font_size=9, padx=20, pady=6, radius=7)
            can_h.pack(side="right", pady=8)
            dlg.update_idletasks(); self._center_win(dlg); dlg.deiconify(); dlg.lift(); dlg.focus_force()

        def _result_popup(deleted, errors):
            res = tk.Toplevel(self.root); res.title("File Dihapus"); res.configure(bg=BG)
            res.resizable(False, False); res.attributes("-topmost", True)
            ok_icon = "\u2713" if not errors else "\u26a0"
            ok_fg   = "#5ecf3e" if not errors else WARN
            hdr2 = tk.Frame(res, bg=BG2, height=48); hdr2.pack(fill="x"); hdr2.pack_propagate(False)
            hdr2i = tk.Frame(hdr2, bg=BG2, padx=20); hdr2i.pack(fill="both", expand=True)
            tk.Label(hdr2i, text=f"{ok_icon}  File Dihapus",
                     bg=BG2, fg=ok_fg, font=(f, 12, "bold")).pack(side="left", fill="y")
            tk.Frame(res, bg=BORDER, height=1).pack(fill="x")
            body2 = tk.Frame(res, bg=BG, padx=24, pady=18); body2.pack(fill="both", expand=True)
            tk.Label(body2, text=ok_icon, bg=BG, fg=ok_fg,
                     font=(f, 22)).grid(row=0, column=0, rowspan=2, padx=(0,16), sticky="n")
            tk.Label(body2, text=f"{deleted} file deleted successfully.",
                     bg=BG, fg=FG, font=(f, 11, "bold"), anchor="w").grid(row=0, column=1, sticky="w")
            if errors:
                tk.Label(body2, text="\n".join(errors[:3]),
                         bg=BG, fg=DANGER, font=(f, 9), anchor="w",
                         wraplength=340).grid(row=1, column=1, sticky="w", pady=(4,0))
            body2.columnconfigure(1, weight=1)
            tk.Frame(res, bg=BORDER, height=1).pack(fill="x")
            foot2 = tk.Frame(res, bg=BG2, height=44); foot2.pack(fill="x"); foot2.pack_propagate(False)
            fi2 = tk.Frame(foot2, bg=BG2, padx=12); fi2.pack(fill="both", expand=True)
            oh, _ = make_pill_btn(fi2, "OK", res.destroy, bg=BG3, fg=FG, hover_bg=BG4,
                                  font_size=9, padx=20, pady=6, radius=7)
            oh.pack(side="right", pady=8)
            res.update_idletasks(); self._center_win(res); res.deiconify(); res.lift(); res.focus_force()

        if self._checked:
            targets = []
            for iid in list(self._checked):
                try:
                    v = self.file_tree.item(iid, "values"); fname = v[0]
                    cat = self.cat_tree.item(iid, "values")[0]
                    path = self._resolve_path(t, cat, fname)
                    targets.append((fname, path))
                except Exception:
                    pass
            if not targets:
                self._status("Notice: selected file is invalid."); return
            def _do_multi():
                deleted, errors = 0, []
                for fname, path in targets:
                    try:
                        if path.exists(): path.unlink(); deleted += 1
                        else: errors.append(f"{fname}: not found")
                    except Exception as e:
                        errors.append(f"{fname}: {e}")
                self._reload_files(t); self._status(f"{deleted} file(s) deleted.")
                _result_popup(deleted, errors)
            _confirm_delete_popup("Confirm Delete", f"Delete the following {len(targets)} file(s)?",
                                  len(targets), [n for n, _ in targets], _do_multi)
            return

        cat, fname = self._file_info()
        if not fname:
            self._status("Check the files to delete, or select a row from the table."); return
        target = self._resolve_path(t, cat, fname)
        if not target.exists():
            self._status(f"File not found: {target}"); return
        def _do_single():
            target.unlink(); self._reload_files(t); self._status(f"'{fname}' deleted.")
        _confirm_delete_popup("Confirm Delete", "Delete this file?", 1, [fname], _do_single)

    # ── Clear Logs ────────────────────────────────────────────────────────────
    def clear_logs_and_history(self):
        t = self._terminal()
        if not t:
            return
        f  = self._font
        fm = self._font_mono
        logs_dir      = t.get("logs")
        terminal_path = Path(t["path"])

        def _info_popup(title, msg, icon="\u2139", icon_fg=ACCENT):
            w = tk.Toplevel(self.root); w.title(title); w.configure(bg=BG)
            w.resizable(False, False); w.attributes("-topmost", True)
            hdr = tk.Frame(w, bg=BG2, height=48); hdr.pack(fill="x"); hdr.pack_propagate(False)
            hdr_i = tk.Frame(hdr, bg=BG2, padx=20); hdr_i.pack(fill="both", expand=True)
            tk.Label(hdr_i, text=f"{icon}  {title}",
                     bg=BG2, fg=icon_fg, font=(f, 12, "bold")).pack(side="left", fill="y")
            tk.Frame(w, bg=BORDER, height=1).pack(fill="x")
            body = tk.Frame(w, bg=BG, padx=24, pady=18); body.pack(fill="both", expand=True)
            tk.Label(body, text=msg, bg=BG, fg=FG2, font=(f, 10),
                     justify="left", anchor="w", wraplength=380).pack(anchor="w")
            tk.Frame(w, bg=BORDER, height=1).pack(fill="x")
            foot = tk.Frame(w, bg=BG2, height=44); foot.pack(fill="x"); foot.pack_propagate(False)
            fi = tk.Frame(foot, bg=BG2, padx=12); fi.pack(fill="both", expand=True)
            oh, _ = make_pill_btn(fi, "OK", w.destroy, bg=BG3, fg=FG, hover_bg=BG4,
                                  font_size=9, padx=20, pady=6, radius=7)
            oh.pack(side="right", pady=8)
            w.update_idletasks(); self._center_win(w); w.deiconify(); w.lift(); w.focus_force()

        # ── Kumpulkan log files ───────────────────────────────────────────────
        _log_dirs = []
        if logs_dir and logs_dir.exists():
            _log_dirs.append(logs_dir)
        _tester_logs = terminal_path / "Tester" / "logs"
        if _tester_logs.exists():
            _log_dirs.append(_tester_logs)
        _tester_dir = terminal_path / "Tester"
        if _tester_dir.exists():
            try:
                for _agent_dir in sorted(_tester_dir.iterdir()):
                    if _agent_dir.is_dir() and _agent_dir.name.startswith("Agent"):
                        _agent_logs = _agent_dir / "logs"
                        if _agent_logs.exists():
                            _log_dirs.append(_agent_logs)
            except OSError:
                pass

        log_files = []
        for _d in _log_dirs:
            try:
                log_files.extend([lf for lf in _d.iterdir() if lf.is_file()])
            except OSError:
                pass

        # ── Kumpulkan history files (.hcs) ────────────────────────────────────
        def _ci_dir(parent, name):
            lo = name.lower()
            try:
                for e in parent.iterdir():
                    if e.is_dir() and e.name.lower() == lo:
                        return e
            except OSError:
                pass
            return None

        _history_roots = []
        for _bname in ("bases", "Bases"):
            _p = terminal_path / _bname
            if _p.is_dir():
                _history_roots.append(_p)
                break
        for _tname in ("Tester", "tester"):
            _tp = terminal_path / _tname
            if _tp.is_dir():
                _tb = _ci_dir(_tp, "bases")
                if _tb:
                    _history_roots.append(_tb)
                break

        hcs_files = []
        for _base_root in _history_roots:
            try:
                _accounts = sorted(_base_root.iterdir(), key=lambda e: e.name)
            except OSError:
                continue
            for _account in _accounts:
                if not _account.is_dir():
                    continue
                if _account.name.lower() == "default":
                    continue
                _hist_dir = _ci_dir(_account, "history")
                if not _hist_dir:
                    continue
                try:
                    _pairs = [e for e in _hist_dir.iterdir() if e.is_dir()]
                except OSError:
                    continue
                for _pair in _pairs:
                    try:
                        hcs_files.extend([
                            Path(e.path) for e in os.scandir(_pair)
                            if e.is_file(follow_symlinks=False)
                            and e.name.lower().endswith((".hcs", ".hcc"))
                        ])
                    except OSError:
                        continue

        all_files   = log_files + hcs_files

        # ── MT4: tambahkan history/*.hst (skip 'default'), tester/history/*.fxt,
        #         dan tester/logs/*.log yang belum tercakup di atas ──
        if t.get("type") == "MT4":
            extra_logs, extra_history = be.collect_mt4_clear_extras(t)
            log_files += extra_logs
            hcs_files += extra_history
            all_files += extra_logs + extra_history

        if not all_files:
            _info_popup("No Files Found",
                "No log or history (.hcs/.hcc) files were found on this terminal.",
                icon="\u26a0", icon_fg=WARN)
            return

        total_kb  = sum(lf.stat().st_size for lf in all_files if lf.exists()) / 1024
        total_str = f"{total_kb:.1f} KB" if total_kb < 1024 else f"{total_kb/1024:.2f} MB"

        # ── Dialog konfirmasi ─────────────────────────────────────────────────
        dlg = tk.Toplevel(self.root); dlg.title("Clear Logs & History"); dlg.configure(bg=BG)
        dlg.resizable(False, False); dlg.attributes("-topmost", True)
        hdr = tk.Frame(dlg, bg=BG2, height=48); hdr.pack(fill="x"); hdr.pack_propagate(False)
        hdr_inner = tk.Frame(hdr, bg=BG2, padx=20); hdr_inner.pack(fill="both", expand=True)
        tk.Label(hdr_inner, text="\u2015  Clear Logs & History",
                 bg=BG2, fg=WARN, font=(f, 12, "bold")).pack(side="left", fill="y")
        tk.Frame(dlg, bg=BORDER, height=1).pack(fill="x")
        body = tk.Frame(dlg, bg=BG, padx=24, pady=18); body.pack(fill="both", expand=True)
        info_box = tk.Frame(body, bg=BG3, padx=14, pady=10); info_box.pack(fill="x", pady=(0,14))
        for label, val in [("Terminal",  f"{t['type']} — {t['name']}"),
                           ("Log files", f"{len(log_files)} file"),
                           ("History",   f"{len(hcs_files)} file (.hcs/.hcc)"),
                           ("Total size", total_str)]:
            row = tk.Frame(info_box, bg=BG3); row.pack(fill="x", pady=1)
            tk.Label(row, text=f"{label:<12}", bg=BG3, fg=FG3, font=(f, 9),
                     anchor="w", width=12).pack(side="left")
            tk.Label(row, text=val, bg=BG3, fg=FG2, font=(fm, 9), anchor="w").pack(side="left")
        tk.Frame(info_box, bg=BORDER, height=1).pack(fill="x", pady=(8,6))
        for lf in all_files[:8]:
            try:    _display = str(lf.relative_to(terminal_path))
            except: _display = lf.name
            tk.Label(info_box, text=f"  {_display}", bg=BG3, fg=FG3,
                     font=(fm, 8), anchor="w").pack(anchor="w")
        if len(all_files) > 8:
            tk.Label(info_box, text=f"  \u2026 and {len(all_files)-8} more file(s)",
                     bg=BG3, fg=FG3, font=(f, 8), anchor="w").pack(anchor="w")
        tk.Label(body,
                 text="All log and history (.hcs/.hcc) files will be permanently deleted.\nThis action cannot be undone.",
                 bg=BG, fg=FG2, font=(f, 9), justify="left", anchor="w").pack(anchor="w", pady=(0,4))
        tk.Frame(dlg, bg=BORDER, height=1).pack(fill="x")
        foot = tk.Frame(dlg, bg=BG2, height=50); foot.pack(fill="x"); foot.pack_propagate(False)
        fi = tk.Frame(foot, bg=BG2, padx=14); fi.pack(fill="both", expand=True)

        def _confirm():
            dlg.destroy()
            deleted, errors = 0, []
            for lf in all_files:
                try: lf.unlink(); deleted += 1
                except Exception as e: errors.append(f"{lf.name}: {e}")
            t_ref = self._terminal(silent=True)
            if t_ref:
                self._reload_files(t_ref)
            self._status(f"{deleted} file(s) (log & history) deleted from {t['name']}.")
            # Result popup
            res = tk.Toplevel(self.root); res.title("Logs & History Cleared"); res.configure(bg=BG)
            res.resizable(False, False); res.attributes("-topmost", True)
            ok_icon = "\u2713" if not errors else "\u26a0"
            ok_fg   = "#5ecf3e" if not errors else WARN
            hdr2 = tk.Frame(res, bg=BG2, height=48); hdr2.pack(fill="x"); hdr2.pack_propagate(False)
            hdr2i = tk.Frame(hdr2, bg=BG2, padx=20); hdr2i.pack(fill="both", expand=True)
            tk.Label(hdr2i, text=f"{ok_icon}  Logs & History Cleared",
                     bg=BG2, fg=ok_fg, font=(f, 12, "bold")).pack(side="left", fill="y")
            tk.Frame(res, bg=BORDER, height=1).pack(fill="x")
            body2 = tk.Frame(res, bg=BG, padx=24, pady=18); body2.pack(fill="both", expand=True)
            tk.Label(body2, text=ok_icon, bg=BG, fg=ok_fg,
                     font=(f, 22)).grid(row=0, column=0, rowspan=2, padx=(0,16), sticky="n")
            tk.Label(body2, text=f"{deleted} file(s) deleted successfully.",
                     bg=BG, fg=FG, font=(f, 11, "bold"), anchor="w").grid(row=0, column=1, sticky="w")
            err_text = ("\n".join(errors[:3]) if errors else f"Dari terminal: {t['name']}")
            tk.Label(body2, text=err_text, bg=BG, fg=FG2 if not errors else DANGER,
                     font=(f, 9), anchor="w", wraplength=340).grid(row=1, column=1, sticky="w", pady=(4,0))
            body2.columnconfigure(1, weight=1)
            tk.Frame(res, bg=BORDER, height=1).pack(fill="x")
            foot2 = tk.Frame(res, bg=BG2, height=44); foot2.pack(fill="x"); foot2.pack_propagate(False)
            fi2 = tk.Frame(foot2, bg=BG2, padx=12); fi2.pack(fill="both", expand=True)
            oh, _ = make_pill_btn(fi2, "OK", res.destroy, bg=BG3, fg=FG, hover_bg=BG4,
                                  font_size=9, padx=20, pady=6, radius=7)
            oh.pack(side="right", pady=8)
            res.update_idletasks(); self._center_win(res); res.deiconify(); res.lift(); res.focus_force()

        confirm_h, _ = make_pill_btn(fi, "\u2015  Clear All", _confirm,
                                     bg="#261a05", fg=WARN, hover_bg="#3d2a08",
                                     font_size=10, padx=20, pady=7, radius=7)
        confirm_h.pack(side="right", pady=8, padx=(0,6))
        cancel_h, _ = make_pill_btn(fi, "Cancel", dlg.destroy, bg=BG3, fg=FG, hover_bg=BG4,
                                    font_size=9, padx=20, pady=6, radius=7)
        cancel_h.pack(side="right", pady=8)
        dlg.update_idletasks(); self._center_win(dlg); dlg.deiconify(); dlg.lift(); dlg.focus_force()

    # ── Browse ────────────────────────────────────────────────────────────────
    def browse_files(self):
        t = self._terminal()
        if not t:
            return
        target = Path(t["path"])
        try:
            if shutil.which("pcmanfm"):
                import subprocess; subprocess.Popen(["pcmanfm", str(target)])
            elif shutil.which("xdg-open"):
                import subprocess; subprocess.Popen(["xdg-open", str(target)])
            else:
                themed_popup(self.root, "info", "Path Terminal", str(target))
        except Exception as e:
            themed_popup(self.root, "error", "Error", str(e))

    # ── wget Download ─────────────────────────────────────────────────────────
    def wget_download(self):
        import shutil as sh_
        if not sh_.which("wget"):
            themed_popup(self.root, "error", "wget not found",
                "wget is not installed.\n\nRun:\n  sudo apt install wget")
            return
        PLACEHOLDER = self._wget_placeholder
        raw = self.wget_var.get().strip()
        if not raw or raw == PLACEHOLDER:
            self.wget_status_var.set("Paste a URL first."); return
        import re
        url_match = re.search(r"https?://[^\s\"']+", raw)
        if not url_match:
            self.wget_status_var.set("URL not found."); return
        url = url_match.group(0).strip("\"' ")
        DOCS_DIR.mkdir(exist_ok=True)
        self.wget_status_var.set("Downloading\u2026")
        self._wget_pct_var.set("")
        self._progress.set(0.0)
        auto_extract = self.auto_extract_var.get()

        def _on_success(downloaded):
            def _finish():
                self.wget_var.set("")
                self._progress.set(1.0)
                self._wget_pct_var.set("100%")
                if downloaded and auto_extract and be.is_archive(downloaded):
                    self.wget_status_var.set(f"Extracting {downloaded.name}\u2026")
                    ok, msg = be.extract_file(downloaded, DOCS_DIR)
                    if ok:
                        self.wget_status_var.set("Done + extracted \u2192 Documents/")
                        self._status(f"wget + extract done: {downloaded.name}")
                        themed_popup(self.root, "success", "Done",
                            f"File downloaded and extracted to:\n{DOCS_DIR}\n\nFile: {downloaded.name}")
                    else:
                        self.wget_status_var.set("Download OK, extract failed.")
                        themed_popup(self.root, "warning", "Extract Failed",
                            f"File downloaded to {DOCS_DIR}\n\nBut extraction failed:\n{msg}")
                else:
                    fname = downloaded.name if downloaded else ""
                    self.wget_status_var.set(f"Done \u2192 Documents/{fname}")
                    self._status(f"wget done \u2192 {DOCS_DIR}")
                    themed_popup(self.root, "success", "Download Complete",
                        f"File downloaded to:\n{DOCS_DIR}")
            self.root.after(0, _finish)

        def _on_error(err):
            self.root.after(0, lambda: (
                self.wget_status_var.set(f"Failed: {err[:55]}"),
                self._progress.set(0.0)))

        def _on_timeout():
            self.root.after(0, lambda: self.wget_status_var.set("Timeout \u2014 >120 seconds."))

        be.wget_download_bg(url, DOCS_DIR, _on_success, _on_error, _on_timeout)

    # ── Open MT / MetaEditor ──────────────────────────────────────────────────
    def open_mt(self):
        t = self._terminal()
        if not t:
            return
        exe = be.find_exe(t, "terminal.exe", "terminal64.exe")
        if exe is None:
            name = "terminal64.exe" if t["type"] == "MT5" else "terminal.exe"
            themed_popup(self.root, "error", f"{name} not found",
                f"File {name} not found for {t['name']} ({t['type']})\n"
                f"Folder: {t['path']}")
            return
        self._wine_launch(exe, f"{t['name']} ({t['type']})")

    def open_metaeditor(self):
        t = self._terminal()
        if not t:
            return
        exe = be.find_exe(t, "metaeditor.exe", "MetaEditor64.exe")
        if exe is None:
            name = "MetaEditor64.exe" if t["type"] == "MT5" else "metaeditor.exe"
            themed_popup(self.root, "error", f"{name} not found",
                f"File {name} not found for {t['name']} ({t['type']})\n"
                f"Folder: {t['path']}")
            return
        self._wine_launch(exe, f"MetaEditor {t['name']} ({t['type']})")

    def _wine_launch(self, exe_path, label: str):
        self._status(f"Opening {label}\u2026")
        def _on_success():
            self.root.after(0, lambda: self._status(f"{label} is opening."))
        def _on_error(reason):
            if reason == "wine_not_found":
                self.root.after(0, lambda: themed_popup(self.root, "error",
                    "Wine Not Found",
                    "The 'wine' command is not available.\n"
                    "Install wine first:\n  sudo apt install wine"))
            else:
                self.root.after(0, lambda r=reason: themed_popup(self.root, "error",
                    "Failed", f"Cannot open {label}:\n{r}"))
        be.wine_launch_bg(exe_path, _on_success, _on_error)

    # ── Uninstall MT ──────────────────────────────────────────────────────────
    def _uninstall_autostart_warning(self, t):
        f = self._font
        win = tk.Toplevel(self.root); win.title("Cannot Uninstall")
        win.configure(bg=BG); win.resizable(False, False); win.attributes("-topmost", True)
        body = tk.Frame(win, bg=BG, padx=28, pady=22); body.pack(fill="both", expand=True)
        hdr = tk.Frame(body, bg=BG); hdr.pack(fill="x", pady=(0, 12))
        tk.Label(hdr, text="⚠", bg=BG, fg=WARN, font=(f, 22)).pack(side="left", padx=(0, 14))
        col = tk.Frame(hdr, bg=BG); col.pack(side="left", fill="x", expand=True)
        tk.Label(col, text="Autostart is Enabled", bg=BG, fg=FG,
                 font=(f, 12, "bold"), anchor="w").pack(anchor="w")
        tk.Label(col, text=f"{t['name']}  ·  {t['type']}",
                 bg=BG, fg=FG3, font=(f, 9), anchor="w").pack(anchor="w")
        tk.Label(body, text="Please disable Autostart before uninstalling this terminal.",
                 bg=BG, fg=FG2, font=(f, 9), justify="left", anchor="w",
                 wraplength=420).pack(anchor="w", pady=(0, 4))
        tk.Frame(win, bg=BORDER, height=1).pack(fill="x")
        foot = tk.Frame(win, bg=BG2, height=48); foot.pack(fill="x"); foot.pack_propagate(False)
        fi = tk.Frame(foot, bg=BG2, padx=12); fi.pack(fill="both", expand=True)

        def _disable_and_continue():
            be.autostart_set(
                t, False,
                lambda t_: be.find_exe(t_, "terminal.exe", "terminal64.exe"))
            sel = self.term_tree.selection()
            if sel:
                self._as_state_cache[sel[0]] = False
            self._update_as_switch(t)
            self._draw_as_canvas()
            win.destroy()
            self.uninstall_ea_exe()   # autostart kini OFF → lanjut ke konfirmasi

        cont_h, _ = make_pill_btn(fi, "Disable Autostart & Continue", _disable_and_continue,
                                  bg="#2a1a00", fg="#e07b00", hover_bg="#3d2800",
                                  font_size=9, padx=18, pady=6, radius=7)
        cont_h.pack(side="right", pady=8, padx=(0, 6))
        cancel_h, _ = make_pill_btn(fi, "Cancel", win.destroy, bg=BG3, fg=FG, hover_bg=BG4,
                                    font_size=9, padx=20, pady=6, radius=7)
        cancel_h.pack(side="right", pady=8)
        win.update_idletasks(); self._center_win(win); win.deiconify(); win.lift(); win.focus_force()

    def uninstall_ea_exe(self):
        t = self._terminal()
        if not t:
            return
        if be.autostart_is_on(t):
            self._uninstall_autostart_warning(t)
            return
        f  = self._font
        terminal_path = Path(t["path"])
        uninstall_exe = None

        if t["type"] == "MT4":
            install_path = t.get("install_path")
            if install_path:
                candidate = Path(install_path) / "uninstall.exe"
                if candidate.exists():
                    uninstall_exe = candidate
            if uninstall_exe is None:
                candidate = terminal_path / "uninstall.exe"
                if candidate.exists():
                    uninstall_exe = candidate
            if uninstall_exe is None:
                ip_str = str(install_path) if install_path else "(failed to parse origin.txt)"
                themed_popup(self.root, "error", "Uninstall.exe not found",
                    f"File Uninstall.exe could not be found for terminal:\n"
                    f"{t['name']} (MT4)\n\nInstall path from origin.txt:\n{ip_str}\n\n"
                    f"AppData folder:\n{terminal_path}")
                return
        else:
            candidate = terminal_path / "uninstall.exe"
            if candidate.exists():
                uninstall_exe = candidate

        if uninstall_exe is None:
            themed_popup(self.root, "error", "Uninstall.exe not found",
                f"File Uninstall.exe could not be found for terminal:\n"
                f"{t['name']} ({t['type']})\n\nChecked folder:\n{terminal_path}")
            return

        win = tk.Toplevel(self.root); win.title("Confirm Uninstall MT")
        win.configure(bg=BG); win.resizable(False, False); win.attributes("-topmost", True)
        body = tk.Frame(win, bg=BG, padx=28, pady=22); body.pack(fill="both", expand=True)
        hdr = tk.Frame(body, bg=BG); hdr.pack(fill="x", pady=(0,14))
        tk.Label(hdr, text="\u26a0", bg=BG, fg="#e07b00", font=(f, 22)).pack(side="left", padx=(0,14))
        title_col = tk.Frame(hdr, bg=BG); title_col.pack(side="left", fill="x", expand=True)
        tk.Label(title_col, text="Uninstall MT", bg=BG, fg=FG,
                 font=(f, 12, "bold"), anchor="w").pack(anchor="w")
        tk.Label(title_col, text=f"{t['name']}  ·  {t['type']}",
                 bg=BG, fg=FG3, font=(f, 9), anchor="w").pack(anchor="w")
        info_box = tk.Frame(body, bg=BG3, padx=12, pady=10); info_box.pack(fill="x", pady=(0,14))
        tk.Label(info_box, text="FILE", bg=BG3, fg=FG3, font=(f, 8), anchor="w").pack(anchor="w")
        exe_path_str = str(uninstall_exe)
        home_str = str(Path.home())
        if exe_path_str.startswith(home_str):
            exe_path_str = "~" + exe_path_str[len(home_str):]
        tk.Label(info_box, text=exe_path_str, bg=BG3, fg=ACCENT2,
                 font=(self._font_mono, 9), anchor="w", wraplength=420, justify="left").pack(anchor="w")
        tk.Label(body, text="The uninstall process will run via Wine.\n"
                             "Make sure the MetaTrader terminal is closed before continuing.",
                 bg=BG, fg=FG2, font=(f, 9), justify="left", anchor="w",
                 wraplength=440).pack(anchor="w", pady=(0,4))
        tk.Frame(win, bg=BORDER, height=1).pack(fill="x")
        foot = tk.Frame(win, bg=BG2, height=48); foot.pack(fill="x"); foot.pack_propagate(False)
        fi = tk.Frame(foot, bg=BG2, padx=12); fi.pack(fill="both", expand=True)

        def _run_uninstall():
            win.destroy()
            self._status(f"Running uninstall {t['name']} in background\u2026")
            def _on_done(rc, t_):
                self.root.after(800, lambda: self.scan_terminals(silent=True))
                self.root.after(0, lambda: self._status(
                    f"Uninstall {t_['name']} finished (rc={rc})."))
            def _on_wine():
                self.root.after(0, lambda: themed_popup(self.root, "error",
                    "Wine Not Found",
                    "The 'wine' command is not available.\nInstall wine: sudo apt install wine"))
            def _on_err(e):
                self.root.after(0, lambda err=e: themed_popup(self.root, "error",
                    "Failed to run uninstall", str(err)))
            be.run_uninstall_bg(uninstall_exe, t, _on_done, _on_wine, _on_err)

        run_h, _ = make_pill_btn(fi, "\u26a0  Continue Uninstall", _run_uninstall,
                                  bg="#2a1a00", fg="#e07b00", hover_bg="#3d2800",
                                  font_size=9, padx=20, pady=6, radius=7)
        run_h.pack(side="right", pady=8, padx=(0,6))
        cancel_h, _ = make_pill_btn(fi, "Cancel", win.destroy, bg=BG3, fg=FG, hover_bg=BG4,
                                    font_size=9, padx=20, pady=6, radius=7)
        cancel_h.pack(side="right", pady=8)
        win.update_idletasks(); self._center_win(win); win.deiconify(); win.lift(); win.focus_force()

    # ── Install MT dropdown ────────────────────────────────────────────────────
    def _make_dropdown(self, anchor_widget, items, flag_attr, direction="down"):
        if getattr(self, flag_attr, False):
            return
        setattr(self, flag_attr, True)
        f = self._font
        popup = tk.Toplevel(self.root)
        popup.wm_overrideredirect(True); popup.attributes("-topmost", True)
        outer = tk.Frame(popup, bg=BORDER2, padx=1, pady=1); outer.pack()
        inner = tk.Frame(outer, bg=BG3); inner.pack()
        _closed = [False]

        def _close():
            if _closed[0]: return
            _closed[0] = True
            setattr(self, flag_attr, False)
            try: popup.destroy()
            except Exception: pass

        def _make_item(text, cmd):
            row = tk.Frame(inner, bg=BG3, cursor="hand2"); row.pack(fill="x")
            lbl = tk.Label(row, text=text, bg=BG3, fg=FG,
                           font=(f, 10), anchor="w", padx=16, pady=8)
            lbl.pack(fill="x")
            def _enter(_): row.config(bg=BG4); lbl.config(bg=BG4, fg=ACCENT)
            def _leave(_): row.config(bg=BG3); lbl.config(bg=BG3, fg=FG)
            def _click(_):
                _close(); self.root.update(); self.root.after(50, cmd)
            for w_ in (row, lbl):
                w_.bind("<Enter>", _enter); w_.bind("<Leave>", _leave)
                w_.bind("<Button-1>", _click)

        for text, cmd in items:
            _make_item(text, cmd)

        popup.update_idletasks()
        bx = anchor_widget.winfo_rootx(); by = anchor_widget.winfo_rooty()
        bh = anchor_widget.winfo_height()
        if direction == "up":
            ph = popup.winfo_reqheight()
            popup.wm_geometry(f"+{bx}+{by - ph - 2}")
        else:
            popup.wm_geometry(f"+{bx}+{by + bh + 2}")

        def _on_press_outside(event):
            if _closed[0]: return
            try:
                wx = popup.winfo_rootx(); wy = popup.winfo_rooty()
                ww = popup.winfo_width(); wh = popup.winfo_height()
                if not (wx <= event.x_root <= wx + ww and wy <= event.y_root <= wy + wh):
                    _close()
            except Exception:
                _close()

        self.root.bind_all("<ButtonPress-1>", _on_press_outside, add=True)

        def _poll():
            if _closed[0]: return
            try:
                mx = self.root.winfo_pointerx(); my = self.root.winfo_pointery()
                wx = popup.winfo_rootx(); wy = popup.winfo_rooty()
                ww = popup.winfo_width(); wh = popup.winfo_height()
                margin = 80
                if not (wx-margin <= mx <= wx+ww+margin and wy-margin <= my <= wy+wh+margin):
                    _close(); return
                popup.after(150, _poll)
            except Exception:
                _close()

        popup.after(300, _poll)

        def _cleanup(_=None):
            try: self.root.unbind_all("<ButtonPress-1>")
            except Exception: pass
            setattr(self, flag_attr, False)

        popup.bind("<Destroy>", _cleanup)

    def _manage_ea_menu(self):
        self._make_dropdown(
            self._manage_ea_btn_holder,
            [("\u2191  Install Expert Advisor", self.install_ea),
             ("\u2191  Install Indicator",       self.install_indicator),
             ("\u232b  Delete EA / Indicator",   self.uninstall_file)],
            "_manage_ea_popup_open")

    def _manage_mt_menu(self):
        self._make_dropdown(
            self._manage_mt_btn_holder,
            [("\u2b07  Install MetaTrader",   self.install_mt),
             ("\u2398  Duplicate MetaTrader", self.duplicate_mt),
             ("\u26d4  Uninstall MetaTrader", self.uninstall_ea_exe)],
            "_manage_mt_popup_open", direction="up")

    def _utility_menu(self):
        self._make_dropdown(
            self._utility_btn_holder,
            [("\u2015  Clear Logs & History", self.clear_logs_and_history),
             ("\u270e  Open MetaEditor", self.open_metaeditor)],
            "_utility_popup_open")

    # ── Install MT ────────────────────────────────────────────────────────────
    def install_mt(self):
        import threading, shutil as sh_
        f  = self._font
        fm = self._font_mono

        win = tk.Toplevel(self.root)
        win.title("Install MetaTrader")
        win.configure(bg=BG)
        win.resizable(True, True)
        # Tidak set topmost agar window installer MT bisa muncul di atas
        win.update_idletasks()
        rx = self.root.winfo_x() + self.root.winfo_width()  // 2 - 340
        ry = self.root.winfo_y() + self.root.winfo_height() // 2 - 260
        win.geometry(f"680x520+{rx}+{ry}")
        win.minsize(520, 400)
        win.deiconify()

        # ── Header ──
        hdr = tk.Frame(win, bg=BG2, height=48)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        hdr_inner = tk.Frame(hdr, bg=BG2, padx=20)
        hdr_inner.pack(fill="both", expand=True)
        tk.Label(hdr_inner, text="\u2b07  Install MetaTrader",
                 bg=BG2, fg=FG, font=(f, 12, "bold")).pack(side="left", fill="y")
        tk.Frame(win, bg=BORDER, height=1).pack(fill="x")

        # ── Filter bar ──
        filter_bar = tk.Frame(win, bg=BG2, padx=14, pady=7)
        filter_bar.pack(fill="x")
        tk.Frame(win, bg=BORDER, height=1).pack(fill="x")

        ver_var    = tk.StringVar(value="Semua")
        search_var = tk.StringVar()
        _filter_btns = {}
        _downloading = [False]

        tk.Label(filter_bar, text="Filter:", bg=BG2, fg=FG3, font=(f, 9)).pack(side="left")
        for lbl in ("Semua", "MT4", "MT5"):
            b = tk.Label(filter_bar, text=lbl, bg=ACCENT_DIM if lbl == "Semua" else BG3,
                         fg=ACCENT if lbl == "Semua" else FG3,
                         font=(f, 9), padx=10, pady=4, cursor="hand2")
            b.pack(side="left", padx=(4, 0))
            _filter_btns[lbl] = b

        def _set_filter(lbl):
            ver_var.set(lbl)
            for k, btn in _filter_btns.items():
                btn.config(bg=ACCENT_DIM if k == lbl else BG3,
                           fg=ACCENT     if k == lbl else FG3)
            _build_broker_list()

        for lbl in ("Semua", "MT4", "MT5"):
            _filter_btns[lbl].bind("<Button-1>", lambda e, l=lbl: _set_filter(l))

        tk.Frame(filter_bar, bg=BORDER2, width=1).pack(side="left", fill="y", padx=8, pady=2)
        tk.Label(filter_bar, text="\u26b2", bg=BG2, fg=FG3, font=(f, 9)).pack(side="left")
        tk.Entry(filter_bar, textvariable=search_var,
                 bg=BG3, fg=FG, insertbackground=ACCENT, relief="flat",
                 font=(f, 9), highlightthickness=0, width=16).pack(
                 side="left", padx=(4, 0), ipady=4)
        search_var.trace_add("write", lambda *_: _build_broker_list())

        # ── Scrollable broker grid ──
        grid_outer = tk.Frame(win, bg=BG)
        grid_outer.pack(fill="both", expand=True, padx=10, pady=(8, 4))

        canvas_grid = tk.Canvas(grid_outer, bg=BG, highlightthickness=0)
        sb_grid     = RoundScrollbar(grid_outer, command=canvas_grid.yview)
        sb_grid.pack(side="right", fill="y")
        canvas_grid.pack(side="left", fill="both", expand=True)
        canvas_grid.configure(yscrollcommand=sb_grid.set)

        broker_inner = tk.Frame(canvas_grid, bg=BG)
        broker_win_id = canvas_grid.create_window((0, 0), window=broker_inner, anchor="nw")

        def _on_broker_configure(e=None):
            canvas_grid.configure(scrollregion=canvas_grid.bbox("all"))
        broker_inner.bind("<Configure>", _on_broker_configure)

        def _on_canvas_resize(e):
            canvas_grid.itemconfig(broker_win_id, width=e.width)
        canvas_grid.bind("<Configure>", _on_canvas_resize)

        # Scroll via mouse — bind ke semua widget agar lebih responsif
        def _do_scroll(e):
            delta = -3 if (e.num == 4 or e.delta > 0) else 3
            canvas_grid.yview_scroll(delta, "units")
            return "break"

        for widget in (canvas_grid, broker_inner, win):
            for ev in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                widget.bind(ev, _do_scroll, add=True)

        def _rebind_scroll(parent):
            """Bind scroll ke semua child widget secara rekursif."""
            for child in parent.winfo_children():
                for ev in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                    child.bind(ev, _do_scroll, add=True)
                _rebind_scroll(child)

        # ── Fetch broker list dari GitHub saat window dibuka ──
        _broker_data = [None]   # None = belum fetch, [] = gagal, [...] = sukses

        def _show_loading():
            for w in broker_inner.winfo_children():
                w.destroy()
            fr = tk.Frame(broker_inner, bg=BG)
            fr.pack(expand=True, pady=40)
            tk.Label(fr, text="\u29d7  Fetching broker list from GitHub\u2026",
                     bg=BG, fg=FG3, font=(f, 10)).pack()
            broker_inner.update_idletasks()
            canvas_grid.configure(scrollregion=canvas_grid.bbox("all"))

        def _show_error(msg):
            for w in broker_inner.winfo_children():
                w.destroy()
            fr = tk.Frame(broker_inner, bg=BG)
            fr.pack(expand=True, pady=40)
            tk.Label(fr, text="\u26a0  Failed to load broker list",
                     bg=BG, fg=WARN, font=(f, 10, "bold")).pack()
            tk.Label(fr, text=msg, bg=BG, fg=FG3, font=(f, 9),
                     wraplength=420, justify="center").pack(pady=(4, 12))
            retry_h, _ = make_pill_btn(fr, "\u21ba  Coba Lagi", _start_fetch,
                                        bg=BG3, fg=FG, hover_bg=BG4,
                                        font_size=9, padx=16, pady=6, radius=7)
            retry_h.pack()

        def _start_fetch():
            _broker_data[0] = None
            _show_loading()
            import queue as _q
            q = be.fetch_broker_list_bg()

            def _poll():
                try:
                    kind, val = q.get_nowait()
                    if kind == "ok":
                        _broker_data[0] = val
                        _build_broker_list()
                    else:
                        _broker_data[0] = []
                        _show_error(val)
                except _q.Empty:
                    win.after(150, _poll)  # cek lagi 150ms kemudian

            win.after(150, _poll)

        def _build_broker_list(*_):
            data = _broker_data[0]
            if data is None:
                return   # masih loading
            if data == []:
                return   # error sudah ditampilkan
            for w in broker_inner.winfo_children():
                w.destroy()
            ver    = ver_var.get()
            search = search_var.get().strip().lower()
            brokers = [b for b in data
                       if (ver == "Semua" or b[0] == ver)
                       and (not search or search in b[1].lower())]
            if not brokers:
                tk.Label(broker_inner, text="No results.",
                         bg=BG, fg=FG3, font=(f, 9)).pack(pady=20)
                return

            COLS = 3
            for idx, (version, name, url) in enumerate(brokers):
                r, c = divmod(idx, COLS)
                badge_col = ACCENT3 if version == "MT4" else WARN

                card = tk.Frame(broker_inner, bg=BG3, cursor="hand2")
                card.grid(row=r, column=c, padx=5, pady=4, sticky="ew")
                broker_inner.columnconfigure(c, weight=1)

                top_row = tk.Frame(card, bg=BG3)
                top_row.pack(fill="x", padx=8, pady=(7, 2))
                badge_lbl = tk.Label(top_row, text=version, bg=badge_col, fg=BG,
                                     font=(f, 7, "bold"), padx=4, pady=1)
                badge_lbl.pack(side="left")

                tk.Label(card, text=name, bg=BG3, fg=FG,
                         font=(f, 10, "bold"), anchor="w",
                         padx=8).pack(fill="x", pady=(0, 7))

                def _all_widgets(w):
                    yield w
                    for ch in w.winfo_children():
                        yield from _all_widgets(ch)

                def _enter(e, c=card, bl=badge_lbl, bc=badge_col):
                    for w in _all_widgets(c):
                        if w is bl:
                            try: w.config(bg=bc)
                            except Exception: pass
                        else:
                            try: w.config(bg=BG4)
                            except Exception: pass
                def _leave(e, c=card, bl=badge_lbl, bc=badge_col):
                    for w in _all_widgets(c):
                        if w is bl:
                            try: w.config(bg=bc)
                            except Exception: pass
                        else:
                            try: w.config(bg=BG3)
                            except Exception: pass
                def _click(e, v=version, n=name, u=url):
                    if _downloading[0]:
                        status_var.set("\u23f3 Downloading, please wait.")
                        return
                    _confirm_download(v, n, u)

                for w_ in _all_widgets(card):
                    w_.bind("<Enter>",    _enter)
                    w_.bind("<Leave>",    _leave)
                    w_.bind("<Button-1>", _click)
                    for ev in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                        w_.bind(ev, _do_scroll, add=True)

            win.after(10, _on_broker_configure)

        # Fetch otomatis saat window terbuka
        _start_fetch()

        # ── Konfirmasi download ──
        def _confirm_download(version, name, url):
            """Tampilkan popup konfirmasi sebelum mulai download."""
            existing = be.broker_already_installed(name, version, self.terminals)
            if existing:
                self._broker_exists_dialog(win, version, name, existing)
                return
            dlg = tk.Toplevel(win)
            dlg.title("Confirm Install")
            dlg.configure(bg=BG)
            dlg.resizable(False, False)
            dlg.transient(win)
            dlg.update_idletasks()
            dx = win.winfo_rootx() + win.winfo_width()  // 2 - 200
            dy = win.winfo_rooty() + win.winfo_height() // 2 - 90
            dlg.geometry(f"400x180+{dx}+{dy}")
            dlg.deiconify()

            badge_col = ACCENT3 if version == "MT4" else WARN

            hdr = tk.Frame(dlg, bg=BG2, height=46)
            hdr.pack(fill="x"); hdr.pack_propagate(False)
            hdr_i = tk.Frame(hdr, bg=BG2, padx=18)
            hdr_i.pack(fill="both", expand=True)
            tk.Label(hdr_i, text="\u2b07  Confirm Install MetaTrader",
                     bg=BG2, fg=FG, font=(f, 11, "bold")).pack(side="left", fill="y")
            tk.Frame(dlg, bg=BORDER, height=1).pack(fill="x")

            body = tk.Frame(dlg, bg=BG, padx=22, pady=16)
            body.pack(fill="both", expand=True)

            info_row = tk.Frame(body, bg=BG)
            info_row.pack(fill="x")
            tk.Label(info_row, text=version, bg=badge_col, fg=BG,
                     font=(f, 8, "bold"), padx=6, pady=2).pack(side="left")
            tk.Label(info_row, text=f"  {name}", bg=BG, fg=FG,
                     font=(f, 11, "bold")).pack(side="left")

            tk.Frame(dlg, bg=BORDER, height=1).pack(fill="x")
            foot_d = tk.Frame(dlg, bg=BG2, height=46)
            foot_d.pack(fill="x"); foot_d.pack_propagate(False)
            fi_d = tk.Frame(foot_d, bg=BG2, padx=12)
            fi_d.pack(fill="both", expand=True)

            def _do_install():
                dlg.destroy()
                _start_download(version, name, url)

            ok_h, _ = make_pill_btn(fi_d, "\u2b07  Yes, Install", _do_install,
                                     bg="#0a1f0a", fg="#5ecf3e", hover_bg="#152e15",
                                     font_size=9, padx=18, pady=6, radius=7)
            ok_h.pack(side="right", pady=8, padx=(0, 6))
            cancel_h2, _ = make_pill_btn(fi_d, "Cancel", dlg.destroy,
                                          bg=BG3, fg=FG, hover_bg=BG4,
                                          font_size=9, padx=16, pady=6, radius=7)
            cancel_h2.pack(side="right", pady=8)
            try: dlg.grab_set()
            except Exception: pass
            dlg.focus_force()

        # ── Download & install handler ──
        def _start_download(version, name, url):
            if not sh_.which("wget"):
                status_var.set("\u26a0 wget not found. Run: sudo apt install wget")
                status_lbl.config(fg=WARN)
                return
            _downloading[0] = True
            prog_bar.set(0.05)
            status_var.set(f"Preparing download for {name}\u2026")
            status_lbl.config(fg=FG3)
            DOCS_DIR.mkdir(exist_ok=True)

            def _on_progress(msg):
                win.after(0, lambda: (status_var.set(msg), prog_bar.set(0.45)))

            def _on_success(exe_name, bname):
                def _done():
                    _downloading[0] = False
                    prog_bar.set(1.0)
                    status_var.set(
                        f"\u2713 {bname} — installer started. ")
                    status_lbl.config(fg="#5ecf3e")
                    self._status(f"Install MT {bname} started via Wine.")
                    self.root.after(5000, lambda: self.scan_terminals(silent=True))
                win.after(0, _done)

            def _on_error(msg):
                def _err():
                    _downloading[0] = False
                    prog_bar.set(0.0)
                    status_var.set(f"\u2717 {msg}")
                    status_lbl.config(fg=DANGER)
                win.after(0, _err)

            def _on_timeout():
                def _to():
                    _downloading[0] = False
                    prog_bar.set(0.0)
                    status_var.set("\u26a0 Timeout — download took too long (>5 min).")
                    status_lbl.config(fg=WARN)
                win.after(0, _to)

            be.wget_then_install_bg(url, DOCS_DIR, name,
                                    _on_progress, _on_success, _on_error, _on_timeout)

        # ── Divider + Browse section ──
        tk.Frame(win, bg=BORDER, height=1).pack(fill="x")
        browse_sec = tk.Frame(win, bg=BG2, padx=14, pady=10)
        browse_sec.pack(fill="x")

        tk.Label(browse_sec, text="OR USE A LOCAL INSTALLER FILE",
                 bg=BG2, fg=FG3, font=(f, 8), anchor="w").pack(fill="x", pady=(0, 6))

        file_row      = tk.Frame(browse_sec, bg=BG2)
        file_row.pack(fill="x")
        installer_var = tk.StringVar(value="")
        entry_border  = tk.Frame(file_row, bg=BORDER2, padx=1, pady=1)
        entry_border.pack(side="left", fill="x", expand=True, padx=(0, 8))
        tk.Entry(entry_border, textvariable=installer_var,
                 bg=BG3, fg=FG2, insertbackground=ACCENT, relief="flat",
                 font=(fm, 9), highlightthickness=0, state="readonly").pack(
                 fill="x", ipady=6, padx=1)

        def _pick_file():
            try: win.attributes("-topmost", False)
            except Exception: pass
            try: win.grab_release()
            except Exception: pass
            def _do_yad():
                result = be.yad_pick_file(title="Select MT Installer File",
                    filetypes=["*.exe"], start_dir=DOCS_DIR, root_widget=self.root)
                def _back():
                    win.lift(); win.focus_force()
                    if result:
                        installer_var.set(result)
                        entry_border.config(bg=ACCENT)
                        win.after(200, lambda: entry_border.config(bg=BORDER2))
                    try: win.grab_set()
                    except Exception: pass
                win.after(0, _back)
            threading.Thread(target=_do_yad, daemon=True).start()

        bh_, _ = make_pill_btn(file_row, "\u25a6 Browse", _pick_file,
                               bg=BG3, fg=FG, hover_bg=BG4,
                               font_size=9, padx=12, pady=6, radius=7)
        bh_.pack(side="left", padx=(0, 6))

        def _run_install_local():
            path = installer_var.get().strip()
            if not path:
                status_var.set("\u26a0  Select an installer file first.")
                status_lbl.config(fg=WARN); return
            if not Path(path).exists():
                status_var.set("\u26a0  File not found.")
                status_lbl.config(fg=DANGER); return
            # Window TIDAK ditutup — tetap terbuka agar user bisa install lagi
            status_var.set(f"\u25b6  Running installer: {Path(path).name}\u2026")
            status_lbl.config(fg=FG3)
            prog_bar.set(0.2)
            def _on_finish_local(done, qty, fname, errs):
                def _ui():
                    prog_bar.set(1.0)
                    if errs:
                        status_var.set(f"\u26a0  Finished with error: {errs[0][:60]}")
                        status_lbl.config(fg=WARN)
                    else:
                        status_var.set(f"\u2713  {fname} installed successfully.")
                        status_lbl.config(fg="#5ecf3e")
                    self._status(f"Local MT install finished: {done}/{qty} of {fname}")
                    self.root.after(800, lambda: self.scan_terminals(silent=True))
                win.after(0, _ui)
            be.run_mt_installer_bg(
                Path(path), 1, "",
                on_progress=None,
                on_finish=_on_finish_local,
            )

        run_h, _ = make_pill_btn(file_row, "\u2b07  Start Install", _run_install_local,
                                  bg="#0a1f0a", fg="#5ecf3e", hover_bg="#152e15",
                                  font_size=9, padx=14, pady=6, radius=7)
        run_h.pack(side="left")

        # ── Status + progress + footer ──
        tk.Frame(win, bg=BORDER, height=1).pack(fill="x")
        status_frame = tk.Frame(win, bg=BG2, padx=14, pady=5)
        status_frame.pack(fill="x")
        status_var = tk.StringVar(value="Select a broker to install.")
        status_lbl = tk.Label(status_frame, textvariable=status_var,
                              bg=BG2, fg=FG3, font=(f, 9), anchor="w")
        status_lbl.pack(side="left", fill="x", expand=True)
        prog_bar = ProgressBar(win, height=2, bg=BG4, fill=ACCENT)
        prog_bar.pack(fill="x")

        tk.Frame(win, bg=BORDER, height=1).pack(fill="x")
        foot = tk.Frame(win, bg=BG2, height=46)
        foot.pack(fill="x")
        foot.pack_propagate(False)
        fi = tk.Frame(foot, bg=BG2, padx=14)
        fi.pack(fill="both", expand=True)
        cancel_h, _ = make_pill_btn(fi, "Close", win.destroy, bg=BG3, fg=FG, hover_bg=BG4,
                                    font_size=9, padx=20, pady=6, radius=7)
        cancel_h.pack(side="right", pady=7)


    def _broker_exists_dialog(self, parent, version, name, existing):
        f = self._font
        dlg = tk.Toplevel(parent); dlg.title("Already Installed")
        dlg.configure(bg=BG); dlg.resizable(False, False)
        dlg.transient(parent); dlg.attributes("-topmost", True)
        body = tk.Frame(dlg, bg=BG, padx=26, pady=20); body.pack(fill="both", expand=True)
        hdr = tk.Frame(body, bg=BG); hdr.pack(fill="x", pady=(0, 12))
        tk.Label(hdr, text="⚠", bg=BG, fg=WARN, font=(f, 22)).pack(side="left", padx=(0, 14))
        col = tk.Frame(hdr, bg=BG); col.pack(side="left", fill="x", expand=True)
        tk.Label(col, text="Already Installed", bg=BG, fg=FG,
                 font=(f, 12, "bold"), anchor="w").pack(anchor="w")
        tk.Label(col, text=f"{name}  ·  {version}",
                 bg=BG, fg=FG3, font=(f, 9), anchor="w").pack(anchor="w")
        tk.Label(body,
                 text=f"{name} ({version}) is already installed as "
                      f"“{existing['name']}”.\n"
                      f"Please duplicate the existing one or choose another broker.",
                 bg=BG, fg=FG2, font=(f, 9), justify="left", anchor="w",
                 wraplength=420).pack(anchor="w", pady=(0, 4))
        tk.Frame(dlg, bg=BORDER, height=1).pack(fill="x")
        foot = tk.Frame(dlg, bg=BG2, height=48); foot.pack(fill="x"); foot.pack_propagate(False)
        fi = tk.Frame(foot, bg=BG2, padx=12); fi.pack(fill="both", expand=True)

        def _go_duplicate():
            dlg.destroy()
            try: parent.destroy()
            except Exception: pass
            self.duplicate_mt()

        dup_h, _ = make_pill_btn(fi, "⧉  Duplicate Existing", _go_duplicate,
                                 bg=ACCENT_DIM, fg=ACCENT, hover_bg="#1d2b36",
                                 font_size=9, padx=18, pady=6, radius=7)
        dup_h.pack(side="right", pady=8, padx=(0, 6))
        cancel_h, _ = make_pill_btn(fi, "Cancel", dlg.destroy, bg=BG3, fg=FG, hover_bg=BG4,
                                    font_size=9, padx=20, pady=6, radius=7)
        cancel_h.pack(side="right", pady=8)
        try: dlg.grab_set()
        except Exception: pass
        dlg.update_idletasks(); self._center_win(dlg); dlg.deiconify(); dlg.lift(); dlg.focus_force()

    # ── Duplicate MT ──────────────────────────────────────────────────────────
    def duplicate_mt(self):
        t = self._terminal(silent=False)
        if not t:
            return
        mt_type = t.get("type", "MT4")
        if mt_type == "MT4":
            src_root_str = t.get("install_path", "")
            linux_base   = Path.home() / ".wine/drive_c/Program Files (x86)"
        else:
            src_root_str = t.get("path", "")
            linux_base   = Path.home() / ".wine/drive_c/Program Files"

        src_folder = None
        if src_root_str:
            candidate = Path(src_root_str)
            if candidate.exists():
                src_folder = candidate
        if src_folder is None:
            terminal_path = Path(t.get("path", ""))
            for candidate in [terminal_path, terminal_path.parent]:
                if candidate.exists() and candidate.is_dir():
                    src_folder = candidate; break
        if src_folder is None or not src_folder.exists():
            themed_popup(self.root, "error", "Folder not found",
                f"MT installation folder could not be found for terminal:\n{t['name']}")
            return

        base_name = src_folder.name
        # Simplified flow: always make exactly one duplicate and go straight to
        # the folder-name prompt (no quantity selector, no custom-name toggle).
        self._run_mt_duplicate(src_folder, base_name, linux_base, 1, mt_type,
                               use_custom=True)

    def _run_mt_duplicate(self, src_folder, base_name, linux_base, qty, mt_type,
                          use_custom=False):
        """Progress window duplikasi. Jika use_custom=True, tampilkan dialog
        input nama folder sebelum tiap copy. Launch semua MT setelah semua
        copy selesai (atau yang sudah ter-copy jika dibatalkan)."""
        f  = self._font
        fm = self._font_mono

        # ── Progress window (dipanggil setelah nama terkumpul) ──
        def _launch_progress_win(custom_names_list):
            win = tk.Toplevel(self.root); win.title("Menduplikat MT")
            win.configure(bg=BG); win.resizable(False, False); win.update_idletasks()
            rx = self.root.winfo_x() + self.root.winfo_width()  // 2 - 240
            ry = self.root.winfo_y() + self.root.winfo_height() // 2 - 130
            win.geometry(f"480x260+{rx}+{ry}"); win.deiconify()
            body = tk.Frame(win, bg=BG, padx=28, pady=20); body.pack(fill="both", expand=True)
            icon_lbl  = tk.Label(body, text="\u2398", bg=BG, fg=WARN, font=(f, 22))
            icon_lbl.grid(row=0, column=0, rowspan=4, padx=(0,16), sticky="n")
            title_lbl = tk.Label(body, text="Memulai duplikat\u2026",
                                 bg=BG, fg=FG, font=(f, 11, "bold"), anchor="w")
            title_lbl.grid(row=0, column=1, sticky="w")
            dir_var = tk.StringVar(value="")
            dir_lbl = tk.Label(body, textvariable=dir_var, bg=BG, fg=FG3, font=(f, 8), anchor="w")
            dir_lbl.grid(row=1, column=1, sticky="w", pady=(2, 4))
            phase_var = tk.StringVar(value="")
            phase_lbl = tk.Label(body, textvariable=phase_var, bg=BG, fg=FG3, font=(f, 8), anchor="w")
            phase_lbl.grid(row=2, column=1, sticky="w", pady=(0, 6))
            prog_frame = tk.Frame(body, bg=BG); prog_frame.grid(row=3, column=1, sticky="ew")
            body.columnconfigure(1, weight=1)
            progress  = ProgressBar(prog_frame, height=3, bg=BG4, fill=WARN); progress.pack(fill="x")
            count_var = tk.StringVar(value=f"0 / {qty}")
            tk.Label(prog_frame, textvariable=count_var, bg=BG, fg=FG3, font=(f, 8)).pack(anchor="e", pady=(3,0))
            tk.Frame(win, bg=BORDER, height=1).pack(fill="x")
            foot = tk.Frame(win, bg=BG2, height=44); foot.pack(fill="x"); foot.pack_propagate(False)
            fi   = tk.Frame(foot, bg=BG2, padx=12); fi.pack(fill="both", expand=True)
            close_h, _ = make_pill_btn(fi, "Close", win.destroy, bg=BG3, fg=FG, hover_bg=BG4,
                                       font_size=9, padx=20, pady=6, radius=7)
            _cancelled = [False]

            def _do_cancel():
                _cancelled[0] = True
                icon_lbl.config(text="\u23f9", fg=WARN)
                title_lbl.config(
                    text="Cancelling\u2026 waiting for copy to finish, then launching the copied MT.",
                    fg=WARN)
                dir_var.set(""); phase_var.set("")
                cancel_h.pack_forget()

            cancel_h, _ = make_pill_btn(fi, "\u2715  Cancel", _do_cancel,
                                        bg="#2a0f0f", fg=DANGER, hover_bg="#3d1212",
                                        font_size=9, padx=20, pady=6, radius=7)
            cancel_h.pack(side="right", pady=8, padx=(0,6))

            def _on_copy_progress(i, total, dst_name):
                def _upd():
                    title_lbl.config(text=f"Copying {i+1} of {total}\u2026", fg=FG)
                    count_var.set(f"{i} / {total}")
                    progress.set((i / total) * 0.5 if total > 1 else 0.05)
                    dir_var.set(f"\u2192 {dst_name}")
                    phase_var.set("Phase 1/2: Copying folder\u2026")
                win.after(0, _upd)

            def _on_launch_progress(j, total, dst_name, exe_name):
                def _upd():
                    title_lbl.config(text=f"Running MT {j+1} of {total}\u2026", fg=FG)
                    count_var.set(f"{j+1} / {total}")
                    progress.set(0.5 + ((j + 1) / max(total, 1)) * 0.5)
                    dir_var.set(f"\u25b6 {dst_name}\\{exe_name}")
                    phase_var.set("Phase 2/2: Opening MetaTrader\u2026")
                win.after(0, _upd)

            def _on_finish(done_cnt, total, src_name, all_errors, was_cancelled):
                def _done():
                    progress.set(1.0); count_var.set(f"{done_cnt} / {total}")
                    dir_var.set(""); phase_var.set("")
                    cancel_h.pack_forget(); close_h.pack(side="right", pady=8)
                    if was_cancelled:
                        icon_lbl.config(text="\u23f9", fg=WARN)
                        title_lbl.config(
                            text=f"Cancelled. {done_cnt} duplicate(s) copied & opened.", fg=WARN)
                    elif all_errors:
                        icon_lbl.config(text="\u26a0", fg=WARN)
                        title_lbl.config(text=f"Finished with {len(all_errors)} error(s).", fg=WARN)
                        dir_lbl.config(text="\n".join(all_errors[:3]), fg=DANGER)
                    else:
                        icon_lbl.config(text="\u2713", fg=WARN)
                        title_lbl.config(
                            text=f"{done_cnt} duplicate(s) created & launched.\n Please Scan MetaTrader",
                            fg=FG)
                        dir_lbl.config(text="Auto-scan started.", fg=FG2)
                    self._status(f"Duplicate MT finished: {done_cnt}/{total} of {src_name}")
                    self.root.after(800, lambda: self.scan_terminals(silent=True))
                win.after(0, _done)

            be.run_mt_duplicate_bg(src_folder, base_name, linux_base, qty, mt_type,
                                   _on_copy_progress, _on_launch_progress,
                                   _on_finish, _cancelled,
                                   custom_names=custom_names_list)

        # ── Jika custom nama: tampilkan dialog input nama satu per satu ──
        if use_custom:
            custom_names = []
            _abort = [False]

            def _ask_name(idx, callback):
                """Tampilkan dialog input nama untuk duplikat ke-idx."""
                dlg = tk.Toplevel(self.root)
                dlg.title(f"Duplicate Name {idx + 1} of {qty}")
                dlg.configure(bg=BG); dlg.resizable(False, False)
                dlg.attributes("-topmost", True)
                dlg.update_idletasks()
                rx = self.root.winfo_x() + self.root.winfo_width()  // 2 - 210
                ry = self.root.winfo_y() + self.root.winfo_height() // 2 - 90
                dlg.geometry(f"420x180+{rx}+{ry}"); dlg.deiconify()

                hdr = tk.Frame(dlg, bg=BG2, height=42); hdr.pack(fill="x"); hdr.pack_propagate(False)
                hdr_i = tk.Frame(hdr, bg=BG2, padx=16); hdr_i.pack(fill="both", expand=True)
                tk.Label(hdr_i, text=f"\u270e  Duplicate Folder Name {idx + 1} / {qty}",
                         bg=BG2, fg=FG, font=(f, 10, "bold")).pack(side="left", fill="y")
                tk.Frame(dlg, bg=BORDER, height=1).pack(fill="x")

                body2 = tk.Frame(dlg, bg=BG, padx=20, pady=14); body2.pack(fill="both", expand=True)
                default_name = f"{base_name} {idx + 2}"
                tk.Label(body2, text="Folder name  (leave empty = default name)",
                         bg=BG, fg=FG3, font=(f, 8), anchor="w").pack(fill="x")
                entry_border = tk.Frame(body2, bg=BORDER2, padx=1, pady=1)
                entry_border.pack(fill="x", pady=(4, 0))
                name_entry = tk.Entry(entry_border, bg=BG3, fg=FG, insertbackground=ACCENT,
                                      relief="flat", font=(fm, 10), highlightthickness=0)
                name_entry.pack(fill="x", ipady=7, padx=1)
                name_entry.insert(0, default_name)
                name_entry.select_range(0, "end")
                name_entry.focus_set()

                tk.Frame(dlg, bg=BORDER, height=1).pack(fill="x")
                foot2 = tk.Frame(dlg, bg=BG2, height=44); foot2.pack(fill="x"); foot2.pack_propagate(False)
                fi2 = tk.Frame(foot2, bg=BG2, padx=12); fi2.pack(fill="both", expand=True)

                def _confirm():
                    val = name_entry.get().strip() or default_name
                    dlg.destroy()
                    callback(val)

                def _cancel_all():
                    _abort[0] = True
                    dlg.destroy()
                    callback(None)

                ok_h, _ = make_pill_btn(fi2, "\u2713  OK", _confirm,
                                        bg="#0d1a0d", fg=ACCENT3, hover_bg="#142814",
                                        font_size=9, padx=18, pady=6, radius=7)
                ok_h.pack(side="right", pady=7, padx=(0,6))
                cx_h, _ = make_pill_btn(fi2, "\u2715  Cancel All", _cancel_all,
                                        bg="#2a0f0f", fg=DANGER, hover_bg="#3d1212",
                                        font_size=9, padx=14, pady=6, radius=7)
                cx_h.pack(side="right", pady=7)
                name_entry.bind("<Return>", lambda _: _confirm())
                name_entry.bind("<Escape>", lambda _: _cancel_all())
                try: dlg.grab_set()
                except Exception: pass

            def _collect_names(idx=0):
                if _abort[0] or idx >= qty:
                    if _abort[0]:
                        return
                    # Semua nama terkumpul, lanjut ke progress window
                    _launch_progress_win(custom_names)
                    return
                def _got_name(val):
                    if val is None:  # user batalkan semua
                        return
                    custom_names.append(val)
                    self.root.after(80, lambda: _collect_names(idx + 1))
                _ask_name(idx, _got_name)

            _collect_names()
            return  # lanjut dari _launch_progress_win()

        # Mode default (tanpa custom nama) — langsung ke progress
        _launch_progress_win(None)

    # ── Update ────────────────────────────────────────────────────────────────
    def _show_update_popup(self, update_sh):
        f   = self._font
        win = tk.Toplevel(self.root); win.title("Update")
        win.configure(bg=BG); win.geometry("420x180"); win.resizable(False, False)
        win.attributes("-topmost", True)
        win.update_idletasks()
        rx = self.root.winfo_x() + self.root.winfo_width()  // 2 - 210
        ry = self.root.winfo_y() + self.root.winfo_height() // 2 - 90
        win.geometry(f"420x180+{rx}+{ry}"); win.deiconify(); win.update()
        try: win.grab_set()
        except Exception: pass

        body = tk.Frame(win, bg=BG, padx=28, pady=24); body.pack(fill="both", expand=True)
        icon_lbl = tk.Label(body, text="\u21ba", bg=BG, fg=ACCENT, font=(f, 22))
        icon_lbl.grid(row=0, column=0, rowspan=2, padx=(0,16), sticky="n")
        msg_var = tk.StringVar(value="Checking for updates...")
        msg_lbl = tk.Label(body, textvariable=msg_var, bg=BG, fg=FG,
                           font=(f, 11, "bold"), anchor="w", justify="left")
        msg_lbl.grid(row=0, column=1, sticky="w")
        sub_var = tk.StringVar(value="")
        tk.Label(body, textvariable=sub_var, bg=BG, fg=FG2,
                 font=(f, 9), anchor="w", justify="left").grid(row=1, column=1, sticky="w", pady=(4,0))
        tk.Frame(win, bg=BORDER, height=1).pack(fill="x")
        foot = tk.Frame(win, bg=BG2, height=44); foot.pack(fill="x"); foot.pack_propagate(False)
        foot_inner = tk.Frame(foot, bg=BG2, padx=12); foot_inner.pack(fill="both", expand=True)

        ok_h, _ = make_pill_btn(foot_inner, "OK", win.destroy, bg=BG3, fg=FG, hover_bg=BG4,
                                 font_size=9, padx=20, pady=6, radius=7)

        def _restart():
            win.destroy()
            import sys, os
            os.execv(sys.executable, [sys.executable] + sys.argv)

        restart_h, _ = make_pill_btn(foot_inner, "\u21bb  Restart App", _restart,
                                      bg=ACCENT_DIM, fg=ACCENT, hover_bg="#1d2b36",
                                      font_size=9, padx=20, pady=6, radius=7)

        def _on_done(already_updated):
            if already_updated:
                icon_lbl.config(text="\u2713", fg=ACCENT3)
                msg_var.set("App is up-to-date."); sub_var.set("No new changes.")
                ok_h.pack(side="right", pady=8)
            else:
                icon_lbl.config(text="\u2713", fg=ACCENT3)
                msg_var.set("Update successful!")
                sub_var.set("Restart the app to apply changes.")
                restart_h.pack(side="right", pady=8, padx=(0,6)); ok_h.pack(side="right", pady=8)

        def _on_fail(msg):
            icon_lbl.config(text="\u2717", fg=DANGER)
            msg_var.set("Update failed."); sub_var.set(msg[:72]); ok_h.pack(side="right", pady=8)

        upd.run_update_bg(update_sh,
                          on_done=lambda au: win.after(0, lambda: _on_done(au)),
                          on_fail=lambda m: win.after(0, lambda: _on_fail(m)))

    def _auto_update_check(self):
        upd.auto_update_check(self)

    def _show_auto_update_result(self, has_update: bool):
        if not has_update:
            return
        f   = self._font
        win = tk.Toplevel(self.root); win.title("Update Available")
        win.configure(bg=BG); win.geometry("400x160"); win.resizable(False, False)
        win.attributes("-topmost", True); win.update_idletasks()
        rx = self.root.winfo_x() + self.root.winfo_width()  // 2 - 200
        ry = self.root.winfo_y() + self.root.winfo_height() // 2 - 80
        win.geometry(f"400x160+{rx}+{ry}"); win.deiconify(); win.lift(); win.focus_force()

        body = tk.Frame(win, bg=BG, padx=28, pady=20); body.pack(fill="both", expand=True)
        tk.Label(body, text="\u21ba", bg=BG, fg=ACCENT3,
                 font=(f, 22)).grid(row=0, column=0, rowspan=2, padx=(0,16), sticky="n")
        tk.Label(body, text="Update installed successfully!",
                 bg=BG, fg=FG, font=(f, 11, "bold"), anchor="w").grid(row=0, column=1, sticky="w")
        tk.Label(body, text="Restart the app to apply changes.",
                 bg=BG, fg=FG2, font=(f, 9), anchor="w").grid(row=1, column=1, sticky="w", pady=(4,0))
        tk.Frame(win, bg=BORDER, height=1).pack(fill="x")
        foot = tk.Frame(win, bg=BG2, height=44); foot.pack(fill="x"); foot.pack_propagate(False)
        fi = tk.Frame(foot, bg=BG2, padx=12); fi.pack(fill="both", expand=True)

        def _restart():
            win.destroy()
            import sys, os
            os.execv(sys.executable, [sys.executable] + sys.argv)

        r_h, _ = make_pill_btn(fi, "\u21bb  Restart App", _restart,
                               bg=ACCENT_DIM, fg=ACCENT, hover_bg="#1d2b36",
                               font_size=9, padx=20, pady=6, radius=7)
        r_h.pack(side="right", pady=8, padx=(0,6))
        ok_h, _ = make_pill_btn(fi, "Later", win.destroy, bg=BG3, fg=FG, hover_bg=BG4,
                                 font_size=9, padx=20, pady=6, radius=7)
        ok_h.pack(side="right", pady=8)
        self._status("A new update is available \u2014 restart to apply.")

    # ── Autostart canvas ──────────────────────────────────────────────────────
    # ── Autostart switch (info bar) ─────────────────────────────────────────────
    def _draw_as_switch(self, on, enabled=True):
        c = self._as_switch
        c.delete("all")
        w, h   = 38, 18
        tw, th = 34, 16
        cx, cy = w // 2, h // 2
        tx1, tx2 = cx - tw // 2, cx + tw // 2
        ty1, ty2 = cy - th // 2, cy + th // 2
        r = th // 2
        thumb_r = 6
        if not enabled:
            track, thumb, on = "#1c2636", "#3a4658", False
        else:
            track = AS_COLOR_ON if on else AS_COLOR_OFF
            thumb = AS_THUMB_COL
        pts = [tx1+r,ty1, tx2-r,ty1, tx2,ty1, tx2,ty1+r,
               tx2,ty2-r, tx2,ty2, tx2-r,ty2, tx1+r,ty2,
               tx1,ty2, tx1,ty2-r, tx1,ty1+r, tx1,ty1, tx1+r,ty1]
        c.create_polygon(pts, smooth=True, fill=track, outline="")
        thumb_cx = (tx2 - r) if on else (tx1 + r)
        c.create_oval(thumb_cx - thumb_r, cy - thumb_r,
                      thumb_cx + thumb_r, cy + thumb_r, fill=thumb, outline="")

    def _update_as_switch(self, t):
        if t is None:
            self._draw_as_switch(False, enabled=False)
            self._as_switch_lbl.config(text="—", fg=FG3)
            self._as_switch.config(cursor="arrow")
            return
        on = be.autostart_is_on(t)
        self._draw_as_switch(on, enabled=True)
        self._as_switch_lbl.config(text="ON" if on else "OFF",
                                   fg=ACCENT3 if on else FG3)
        self._as_switch.config(cursor="hand2")

    def _toggle_selected_autostart(self, _=None):
        t = self._terminal(silent=True)
        if not t:
            self._status("Select a terminal first to configure autostart.")
            return
        new_state = not be.autostart_is_on(t)
        ok = be.autostart_set(
            t, new_state,
            lambda t_: be.find_exe(t_, "terminal.exe", "terminal64.exe"))
        if new_state and not ok:
            themed_popup(self.root, "error", "Autostart Failed",
                f"File terminal.exe / terminal64.exe not found\n"
                f"for {t['name']} ({t['type']}).\n\nAutostart could not be created.")
            return
        sel = self.term_tree.selection()
        if sel:
            self._as_state_cache[sel[0]] = new_state
        self._update_as_switch(t)
        self._draw_as_canvas()
        self._status(f"Autostart {t['name']} → {'ON' if new_state else 'OFF'}")

    # ── Autostart overview (sidebar) ────────────────────────────────────────────
    def _draw_as_canvas(self):
        if getattr(self, "_as_draw_id", None):
            self._as_canvas.after_cancel(self._as_draw_id)
        self._as_draw_id = self._as_canvas.after(8, self._do_draw_as_canvas)

    def _do_draw_as_canvas(self):
        self._as_draw_id = None
        c  = self._as_canvas
        cw = c.winfo_width(); ch = c.winfo_height()
        if cw < 4 or ch < 4:
            return
        c.delete("all")
        rh      = 44
        iid_map = getattr(self, "_iid_to_terminal", {})
        all_rows = getattr(self, "_all_term_rows", None) or self.term_tree.get_children()
        if not all_rows:
            return
        yview         = self.term_tree.yview()
        scroll_offset = int(yview[0] * len(all_rows) * rh)
        cx = cw // 2
        hover = getattr(self, "_as_hover_iid", None)
        as_cache = self._as_state_cache
        dot_r = 5

        for idx, iid in enumerate(all_rows):
            if iid not in iid_map:
                continue
            y_center = idx * rh + (rh >> 1) - scroll_offset
            if y_center < -rh or y_center > ch + rh:
                continue
            on = as_cache.get(iid)
            if on is None:
                on = be.autostart_is_on(iid_map[iid])
                as_cache[iid] = on
            is_hover = (iid == hover)
            # Indikator status (read-only) — kontrol ada di info bar
            if on:
                fill = "#00e6ac" if is_hover else AS_COLOR_ON
                c.create_oval(cx - dot_r, y_center - dot_r,
                              cx + dot_r, y_center + dot_r,
                              fill=fill, outline="")
            else:
                ring = "#3a5570" if is_hover else AS_COLOR_OFF
                c.create_oval(cx - dot_r, y_center - dot_r,
                              cx + dot_r, y_center + dot_r,
                              fill="", outline=ring, width=2)

    def _as_y_to_iid(self, y: int):
        rh       = 44
        all_rows = getattr(self, "_all_term_rows", None) or self.term_tree.get_children()
        if not all_rows:
            return None
        yview         = self.term_tree.yview()
        scroll_offset = int(yview[0] * len(all_rows) * rh)
        idx = (y + scroll_offset) // rh
        if idx < 0 or idx >= len(all_rows):
            return None
        iid = all_rows[idx]
        return iid if iid in getattr(self, "_iid_to_terminal", {}) else None

    def _on_as_click(self, event):
        # Kolom ini kini hanya overview: klik = pilih terminal,
        # pengaturan autostart dilakukan lewat switch di info bar.
        iid = self._as_y_to_iid(event.y)
        if iid is None:
            return
        self.term_tree.selection_set(iid)
        self.term_tree.see(iid)

    def _on_as_motion(self, event):
        iid = self._as_y_to_iid(event.y)
        if iid != self._as_hover_iid:
            self._as_hover_iid = iid
            self._draw_as_canvas()   # sudah ter-debounce via _draw_as_canvas
            self._as_cancel_tooltip()
            if iid is not None:
                self._as_tooltip_id = self._as_canvas.after(
                    650, lambda: self._as_show_tooltip(event.x_root, event.y_root))

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
            try: self._as_tooltip_win.destroy()
            except Exception: pass
            self._as_tooltip_win = None

    def _as_show_tooltip(self, rx, ry):
        if self._as_tooltip_win:
            return
        tw = tk.Toplevel(self.root); tw.wm_overrideredirect(True)
        tw.configure(bg=BORDER2); tw.attributes("-topmost", True)
        outer = tk.Frame(tw, bg=BORDER2, padx=1, pady=1); outer.pack()
        inner = tk.Frame(outer, bg=BG3, padx=12, pady=7); inner.pack()
        tk.Label(inner, text="Autostart status — select a terminal, then toggle via the switch in the info panel",
                 bg=BG3, fg=FG2, font=(self._font, 9), wraplength=260, justify="left").pack()
        tw.update_idletasks()
        tw_ = tw.winfo_reqwidth(); th_ = tw.winfo_reqheight()
        x = rx + 14; y = ry + 18
        sw = tw.winfo_screenwidth(); sh = tw.winfo_screenheight()
        if x + tw_ > sw: x = rx - tw_ - 6
        if y + th_ > sh: y = ry - th_ - 6
        tw.wm_geometry(f"+{x}+{y}")
        self._as_tooltip_win = tw

    def _autostart_sync_poll(self):
        iid_map = getattr(self, "_iid_to_terminal", {})
        # Hanya iterasi jika ada entry yang ON di cache
        on_entries = [(iid, state) for iid, state in self._as_state_cache.items() if state]
        if on_entries:
            changed = False
            for iid, _ in on_entries:
                t = iid_map.get(iid)
                if t is None:
                    continue
                now_on = be.autostart_is_on(t)
                if not now_on:
                    self._as_state_cache[iid] = False
                    changed = True
            if changed:
                self._draw_as_canvas()
        self.root.after(2000, self._autostart_sync_poll)

    # ── Scan terminals ────────────────────────────────────────────────────────
    def scan_terminals(self, silent=False):
        # Bersihkan SEMUA tiga tree sekaligus
        self.term_tree.delete(*self.term_tree.get_children())
        for tree in (self.chk_tree, self.cat_tree, self.file_tree):
            tree.delete(*tree.get_children())
        # Reset state checkbox
        self._checked.clear()
        self._all_checked = False
        self.chk_tree.heading("chk", text=CHK_CHAR_OFF)
        # Reset info bar ke default
        for key, (var, lbl) in self._info_fields.items():
            var.set("—")
        self._info_fields["type"][1].config(fg=FG)
        self._info_fields["path"][1].config(fg=FG)
        self.terminals.clear()
        self._as_state_cache.clear()
        self._last_selected_path = None
        # Bersihkan clipboard agar tidak ada referensi path lama
        self._clipboard      = []
        self._clipboard_mode = ""
        self._status("Scanning terminals…")

        def _on_result(found):
            self.root.after(0, lambda: self._apply_scan(found, silent))

        be.scan_terminals_bg(_on_result)

    def _apply_scan(self, found, silent):
        self.terminals.clear(); self.terminals.extend(found)
        # Pastikan semua tree bersih dan selection cleared
        self.term_tree.selection_remove(*self.term_tree.selection())
        self.term_tree.delete(*self.term_tree.get_children())
        for tree in (self.chk_tree, self.cat_tree, self.file_tree):
            tree.delete(*tree.get_children())
        self._iid_to_terminal = {}
        cur_type = None
        for item in found:
            if item["type"] != cur_type:
                cur_type = item["type"]
                label = f"METATRADER {'4' if cur_type == 'MT4' else '5'}"
                self.term_tree.insert("", "end",
                    values=("", label, ""), tags=("group",))
            iid = self.term_tree.insert("", "end",
                values=(item["type"], item["name"], item["type"]),
                tags=(item["type"],))
            self._iid_to_terminal[iid] = item

        self._all_term_rows = self.term_tree.get_children()
        self.root.after(50, self._draw_as_canvas)

        n = len(found)
        if hasattr(self, "_term_count_var"):
            self._term_count_var.set(f"{n} terminal(s) detected")
        self._status(f"{n} terminal(s) found.")

        if not silent:
            self._show_scan_result(found)

    def _show_scan_result(self, found):
        f  = self._font
        mt4_count = sum(1 for t in found if t["type"] == "MT4")
        mt5_count = sum(1 for t in found if t["type"] == "MT5")
        n = len(found)

        dlg = tk.Toplevel(self.root); dlg.title("Scan Complete")
        dlg.configure(bg=BG); dlg.resizable(False, False); dlg.attributes("-topmost", True)
        hdr = tk.Frame(dlg, bg=BG2, height=48); hdr.pack(fill="x"); hdr.pack_propagate(False)
        hdr_inner = tk.Frame(hdr, bg=BG2, padx=20); hdr_inner.pack(fill="both", expand=True)
        tk.Label(hdr_inner, text="\u2713  Scan Complete",
                 bg=BG2, fg="#5ecf3e", font=(f, 12, "bold")).pack(side="left", fill="y")
        tk.Frame(dlg, bg=BORDER, height=1).pack(fill="x")
        body = tk.Frame(dlg, bg=BG, padx=24, pady=18); body.pack(fill="both", expand=True)
        tk.Label(body, text="\u2713", bg=BG, fg="#5ecf3e",
                 font=(f, 22)).grid(row=0, column=0, rowspan=3, padx=(0,16), sticky="n")
        tk.Label(body, text=f"Found {n} MetaTrader terminal(s).",
                 bg=BG, fg=FG, font=(f, 11, "bold"), anchor="w").grid(row=0, column=1, sticky="w")
        info_box = tk.Frame(body, bg=BG3, padx=14, pady=10)
        info_box.grid(row=1, column=1, sticky="ew", pady=(10,0))
        body.columnconfigure(1, weight=1)
        for lbl, val, clr in [("MetaTrader 4", f"{mt4_count} terminal", ACCENT),
                               ("MetaTrader 5", f"{mt5_count} terminal", ACCENT),
                               ("Total",        f"{n} terminal",         FG)]:
            row = tk.Frame(info_box, bg=BG3); row.pack(fill="x", pady=2)
            tk.Label(row, text=f"{lbl:<14}", bg=BG3, fg=FG3,
                     font=(f, 9), anchor="w", width=14).pack(side="left")
            tk.Label(row, text=val, bg=BG3, fg=clr,
                     font=(f, 9, "bold"), anchor="w").pack(side="left")
        if found:
            tk.Frame(info_box, bg=BORDER, height=1).pack(fill="x", pady=(8,6))
            for t in found[:8]:
                tk.Label(info_box, text=f"  {t['type']}  {t['name']}",
                         bg=BG3, fg=FG3, font=(f, 8), anchor="w").pack(anchor="w")
            if len(found) > 8:
                tk.Label(info_box, text=f"  \u2026 and {len(found)-8} more",
                         bg=BG3, fg=FG3, font=(f, 8), anchor="w").pack(anchor="w")
        tk.Frame(dlg, bg=BORDER, height=1).pack(fill="x")
        foot = tk.Frame(dlg, bg=BG2, height=44); foot.pack(fill="x"); foot.pack_propagate(False)
        fi = tk.Frame(foot, bg=BG2, padx=12); fi.pack(fill="both", expand=True)
        oh, _ = make_pill_btn(fi, "OK", dlg.destroy, bg=BG3, fg=FG, hover_bg=BG4,
                              font_size=9, padx=20, pady=6, radius=7)
        oh.pack(side="right", pady=8)
        dlg.update_idletasks(); self._center_win(dlg); dlg.deiconify(); dlg.lift(); dlg.focus_force()

    # ── Utility ───────────────────────────────────────────────────────────────
    def _center_win(self, win):
        """Pusatkan window relatif terhadap root."""
        win.update_idletasks()
        rx = self.root.winfo_x() + self.root.winfo_width()  // 2 - win.winfo_reqwidth()  // 2
        ry = self.root.winfo_y() + self.root.winfo_height() // 2 - win.winfo_reqheight() // 2
        win.geometry(f"+{rx}+{ry}")
