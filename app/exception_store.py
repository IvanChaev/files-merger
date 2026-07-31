import os

from .exceptions_engine import SCOPE_ALL, SCOPE_ROOT, SCOPE_PATH
from .logger import get_logger

ALLOWED_SCOPES = {SCOPE_ALL, SCOPE_ROOT, SCOPE_PATH}

log = get_logger(__name__)


class ExceptionStore:
    def __init__(self, settings):
        self._settings = settings

    def get_current_exceptions(self):
        result = self._settings.all_exceptions.get(
            os.path.normcase(self._settings.current_folder), []
        ).copy()
        log.debug("get_current_exceptions: folder=%s count=%d",
                  self._settings.current_folder, len(result))
        return result

    def save_current_exceptions(self, exceptions_list):
        key = os.path.normcase(self._settings.current_folder)
        old_value = self._settings.all_exceptions.get(key)
        self._settings.all_exceptions[key] = exceptions_list.copy()
        if not self._settings._save_local_exceptions():
            if old_value is not None:
                self._settings.all_exceptions[key] = old_value
            elif key in self._settings.all_exceptions:
                del self._settings.all_exceptions[key]
            log.error("Failed to save local exceptions, rollback")
            return False
        log.info("Saved %d local exceptions for folder=%s", len(exceptions_list), key)
        return True

    def add_exception(self, name, scope, scope_path):
        if scope not in ALLOWED_SCOPES:
            scope = SCOPE_ALL
        name = name.strip()
        if not name:
            log.warning("add_exception: empty name")
            return False
        if scope == "path" and not scope_path.strip():
            log.warning("add_exception: scope=path but empty scope_path")
            return False
        name = os.path.normpath(name.replace("/", os.sep).replace("\\", os.sep))
        sp = scope_path.strip().replace("/", os.sep).replace("\\", os.sep)
        scope_path = os.path.normpath(sp) if sp and sp not in (".", "\\", "/") else ""
        entry = {"name": name, "scope": scope, "path": scope_path}
        current = self.get_current_exceptions()
        for existing in current:
            if (os.path.normcase(existing.get("name", "")) == os.path.normcase(entry.get("name", ""))
                    and existing.get("scope") == entry.get("scope")
                    and os.path.normcase(existing.get("path", "")) == os.path.normcase(entry.get("path", ""))):
                log.debug("add_exception: duplicate skipped %s", name)
                return False
        current.append(entry)
        if not self.save_current_exceptions(current):
            log.error("Failed to add local exception (save failed): %s", name)
            return False
        log.info("Added local exception: %s (scope=%s)", name, scope)
        return True

    def remove_exception(self, index):
        current = self.get_current_exceptions()
        if 0 <= index < len(current):
            removed = current.pop(index)
            if self.save_current_exceptions(current):
                log.info("Removed local exception #%d: %s", index, removed.get("name"))
                return True
            log.error("Failed to remove local exception (save failed)")
            return False
        log.warning("remove_exception: index %d out of range (len=%d)", index, len(current))
        return False

    def clear_exceptions(self):
        count = len(self.get_current_exceptions())
        if self.save_current_exceptions([]):
            log.info("Cleared %d local exceptions", count)
            return True
        log.error("Failed to clear local exceptions (save failed)")
        return False

    def add_global_exception(self, name):
        name = name.strip()
        if not name:
            return False
        name_lower = name.lower()
        for ex in self._settings.global_exceptions:
            if ex["name"].lower() == name_lower:
                log.debug("add_global_exception: duplicate skipped %s", name)
                return False
        old = list(self._settings.global_exceptions)
        self._settings.global_exceptions.append({"name": name, "enabled": True})
        if not self._settings._save_global_exceptions():
            self._settings.global_exceptions = old
            log.error("Failed to save global exceptions after adding: %s", name)
            return False
        log.info("Added global exception: %s", name)
        return True

    def remove_global_exception(self, index):
        if 0 <= index < len(self._settings.global_exceptions):
            old = list(self._settings.global_exceptions)
            removed = self._settings.global_exceptions.pop(index)
            if not self._settings._save_global_exceptions():
                self._settings.global_exceptions = old
                log.error("Failed to save global exceptions after removing: %s", removed["name"])
                return False
            log.info("Removed global exception #%d: %s", index, removed["name"])
            return True
        return False

    def toggle_global_exception(self, index):
        if 0 <= index < len(self._settings.global_exceptions):
            old = [dict(e) for e in self._settings.global_exceptions]
            item = self._settings.global_exceptions[index]
            item["enabled"] = not item.get("enabled", True)
            if not self._settings._save_global_exceptions():
                self._settings.global_exceptions = old
                log.error("Failed to save global exceptions after toggle")
                return False
            log.info("Toggled global exception #%d '%s' -> enabled=%s",
                     index, item["name"], item["enabled"])
            return True
        return False
