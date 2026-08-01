import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import os
import traceback
import subprocess
import datetime
import threading
import json

from .logger import get_logger
from .exceptions_engine import count_excluded
from .settings_manager import SettingsManager
from .exceptions_window import ExceptionsWindow
from .merge_worker import MergeWorker
from .theme import DARK_BG, setup_dark_style

log = get_logger(__name__)

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(BASE, "config")
LOGS_DIR = os.path.join(BASE, "logs")
DUMPS_DIR = os.path.join(BASE, "dumps")


class MainWindow:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Folder Merger — объединение файлов в один")
        self.root.geometry("900x385+400+200")
        self.root.minsize(430, 385)
        self.root.configure(bg=DARK_BG)

        setup_dark_style(self.root)

        def _tk_exception(exc_type, exc_value, exc_traceback):
            try:
                os.makedirs(LOGS_DIR, exist_ok=True)
                log.critical("tkinter callback exception",
                             exc_info=(exc_type, exc_value, exc_traceback))
            except Exception:
                pass

        self.root.report_callback_exception = _tk_exception

        self.settings = SettingsManager(CONFIG_DIR)
        self._worker = MergeWorker(
            self.settings,
            progress_callback=self._on_progress,
            success_callback=self._on_success,
            error_callback=self._on_error,
            cancel_callback=self._on_cancelled
        )
        self._excluded_count = 0
        self._excluded_counts = {}
        self._closing = False
        self._drag_data = {}
        self._excluded_preview_cache = {}
        self._excluded_preview_running = False
        self._excluded_preview_pending = False
        self._exceptions_window = None
        self._build_ui()
        self._setup_drag()
        self._poll_worker()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        if self.settings.current_folder:
            self.dir_path.set(self.settings.current_folder)
            self._update_history()
            self._update_exception_count()
            self._update_excluded_preview()
            log.info("Restored folder: %s", self.settings.current_folder)

        log.info("MainWindow initialized")

    def _setup_drag(self):
        self.root.bind("<ButtonPress-1>", self._drag_start)
        self.root.bind("<B1-Motion>", self._drag_move)

    def _drag_start(self, event):
        if isinstance(event.widget, (ttk.Entry, ttk.Button, ttk.Combobox)):
            self._drag_data = {}
            return
        self._drag_data = {"x": event.x_root, "y": event.y_root,
                          "win_x": self.root.winfo_x(), "win_y": self.root.winfo_y()}

    def _drag_move(self, event):
        d = self._drag_data
        if not d:
            return
        dx = event.x_root - d["x"]
        dy = event.y_root - d["y"]
        self.root.geometry("+%d+%d" % (d["win_x"] + dx, d["win_y"] + dy))

    def _build_ui(self):
        main_frame = ttk.Frame(self.root, padding=15)
        main_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(main_frame, text="История папок:").grid(row=0, column=0, sticky=tk.W, pady=(0, 5))
        history_frame = ttk.Frame(main_frame)
        history_frame.grid(row=0, column=1, columnspan=2, sticky=tk.EW, pady=(0, 5))
        history_frame.columnconfigure(0, weight=1)

        self.history_var = tk.StringVar()
        self.history_combo = ttk.Combobox(history_frame, textvariable=self.history_var,
                                           state="readonly", font=("Consolas", 9))
        self.history_combo.grid(row=0, column=0, sticky=tk.EW, padx=(0, 5))
        self.history_combo.bind("<<ComboboxSelected>>", self._on_history_select)

        self.btn_history_delete = ttk.Button(history_frame, text="✕", command=self._remove_from_history, width=3)
        self.btn_history_delete.grid(row=0, column=1)

        ttk.Label(main_frame, text="Исходная папка:").grid(row=1, column=0, sticky=tk.W, pady=(0, 5))
        dir_frame = ttk.Frame(main_frame)
        dir_frame.grid(row=2, column=0, columnspan=3, sticky=tk.EW, pady=(0, 10))
        dir_frame.columnconfigure(0, weight=1)

        self.dir_path = tk.StringVar()
        self.dir_entry = ttk.Entry(dir_frame, textvariable=self.dir_path, font=("Consolas", 10))
        self.dir_entry.grid(row=0, column=0, sticky=tk.EW, padx=(0, 5))
        self.dir_entry.bind("<Return>", lambda e: self._commit_dir())
        self.dir_entry.bind("<FocusOut>", lambda e: self._commit_dir())

        self.btn_browse_dir = ttk.Button(dir_frame, text="Выбрать", command=self._browse_dir, width=10)
        self.btn_browse_dir.grid(row=0, column=1, padx=(0, 5))
        self.btn_open_dumps = ttk.Button(dir_frame, text="К объединённым", command=self._open_dumps, width=18)
        self.btn_open_dumps.grid(row=0, column=2)

        ttk.Label(main_frame, text="Выходной файл:").grid(row=3, column=0, sticky=tk.W, pady=(0, 5))
        out_frame = ttk.Frame(main_frame)
        out_frame.grid(row=4, column=0, columnspan=3, sticky=tk.EW, pady=(0, 10))
        out_frame.columnconfigure(0, weight=1)

        self.out_path = tk.StringVar()
        self._set_default_out_path()
        out_entry = ttk.Entry(out_frame, textvariable=self.out_path, font=("Consolas", 10))
        out_entry.grid(row=0, column=0, sticky=tk.EW, padx=(0, 5))

        self.btn_save_as = ttk.Button(out_frame, text="Сохранить как...", command=self._browse_output, width=16)
        self.btn_save_as.grid(row=0, column=1, padx=(0, 5))
        self.btn_run = ttk.Button(out_frame, text="Объединить", command=self._run_merge_default, width=15)
        self.btn_run.grid(row=0, column=2, padx=(0, 5))
        self.btn_cancel = ttk.Button(out_frame, text="Отмена", command=self._cancel_merge, width=10, state="disabled")
        self.btn_cancel.grid(row=0, column=3)

        btn_frame = ttk.Frame(main_frame)
        btn_frame.grid(row=5, column=0, columnspan=3, pady=(5, 5))

        self.btn_exceptions = ttk.Button(btn_frame, text="Настроить исключения", command=self._open_exceptions, width=26)
        self.btn_exceptions.pack(side=tk.LEFT)

        self.exception_count_var = tk.StringVar(value="")
        self.exception_count_label = ttk.Label(main_frame, textvariable=self.exception_count_var,
                                                foreground="#ffd700", font=("Consolas", 9))
        self.exception_count_label.grid(row=6, column=0, columnspan=3, sticky=tk.W, pady=(0, 2))

        self.status_var = tk.StringVar(value="Готов к работе")
        ttk.Label(main_frame, textvariable=self.status_var, foreground="#aaaaaa").grid(
            row=7, column=0, columnspan=3, sticky=tk.W, pady=(0, 0))

        self.progress = ttk.Progressbar(main_frame, mode="determinate", length=660)
        self.progress.grid(row=8, column=0, columnspan=3, sticky=tk.EW, pady=(5, 0))

        main_frame.columnconfigure(1, weight=1)

    def _update_history(self):
        self.history_combo["values"] = self.settings.folder_history if self.settings.folder_history else []

    def _update_exception_count(self):
        folder = self.settings.current_folder
        if folder:
            local = len(self.settings.get_current_exceptions())
            glbl = len(self.settings.global_exceptions)
            total_rules = local + glbl
            ec = getattr(self, "_excluded_counts", {})
            lines = [
                f"Исключений для «{os.path.basename(folder)}»: {total_rules}",
                f"Для этой папки - {local}",
                f"Общих исключений - {glbl}",
                f"Файлов исключено - {ec.get('total', 0)} (глобал: {ec.get('global', 0)}, локал: {ec.get('local', 0)})",
            ]
            self.exception_count_var.set("\n".join(lines))
            self.exception_count_label.configure(wraplength=800)
        else:
            self.exception_count_var.set("")

    def _on_history_select(self, event=None):
        path = self.history_combo.get()
        if path and os.path.isdir(path):
            self.dir_path.set(path)
            self._commit_dir()
        else:
            messagebox.showwarning("Внимание", "Папка больше не существует:\n" + path)
            self._remove_from_history()

    def _remove_from_history(self):
        path = self.history_combo.get()
        if path and path in self.settings.folder_history:
            self.settings.folder_history.remove(path)
            if self.settings.last_folder and os.path.normcase(path) == os.path.normcase(self.settings.last_folder):
                self.settings.last_folder = self.settings.folder_history[0] if self.settings.folder_history else ""
            if self.settings.current_folder and os.path.normcase(path) == os.path.normcase(self.settings.current_folder):
                self.settings.current_folder = ""
                self.dir_path.set("")
                self._update_exception_count()
                self._excluded_preview_cache.clear()
            elif os.path.normcase(path) == os.path.normcase(self.dir_path.get().strip()):
                self.dir_path.set("")
            if not self.settings._save():
                messagebox.showwarning("Ошибка сохранения",
                    "Не удалось сохранить настройки.\nПроверьте права доступа к папке config.")
            self._update_history()
            self.history_combo.set("")

    def _commit_dir(self):
        path = self.dir_path.get().strip()
        if os.path.isdir(path):
            if not self.settings.set_current_folder(path):
                messagebox.showwarning("Ошибка сохранения",
                    "Не удалось сохранить настройки.\nПроверьте права доступа к папке config.")
            self._update_history()
            self._update_exception_count()
            self._update_excluded_preview()

    def _browse_dir(self):
        path = filedialog.askdirectory(title="Выберите папку для объединения")
        if path:
            self.dir_path.set(path)
            self._commit_dir()

    def _browse_output(self):
        path = filedialog.asksaveasfilename(
            title="Сохранить как", defaultextension=".txt",
            filetypes=[("Текстовые файлы", "*.txt"), ("Все файлы", "*.*")])
        if path:
            self.out_path.set(path)
            self._run_merge()

    def _open_dumps(self):
        os.makedirs(DUMPS_DIR, exist_ok=True)
        subprocess.Popen(["explorer", DUMPS_DIR])

    def _set_default_out_path(self):
        os.makedirs(DUMPS_DIR, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S-%f")
        self.out_path.set(os.path.join(DUMPS_DIR, f"{ts}.txt"))

    def _update_excluded_preview(self):
        source = self.dir_path.get().strip()
        if not os.path.isdir(source):
            log.debug("Preview: source not a dir: %s", source)
            self._excluded_counts = {}
            self._excluded_count = 0
            self._update_exception_count()
            self.status_var.set("Готов к работе")
            return
        try:
            local = self.settings.get_current_exceptions()
            glbl = self.settings.global_exceptions
            log.info("Preview: source=%s local=%d glbl=%d",
                     source, len(local), len(glbl))
            if local:
                log.debug("Preview local rules: %s", [e.get("name") for e in local])
        except Exception as e:
            log.warning("Failed to get exceptions for preview: %s", e)
            return

        cache_key = (source, json.dumps(local, sort_keys=True), json.dumps(glbl, sort_keys=True))
        cached = self._excluded_preview_cache.get(cache_key)
        if cached is not None:
            self._excluded_counts = cached
            self._excluded_count = cached["total"]
            log.info("Preview result (cached): total=%d global=%d local=%d",
                     cached["total"], cached["global"], cached["local"])
            self._update_exception_count()
            return

        if self._excluded_preview_running:
            self._excluded_preview_pending = True
            log.debug("Preview: scan already running, deferring")
            return

        self._excluded_preview_running = True
        self._excluded_preview_pending = False
        self.status_var.set("Подсчёт исключений...")

        def _run():
            try:
                result = count_excluded(source, local, glbl)
                self.root.after(0, _done, result)
            except Exception as e:
                log.warning("Pre-scan failed: %s", e)
                self.root.after(0, _done, None)

        def _done(result):
            self._excluded_preview_running = False
            if result is not None:
                if len(self._excluded_preview_cache) >= 5:
                    self._excluded_preview_cache.pop(next(iter(self._excluded_preview_cache)))
                self._excluded_preview_cache[cache_key] = result
                self._excluded_counts = result
                self._excluded_count = result["total"]
                log.info("Preview result: total=%d global=%d local=%d",
                         result["total"], result["global"], result["local"])
                self._update_exception_count()
            self.status_var.set("Готов к работе")
            if self._excluded_preview_pending:
                self._excluded_preview_pending = False
                self.root.after(10, self._update_excluded_preview)

        threading.Thread(target=_run, daemon=True).start()

    def _open_exceptions(self):
        if self._exceptions_window is not None and self._exceptions_window.win.winfo_exists():
            self._exceptions_window.win.lift()
            self._exceptions_window.win.focus_force()
            return
        self._exceptions_window = ExceptionsWindow(
            self.root, self.settings,
            on_change=self._update_excluded_preview,
            close_callback=lambda: self._on_exceptions_window_closed()
        )
        log.info("After _open_exceptions: excluded_count=%d", self._excluded_count)

    def _on_exceptions_window_closed(self):
        self._exceptions_window = None

    def _poll_worker(self):
        try:
            self._worker.poll()
        except Exception:
            log.exception("Worker poll failed")
        finally:
            if not self._closing:
                try:
                    self.root.after(100, self._poll_worker)
                except RuntimeError:
                    pass

    def _on_progress(self, value):
        try:
            self.progress.configure(value=value)
        except Exception:
            pass

    def _on_success(self, count, output, walk_errors, excluded_counts):
        self._excluded_count = excluded_counts["total"]
        self._excluded_counts = excluded_counts
        self._update_exception_count()
        self._set_idle()
        msg = (
            f"Обработано файлов: {count}\n"
            f"Исключено из обхода: {excluded_counts['total']} "
            f"(глобал: {excluded_counts['global']}, локал: {excluded_counts['local']})\n"
            f"Результат сохранён:\n{output}"
        )
        log.info("Merge success: written=%d excluded=%d global=%d local=%d errors=%d",
                 count, excluded_counts["total"], excluded_counts["global"],
                 excluded_counts["local"], len(walk_errors))
        if walk_errors:
            err_preview = "\n".join(walk_errors[:10])
            if len(walk_errors) > 10:
                err_preview += f"\n... и ещё ошибок: {len(walk_errors) - 10}"
            msg += f"\n\nВнимание: возникли ошибки при обходе папок ({len(walk_errors)}):\n{err_preview}"
            messagebox.showwarning("Готово с предупреждениями", msg)
            self.status_var.set(f"Готово: {count} файлов, ошибок обхода: {len(walk_errors)}")
        else:
            messagebox.showinfo("Готово", msg)
            self.status_var.set(f"Готово: {count} файлов, исключено: {excluded_counts['total']}")

    def _on_cancelled(self, count, output, walk_errors, excluded_counts):
        self._excluded_count = excluded_counts["total"]
        self._excluded_counts = excluded_counts
        self._update_exception_count()
        self._set_idle()
        log.info("Merge cancelled by user, processed=%d excluded=%d global=%d local=%d",
                 count, excluded_counts["total"], excluded_counts["global"],
                 excluded_counts["local"])
        messagebox.showwarning("Отменено", f"Объединение прервано.\nФайлов обработано: {count}")
        self.status_var.set("Объединение отменено")

    def _on_error(self, error):
        log.error("Merge error dialog: %s", error[:200])
        self._set_idle()
        messagebox.showerror("Ошибка", error)

    def _set_idle(self):
        self.btn_run.config(state="normal")
        self.btn_cancel.config(state="disabled")
        self.history_combo.config(state="readonly")
        self.btn_history_delete.config(state="normal")
        self.dir_entry.config(state="normal")
        self.btn_browse_dir.config(state="normal")
        self.btn_open_dumps.config(state="normal")
        self.btn_save_as.config(state="normal")
        self.btn_exceptions.config(state="normal")
        self.status_var.set("Готов к работе")

    def _run_merge_default(self):
        self._set_default_out_path()
        self._run_merge()

    def _run_merge(self):
        if self._worker.merging:
            log.debug("Merge already in progress, ignoring")
            return

        raw_source = self.dir_path.get().strip()
        output = self.out_path.get().strip()

        if not raw_source:
            messagebox.showerror("Ошибка", "Выберите исходную папку")
            return
        if not output:
            messagebox.showerror("Ошибка", "Укажите имя выходного файла")
            return
        if os.path.exists(output) and os.path.isdir(output):
            messagebox.showerror("Ошибка", "Выходной путь является папкой, а не файлом")
            return

        if os.path.exists(output):
            if not messagebox.askyesno("Подтверждение", "Файл уже существует. Перезаписать?"):
                return

        source = os.path.abspath(raw_source)
        if not os.path.isdir(source):
            messagebox.showerror("Ошибка", f"Папка не найдена:\n{source}")
            return

        output_abs = os.path.normcase(os.path.realpath(output))
        source_abs = os.path.normcase(os.path.realpath(source))
        if output_abs == source_abs or output_abs.startswith(source_abs.rstrip(os.sep) + os.sep):
            log.warning("Cycle prevented: output inside source. output=%s source=%s", output, source)
            messagebox.showerror("Ошибка", "Выходной файл находится внутри исходной папки.\nЭто приведёт к зацикливанию.")
            return

        self.settings.set_current_folder(source)

        try:
            is_empty = not any(os.scandir(source))
        except OSError as e:
            messagebox.showerror("Ошибка", f"Нет доступа к папке:\n{source}\n\n{e}")
            return

        if is_empty:
            messagebox.showerror("Ошибка", "Исходная папка пуста")
            return

        log.info("Starting merge: source=%s output=%s", source, output)

        self.btn_run.config(state="disabled")
        self.btn_cancel.config(state="normal")
        self.history_combo.config(state="disabled")
        self.btn_history_delete.config(state="disabled")
        self.dir_entry.config(state="disabled")
        self.btn_browse_dir.config(state="disabled")
        self.btn_open_dumps.config(state="disabled")
        self.btn_save_as.config(state="disabled")
        self.btn_exceptions.config(state="disabled")
        self.status_var.set("Объединение файлов...")
        self.progress.configure(value=0)
        self._excluded_count = 0
        self._excluded_counts = {}
        self._update_exception_count()

        exceptions_snapshot = self.settings.get_current_exceptions()
        self._worker.start(source, output, exceptions_snapshot)

    def _cancel_merge(self):
        log.info("Cancel button pressed")
        self._worker.cancel()
        self.btn_cancel.config(state="disabled")
        self.status_var.set("Отмена...")

    def _on_close(self):
        if self._worker.merging:
            if not messagebox.askokcancel("Внимание", "Объединение ещё выполняется.\nЗакрыть — данные будут потеряны."):
                return
            log.info("Closing while merge in progress")
            self._worker.cancel()
            self._worker.join(timeout=2.0)
        self._closing = True
        log.info("Application closing")
        self.root.destroy()

    def run(self):
        self.root.mainloop()
