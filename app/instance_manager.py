import os
import ctypes

from .logger import get_logger

log = get_logger(__name__)


class InstanceManager:
    def __init__(self):
        self._mutex = None

    def acquire_mutex(self):
        try:
            self._mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\FolderMerger_SingleInstance")
            log.debug("CreateMutexW -> %s", self._mutex)
            ret = ctypes.windll.kernel32.WaitForSingleObject(self._mutex, 0)
            log.debug("WaitForSingleObject -> %d", ret)
            WAIT_OBJECT_0 = 0
            WAIT_ABANDONED = 0x80
            if ret in (WAIT_OBJECT_0, WAIT_ABANDONED):
                log.info("Mutex acquired — first instance")
                return True
            log.info("Another instance is already running")
            ctypes.windll.kernel32.CloseHandle(self._mutex)
            self._mutex = None
            return False
        except Exception as e:
            log.error("Mutex failed: %s", e)
            return False

    def release_mutex(self):
        if self._mutex:
            try:
                ctypes.windll.kernel32.ReleaseMutex(self._mutex)
                ctypes.windll.kernel32.CloseHandle(self._mutex)
                log.debug("Mutex released")
            except Exception as e:
                log.error("Failed to release mutex: %s", e)
            self._mutex = None

    def run(self, startup):
        if not self.acquire_mutex():
            log.info("Another instance is running, exiting")
            ctypes.windll.user32.MessageBoxW(None, "Программа уже запущена.", "Folder Merger", 0)
            return
        try:
            startup()
        finally:
            self.release_mutex()
