import tkinter as tk
from tkinter import messagebox, ttk

from .theme import DARK_BG, DARK_FG, DARK_ENTRY, DARK_SELECT, DARK_LIST, DARK_HIGHLIGHT


class GlobalExceptionsWindow:
    def __init__(self, parent, settings, on_change=None):
        self.on_change = on_change
        self.win = tk.Toplevel(parent)
        self.win.title("Глобальные исключения")
        self.win.geometry("500x400")
        self.win.resizable(False, False)
        self.win.configure(bg=DARK_BG)

        self.settings = settings
        self.changed = False
        self._drag_data = {}
        self._setup_drag()

        main_frame = ttk.Frame(self.win, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(main_frame, text="Общие исключения (действуют для всех папок):").pack(anchor=tk.W, pady=(0, 2))
        ttk.Label(main_frame, text="Двойной клик ЛКМ — переключить состояние", foreground="#aaaaaa",
                  font=("Consolas", 9)).pack(anchor=tk.W, pady=(0, 5))

        list_frame = ttk.Frame(main_frame)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set, font=("Consolas", 10),
                                  bg=DARK_LIST, fg=DARK_FG, selectbackground=DARK_SELECT,
                                  selectforeground=DARK_FG, highlightbackground=DARK_ENTRY,
                                  highlightcolor=DARK_HIGHLIGHT, borderwidth=0)
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.listbox.yview)
        self.listbox.bind("<Double-1>", lambda e: self._toggle())

        input_frame = ttk.Frame(main_frame)
        input_frame.pack(fill=tk.X, pady=(0, 5))

        self.entry = ttk.Entry(input_frame, font=("Consolas", 10))
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.entry.bind("<Return>", lambda e: self._add())

        btn_add = ttk.Button(input_frame, text="Добавить", command=self._add, width=12)
        btn_add.pack(side=tk.RIGHT)

        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X)

        btn_toggle = ttk.Button(btn_frame, text="Вкл/Выкл", command=self._toggle, width=12)
        btn_toggle.pack(side=tk.LEFT, padx=(0, 5))

        btn_remove = ttk.Button(btn_frame, text="Удалить", command=self._remove, width=12)
        btn_remove.pack(side=tk.LEFT, padx=(0, 5))

        ttk.Button(btn_frame, text="Закрыть", command=self.win.destroy, width=12).pack(side=tk.RIGHT)

        self.listbox.bind("<ButtonPress-1>", self._listbox_click)
        self._refresh()

    def _setup_drag(self):
        self.win.bind("<ButtonPress-1>", self._drag_start)
        self.win.bind("<B1-Motion>", self._drag_move)

    def _listbox_click(self, event):
        self.listbox.selection_clear(0, tk.END)
        if self.listbox.size() > 0:
            idx = self.listbox.nearest(event.y)
            if idx != -1:
                bbox = self.listbox.bbox(idx)
                if bbox and bbox[1] <= event.y <= bbox[1] + bbox[3]:
                    self.listbox.selection_set(idx)
                    self.listbox.activate(idx)
                    self._drag_data = {}
                    return "break"
        self._drag_start(event)
        return "break"

    def _drag_start(self, event):
        widget = event.widget
        if isinstance(widget, (ttk.Button, ttk.Entry, ttk.Scrollbar)):
            self._drag_data = {}
            return
        if isinstance(widget, tk.Listbox):
            if widget.size() > 0:
                idx = widget.nearest(event.y)
                if idx != -1:
                    bbox = widget.bbox(idx)
                    if bbox and bbox[1] <= event.y <= bbox[1] + bbox[3]:
                        self._drag_data = {}
                        return
        self._drag_data = {"x": event.x_root, "y": event.y_root,
                          "win_x": self.win.winfo_x(), "win_y": self.win.winfo_y()}

    def _drag_move(self, event):
        d = self._drag_data
        if not d:
            return
        dx = event.x_root - d["x"]
        dy = event.y_root - d["y"]
        self.win.geometry("+%d+%d" % (d["win_x"] + dx, d["win_y"] + dy))

    def _refresh(self):
        self.listbox.delete(0, tk.END)
        for ex in self.settings.global_exceptions:
            status = "[ВКЛ]" if ex.get("enabled", True) else "[ВЫКЛ]"
            self.listbox.insert(tk.END, f"{status} {ex['name']}")

    def _add(self):
        name = self.entry.get().strip()
        if not name:
            return
        self.settings._last_save_ok = True
        added = self.settings.add_global_exception(name)
        self.entry.delete(0, tk.END)
        self._refresh()
        if added:
            self.changed = True
            if not self.settings._last_save_ok:
                messagebox.showwarning("Ошибка сохранения",
                    "Не удалось сохранить глобальные исключения.\nПроверьте права доступа к папке config.",
                    parent=self.win)
            if self.on_change:
                self.on_change()

    def _remove(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        self.settings._last_save_ok = True
        for i in reversed(sel):
            if self.settings.remove_global_exception(i):
                self.changed = True
        self._refresh()
        if not self.settings._last_save_ok:
            messagebox.showwarning("Ошибка сохранения",
                "Не удалось сохранить глобальные исключения.\nПроверьте права доступа к папке config.",
                parent=self.win)
        if self.on_change:
            self.on_change()

    def _toggle(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        self.settings._last_save_ok = True
        for i in reversed(sel):
            if self.settings.toggle_global_exception(i):
                self.changed = True
        self._refresh()
        if not self.settings._last_save_ok:
            messagebox.showwarning("Ошибка сохранения",
                "Не удалось сохранить глобальные исключения.\nПроверьте права доступа к папке config.",
                parent=self.win)
        if self.on_change:
            self.on_change()
