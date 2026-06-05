"""
mt_manager.py — Entry point
Jalankan: python mt_manager.py
"""

import tkinter as tk
from pathlib import Path
from ui import MTManager

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
