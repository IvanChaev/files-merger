import tkinter as tk
from tkinter import ttk


DARK_BG = "#1e1e1e"
DARK_FG = "#ffffff"
DARK_ENTRY = "#3c3c3c"
DARK_SELECT = "#264f78"
DARK_BUTTON = "#2d2d2d"
DARK_FRAME = "#252526"
DARK_LIST = "#1e1e1e"
DARK_SCROLLBAR = "#3c3c3c"
DARK_DISABLED_FG = "#888888"
DARK_HIGHLIGHT = "#094771"


def setup_dark_style(root):
    root.configure(bg=DARK_BG)

    style = ttk.Style(root)
    style.theme_use("clam")

    style.configure(".", background=DARK_FRAME, foreground=DARK_FG, fieldbackground=DARK_ENTRY,
                     troughcolor=DARK_FRAME, selectbackground=DARK_SELECT, selectforeground=DARK_FG)

    style.configure("TFrame", background=DARK_FRAME)
    style.configure("TLabel", background=DARK_FRAME, foreground=DARK_FG)
    style.configure("TButton", background=DARK_BUTTON, foreground=DARK_FG, bordercolor="#ffd700",
                     focuscolor="#ffd700", lightcolor="#ffd700", darkcolor="#ffd700", borderwidth=2)
    style.map("TButton", background=[("active", "#3c3c3c"), ("pressed", "#1a1a1a")],
              bordercolor=[("active", "#ffd700"), ("disabled", "#555555")],
              foreground=[("disabled", DARK_DISABLED_FG)])
    style.configure("TEntry", fieldbackground=DARK_ENTRY, foreground=DARK_FG, insertcolor=DARK_FG)
    style.configure("TCombobox", fieldbackground=DARK_ENTRY, foreground=DARK_FG, arrowcolor="#ffd700",
                     selectbackground=DARK_SELECT, bordercolor="#ffd700", lightcolor="#ffd700",
                     darkcolor="#ffd700")
    style.map("TCombobox", fieldbackground=[("readonly", DARK_ENTRY)])
    style.configure("Horizontal.TProgressbar", background=DARK_SELECT, troughcolor=DARK_FRAME)
    style.configure("Vertical.TScrollbar", background=DARK_SCROLLBAR, troughcolor=DARK_FRAME,
                     arrowcolor=DARK_FG)
