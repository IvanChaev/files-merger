import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .exceptions_engine import format_entry, SCOPE_ALL, SCOPE_ROOT, SCOPE_PATH
from .theme import DARK_BG, DARK_FG, DARK_ENTRY, DARK_SELECT, DARK_LIST, DARK_HIGHLIGHT
from .global_exceptions_window import GlobalExceptionsWindow


class ExceptionsWindow:
    def __init__(self, parent, settings, on_change=None, close_callback=None):
        self.on_change = on_change
        self.close_callback = close_callback
        self.win = tk.Toplevel(parent)
        self.win.title("Настройка исключений")
        self.win.geometry("800x450")
        self.win.resizable(False, False)
        self.win.configure(bg=DARK_BG)

        self.settings = settings
        self._drag_data = {}
        self._global_window = None
        self._setup_drag()
        self.win.protocol("WM_DELETE_WINDOW", self._on_close)

        main_frame = ttk.Frame(self.win, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(main_frame, text="Исключения (файлы и папки, пропускаемые при объединении):").pack(anchor=tk.W, pady=(0, 5))

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

        input_frame = ttk.Frame(main_frame)
        input_frame.pack(fill=tk.X, pady=(0, 5))

        self.entry = ttk.Entry(input_frame, font=("Consolas", 10))
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.entry.bind("<Return>", lambda e: self._add())

        btn_add = ttk.Button(input_frame, text="Добавить", command=self._add, width=12)
        btn_add.pack(side=tk.RIGHT)

        scope_frame = ttk.Frame(main_frame)
        scope_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(scope_frame, text="Область исключения:").pack(side=tk.LEFT, padx=(0, 5))

        self.scope_var = tk.StringVar(value="везде")
        scope_combo = ttk.Combobox(scope_frame, textvariable=self.scope_var, state="readonly", width=18,
                                    values=["везде", "только корень", "в папке..."])
        scope_combo.pack(side=tk.LEFT, padx=(0, 5))
        scope_combo.bind("<<ComboboxSelected>>", self._on_scope_change)

        self.scope_path_var = tk.StringVar()
        self.scope_path_entry = ttk.Entry(scope_frame, textvariable=self.scope_path_var,
                                           font=("Consolas", 10), state="disabled")
        self.scope_path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        self.scope_path_btn = ttk.Button(scope_frame, text="Обзор", command=self._browse_scope_path,
                                          width=8, state="disabled")
        self.scope_path_btn.pack(side=tk.LEFT)

        file_btn_frame = ttk.Frame(main_frame)
        file_btn_frame.pack(fill=tk.X, pady=(0, 10))

        btn_browse_file = ttk.Button(file_btn_frame, text="Выбрать файл(ы)", command=self._browse_file, width=18)
        btn_browse_file.pack(side=tk.LEFT, padx=(0, 5))

        btn_browse_dir = ttk.Button(file_btn_frame, text="Выбрать папку", command=self._browse_dir, width=18)
        btn_browse_dir.pack(side=tk.LEFT)

        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X)

        btn_remove = ttk.Button(btn_frame, text="Удалить", command=self._remove, width=12)
        btn_remove.pack(side=tk.LEFT, padx=(0, 5))

        btn_clear = ttk.Button(btn_frame, text="Очистить всё", command=self._clear, width=14)
        btn_clear.pack(side=tk.LEFT, padx=(0, 5))

        ttk.Button(btn_frame, text="Общие исключения", command=self._open_global, width=22).pack(side=tk.LEFT, padx=(0, 5))

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
        if isinstance(widget, (ttk.Button, ttk.Entry, ttk.Combobox, ttk.Scrollbar)):
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

    def _on_close(self):
        if self.close_callback:
            self.close_callback()
        self.win.destroy()

    def _open_global(self):
        if self._global_window is not None and self._global_window.win.winfo_exists():
            self._global_window.win.lift()
            self._global_window.win.focus_force()
            return
        self._global_window = GlobalExceptionsWindow(self.win, self.settings, on_change=self.on_change)

    def _on_scope_change(self, event=None):
        is_path = self.scope_var.get() == "в папке..."
        state = "normal" if is_path else "disabled"
        self.scope_path_entry.config(state=state)
        self.scope_path_btn.config(state=state)

    def _browse_scope_path(self):
        path = filedialog.askdirectory(title="Выберите папку для области исключения", parent=self.win)
        if path:
            self.scope_path_var.set(path)

    def _refresh(self):
        self.listbox.delete(0, tk.END)
        for entry in self.settings.get_current_exceptions():
            self.listbox.insert(tk.END, format_entry(entry))
        if self.on_change:
            self.on_change()

    def _resolve_scope(self):
        label = self.scope_var.get()
        if label == "только корень":
            return SCOPE_ROOT, ""
        elif label == "в папке...":
            path = self.scope_path_var.get().strip()
            return SCOPE_PATH, path
        return SCOPE_ALL, ""

    def _add_scope_path(self, names):
        scope, scope_path = self._resolve_scope()
        if scope == SCOPE_PATH and not scope_path:
            messagebox.showwarning("Внимание", "Выберите папку для области «в папке...»", parent=self.win)
            return
        for name in names:
            self.settings.add_exception(name, scope, scope_path)
        self._refresh()

    def _add(self):
        name = self.entry.get().strip()
        if not name:
            return
        scope, scope_path = self._resolve_scope()
        if scope == SCOPE_PATH and not scope_path:
            messagebox.showwarning("Внимание", "Выберите папку для области «в папке...»", parent=self.win)
            return
        self.settings._last_save_ok = True
        added = self.settings.add_exception(name, scope, scope_path)
        self.entry.delete(0, tk.END)
        self._refresh()
        if added and not self.settings._last_save_ok:
            messagebox.showwarning("Ошибка сохранения",
                "Не удалось сохранить настройки исключений.\nПроверьте права доступа к папке config.",
                parent=self.win)

    def _remove(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        self.settings._last_save_ok = True
        for i in reversed(sel):
            self.settings.remove_exception(i)
        self._refresh()
        if not self.settings._last_save_ok:
            messagebox.showwarning("Ошибка сохранения",
                "Не удалось сохранить настройки исключений.\nПроверьте права доступа к папке config.",
                parent=self.win)

    def _clear(self):
        if messagebox.askyesno("Подтверждение", "Удалить все исключения для текущей папки?", parent=self.win):
            self.settings._last_save_ok = True
            self.settings.clear_exceptions()
            self._refresh()
            if not self.settings._last_save_ok:
                messagebox.showwarning("Ошибка сохранения",
                    "Не удалось сохранить настройки исключений.\nПроверьте права доступа к папке config.",
                    parent=self.win)

    def _browse_file(self):
        paths = filedialog.askopenfilenames(title="Выберите файлы для исключения", parent=self.win)
        if paths:
            self._add_scope_path(paths)

    def _browse_dir(self):
        path = filedialog.askdirectory(title="Выберите папку для исключения", parent=self.win)
        if path:
            self._add_scope_path([path])
