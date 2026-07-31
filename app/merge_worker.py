import os
import threading
import queue
import traceback

from .logger import get_logger
from .merger import FolderMerger
from .exceptions_engine import Exclusions

log = get_logger(__name__)


class MergeWorker:
    def __init__(self, settings, progress_callback, success_callback, error_callback, cancel_callback=None):
        self.settings = settings
        self._progress = progress_callback
        self._on_success_cb = success_callback
        self._on_error_cb = error_callback
        self._on_cancel_cb = cancel_callback

        self._queue = queue.Queue()
        self._merging = False
        self._cancel_requested = False
        self._excluded_count = 0
        self._current_output = None
        self._worker_thread = None

    @property
    def merging(self):
        return self._merging

    @property
    def excluded_count(self):
        return self._excluded_count

    @property
    def cancel_requested(self):
        return self._cancel_requested

    @property
    def current_output(self):
        return self._current_output

    def start(self, source, output, exceptions_snapshot):
        self._merging = True
        self._cancel_requested = False
        self._excluded_count = 0
        self._current_output = output

        global_snapshot = [
            {"name": ex.get("name", ""), "enabled": bool(ex.get("enabled", True))}
            for ex in self.settings.global_exceptions
        ]

        log.info("Starting merge: source=%s output=%s local_exceptions=%d",
                 source, output, len(exceptions_snapshot))
        log.debug("Global exceptions (snapshot): %s", global_snapshot)
        self._worker_thread = threading.Thread(
            target=self._thread,
            args=(source, output, exceptions_snapshot, global_snapshot),
            daemon=True
        )
        self._worker_thread.start()

    def cancel(self):
        log.info("Cancel requested")
        self._cancel_requested = True

    def join(self, timeout=None):
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=timeout)

    def poll(self):
        try:
            while True:
                msg = self._queue.get_nowait()
                if msg[0] == "progress":
                    self._progress(msg[1])
                elif msg[0] == "success":
                    ec = msg[4]
                    log.info("Merge success: count=%d excluded=%d (global=%d local=%d) errors=%d",
                             msg[1], ec["total"], ec["global"], ec["local"], len(msg[3]))
                    self._merging = False
                    self._on_success_cb(msg[1], msg[2], msg[3], ec)
                elif msg[0] == "cancelled":
                    ec = msg[4]
                    log.info("Merge cancelled: count=%d excluded=%d (global=%d local=%d) errors=%d",
                             msg[1], ec["total"], ec["global"], ec["local"], len(msg[3]))
                    self._merging = False
                    if self._on_cancel_cb:
                        self._on_cancel_cb(msg[1], msg[2], msg[3], ec)
                elif msg[0] == "error":
                    log.error("Merge error: %s", msg[1][:200])
                    self._merging = False
                    self._on_error_cb(msg[1])
        except queue.Empty:
            pass

        if (self._merging and self._worker_thread is not None
                and not self._worker_thread.is_alive()
                and self._queue.empty()):
            log.error("Merge thread died without result")
            self._merging = False
            self._on_error_cb("Поток объединения завершился без результата.")

    def _thread(self, source, output, exceptions_snapshot, global_snapshot):
        tmp_output = output + ".part"
        try:
            exclusions = Exclusions(
                local_exceptions=exceptions_snapshot,
                global_exceptions=global_snapshot,
                source_folder=source
            )
            merger = FolderMerger(
                exclusions,
                cancel_target=self,
                progress_callback=lambda v: self._queue.put(("progress", v))
            )
            count, walk_errors = merger.merge(source, tmp_output)
            if os.path.exists(tmp_output):
                if merger.was_cancelled:
                    os.remove(tmp_output)
                    log.info("Temp output removed (cancelled): %s", tmp_output)
                else:
                    try:
                        os.replace(tmp_output, output)
                        log.info("Output saved: %s", output)
                    except Exception as e:
                        log.exception("Failed to replace output")
                        self._queue.put((
                            "error",
                            f"Не удалось сохранить результат:\n{e}\n\n"
                            f"Временный файл сохранён:\n{tmp_output}"
                        ))
                        return
            self._excluded_count = merger.exclusions.excluded_count
            excluded_counts = {
                "total": merger.exclusions.excluded_count,
                "global": merger.exclusions.excluded_by_global,
                "local": merger.exclusions.excluded_by_local,
            }
            log.info("Thread done: written=%d excluded=%d (global=%d local=%d) walk_errors=%d",
                     count, self._excluded_count,
                     excluded_counts["global"], excluded_counts["local"],
                     len(walk_errors))
            if merger.was_cancelled:
                self._queue.put(("cancelled", count, output, walk_errors, excluded_counts))
            else:
                self._queue.put(("success", count, output, walk_errors, excluded_counts))
        except Exception as e:
            log.exception("Merge thread exception")
            try:
                if os.path.exists(tmp_output):
                    os.remove(tmp_output)
            except Exception:
                pass
            tb = traceback.format_exc()
            self._queue.put(("error", f"{e}\n\n{tb}" if tb else str(e)))
