import json
import os
import shutil

from .exceptions_engine import SCOPE_ALL, SCOPE_ROOT, SCOPE_PATH
from .exception_store import ExceptionStore
from .logger import get_logger

log = get_logger(__name__)

SETTINGS_FILE = "settings.json"
LOCAL_EXCEPTIONS_FILE = "local_exceptions.json"
GLOBAL_EXCEPTIONS_FILE = "global_exceptions.json"
OLD_EXCEPTIONS_FILE = "exceptions.json"
ALLOWED_SCOPES = {SCOPE_ALL, SCOPE_ROOT, SCOPE_PATH}

GLOBAL_DEFAULTS = [
    "logs", "dumps", "__pycache__", ".git", "node_modules",
    "*.tmp", "*.log", "Thumbs.db", ".DS_Store",
]


class SettingsManager:
    def __init__(self, config_dir):
        self.config_dir = config_dir
        self.settings_path = os.path.join(config_dir, SETTINGS_FILE)
        self.local_exceptions_path = os.path.join(config_dir, LOCAL_EXCEPTIONS_FILE)
        self.global_exceptions_path = os.path.join(config_dir, GLOBAL_EXCEPTIONS_FILE)
        self.old_path = os.path.join(config_dir, OLD_EXCEPTIONS_FILE)

        self.current_folder = ""
        self.last_folder = ""
        self.folder_history = []
        self.all_exceptions = {}
        self.global_exceptions = []
        self._load_failed = False

        self._store = ExceptionStore(self)
        self._last_save_ok = True
        self._ensure_config_dir()
        self._load()
        self._load_global_exceptions()
        self._load_local_exceptions()
        self._migrate_old()

        if self.last_folder and os.path.isdir(self.last_folder):
            log.info("Restoring last folder: %s", self.last_folder)
            self.set_current_folder(self.last_folder)

    def _ensure_config_dir(self):
        if not os.path.exists(self.config_dir):
            os.makedirs(self.config_dir, exist_ok=True)
            log.info("Created config dir: %s", self.config_dir)
        for f in os.listdir(self.config_dir):
            if f.endswith(".tmp"):
                try:
                    os.remove(os.path.join(self.config_dir, f))
                except Exception:
                    pass

    def _load_global_exceptions(self):
        if os.path.exists(self.global_exceptions_path):
            try:
                with open(self.global_exceptions_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    cleaned = []
                    for item in data:
                        if not isinstance(item, dict):
                            continue
                        name = item.get("name", "").strip()
                        if not name:
                            continue
                        cleaned.append({
                            "name": name,
                            "enabled": bool(item.get("enabled", True))
                        })
                    self.global_exceptions = cleaned
                    log.info("Loaded %d global exceptions from %s", len(cleaned), self.global_exceptions_path)
                    return
            except Exception as e:
                log.warning("Failed to load global exceptions: %s", e)
        # also check in old settings.json for migration
        self._migrate_global_from_settings()
        # First launch: seed defaults only when file never existed
        if not self.global_exceptions:
            self.global_exceptions = [
                {"name": name, "enabled": True}
                for name in GLOBAL_DEFAULTS
            ]
            self._save_global_exceptions()
            log.info("Seeded %d default global exceptions", len(self.global_exceptions))

    def _migrate_global_from_settings(self):
        if not os.path.exists(self.settings_path):
            return
        try:
            with open(self.settings_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            old = data.get("global_exceptions", [])
            if isinstance(old, list) and old:
                cleaned = []
                for item in old:
                    if not isinstance(item, dict):
                        continue
                    name = item.get("name", "").strip()
                    if not name:
                        continue
                    cleaned.append({
                        "name": name,
                        "enabled": bool(item.get("enabled", True))
                    })
                if cleaned:
                    self.global_exceptions = cleaned
                    self._save_global_exceptions()
                    log.info("Migrated %d global exceptions from settings.json", len(cleaned))
        except Exception as e:
            log.warning("Global migration from settings.json failed: %s", e)

    @staticmethod
    def _atomic_json_write(path, data):
        tmp_path = path + ".tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=True, indent=4)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, path)
        except Exception as e:
            try:
                os.remove(tmp_path)
            except Exception:
                pass
            raise e

    def _save_global_exceptions(self):
        self._last_save_ok = True
        try:
            self._atomic_json_write(self.global_exceptions_path, self.global_exceptions)
            log.debug("Global exceptions saved")
            return True
        except Exception as e:
            self._last_save_ok = False
            log.error("Failed to save global exceptions: %s", e)
            return False

    def _load_local_exceptions(self):
        if os.path.exists(self.local_exceptions_path):
            try:
                with open(self.local_exceptions_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    normalized = {}
                    for k, v in data.items():
                        nk = os.path.normcase(os.path.normpath(k))
                        if isinstance(v, list):
                            cleaned = []
                            for e in v:
                                if not isinstance(e, dict):
                                    continue
                                name = e.get("name")
                                if not isinstance(name, str) or not name.strip():
                                    continue
                                scope = e.get("scope", SCOPE_ALL)
                                if scope not in ALLOWED_SCOPES:
                                    scope = SCOPE_ALL
                                path = e.get("path", "")
                                if not isinstance(path, str):
                                    path = ""
                                if path in (".", None):
                                    path = ""
                                cleaned.append({"name": name, "scope": scope, "path": path})
                            normalized[nk] = cleaned
                        else:
                            normalized[nk] = []
                    self.all_exceptions = normalized
                    log.info("Loaded %d folder exception sets from %s", len(normalized), self.local_exceptions_path)
                    return
            except Exception as e:
                log.warning("Failed to load local exceptions: %s", e)
        self._migrate_local_from_settings()

    def _migrate_local_from_settings(self):
        if not os.path.exists(self.settings_path):
            return
        try:
            with open(self.settings_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            old = data.get("exceptions", {})
            if isinstance(old, dict) and old:
                normalized = {}
                for k, v in old.items():
                    nk = os.path.normcase(os.path.normpath(k))
                    if isinstance(v, list):
                        cleaned = []
                        for e in v:
                            if not isinstance(e, dict):
                                continue
                            name = e.get("name")
                            if not isinstance(name, str) or not name.strip():
                                continue
                            scope = e.get("scope", SCOPE_ALL)
                            if scope not in ALLOWED_SCOPES:
                                scope = SCOPE_ALL
                            path = e.get("path", "")
                            if not isinstance(path, str):
                                path = ""
                            if path in (".", None):
                                path = ""
                            cleaned.append({"name": name, "scope": scope, "path": path})
                        normalized[nk] = cleaned
                if normalized:
                    self.all_exceptions = normalized
                    self._save_local_exceptions()
                    log.info("Migrated %d folder exception sets from settings.json", len(normalized))
        except Exception as e:
            log.warning("Local migration from settings.json failed: %s", e)

    def _save_local_exceptions(self):
        self._last_save_ok = True
        try:
            self._atomic_json_write(self.local_exceptions_path, self.all_exceptions)
            log.debug("Local exceptions saved")
            return True
        except Exception as e:
            self._last_save_ok = False
            log.error("Failed to save local exceptions: %s", e)
            return False

    def _migrate_old(self):
        if not os.path.exists(self.old_path):
            return
        log.info("Found old exceptions.json, attempting migration")
        try:
            with open(self.old_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            raw = data.get("exceptions", [])
            if raw and self.last_folder:
                parsed = []
                for item in raw:
                    if isinstance(item, dict):
                        parsed.append(item)
                    elif isinstance(item, str):
                        parsed.append({"name": item, "scope": SCOPE_ALL, "path": ""})
                if parsed:
                    lk = os.path.normcase(self.last_folder)
                    existing = self.all_exceptions.get(lk, [])
                    existing_names = {(e.get("name", ""), e.get("scope")) for e in existing}
                    for e in parsed:
                        if (e.get("name", ""), e.get("scope")) not in existing_names:
                            existing.append(e)
                    self.all_exceptions[lk] = existing
                    if self._save_local_exceptions():
                        os.remove(self.old_path)
                        log.info("Removed old exceptions.json")
                        log.info("Migrated %d exceptions from old format", len(parsed))
                    else:
                        log.error("Migration aborted: failed to save local exceptions")
        except Exception as e:
            log.warning("Migration failed: %s", e)

    def _load(self):
        has_path = os.path.exists(self.settings_path)
        has_bak = os.path.exists(self.settings_path + ".bak")

        loaded = False
        if has_path:
            loaded = self._try_load_from(self.settings_path)
        if not loaded and has_bak:
            log.info("Settings file corrupt, trying backup")
            loaded = self._try_load_from(self.settings_path + ".bak")
            if loaded:
                try:
                    shutil.copy2(self.settings_path + ".bak", self.settings_path)
                    log.info("Restored settings from backup")
                except Exception:
                    pass

        self._load_failed = not loaded
        if loaded:
            log.info("Settings loaded successfully")
        else:
            log.warning("No settings file found, using defaults")

    def _try_load_from(self, path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                data = {}
            self.last_folder = data.get("last_folder", "")
            if not isinstance(self.last_folder, str):
                self.last_folder = ""
            elif self.last_folder:
                self.last_folder = os.path.normpath(self.last_folder)
            self.folder_history = data.get("folder_history", [])
            if not isinstance(self.folder_history, list):
                self.folder_history = []
            else:
                self.folder_history = [os.path.normpath(p) for p in self.folder_history if isinstance(p, str)]
                seen = set()
                deduped = []
                for p in self.folder_history:
                    pk = os.path.normcase(p)
                    if pk not in seen:
                        seen.add(pk)
                        deduped.append(p)
                self.folder_history = deduped
            return True
        except Exception as e:
            log.warning("Failed to load from %s: %s", path, e)
            return False

    def _save(self):
        self._last_save_ok = True
        if self._load_failed:
            log.warning("Save skipped: load failed flag set")
            self._last_save_ok = False
            return False
        try:
            data = {
                "last_folder": self.last_folder,
                "folder_history": self.folder_history,
            }
            tmp = self.settings_path + ".tmp"
            bak = self.settings_path + ".bak"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=True, indent=4)
                f.flush()
                os.fsync(f.fileno())
            if os.path.exists(self.settings_path):
                shutil.copy2(self.settings_path, bak)
            os.replace(tmp, self.settings_path)
            log.debug("Settings saved")
            return True
        except Exception:
            self._last_save_ok = False
            if os.path.exists(bak) and not os.path.exists(self.settings_path):
                try:
                    shutil.copy2(bak, self.settings_path)
                except Exception:
                    pass
            log.error("Failed to save settings")
            return False

    def set_current_folder(self, path):
        path = os.path.normpath(os.path.abspath(path))
        path_key = os.path.normcase(path)
        if self.current_folder:
            old_key = os.path.normcase(self.current_folder)
            current = self.get_current_exceptions()
            if current:
                self.all_exceptions[old_key] = current
            elif old_key in self.all_exceptions:
                del self.all_exceptions[old_key]

        self.current_folder = path

        if not any(os.path.normcase(p) == path_key for p in self.folder_history):
            self.folder_history.insert(0, path)
        else:
            self.folder_history = [p for p in self.folder_history if os.path.normcase(p) != path_key]
            self.folder_history.insert(0, path)
        self.folder_history = self.folder_history[:20]

        self.last_folder = path
        ok1 = self._save()
        ok2 = self._save_local_exceptions()
        log.info("Current folder set to: %s", path)
        return ok1 and ok2

    def get_current_exceptions(self):
        return self._store.get_current_exceptions()

    def save_current_exceptions(self, exceptions_list):
        self._store.save_current_exceptions(exceptions_list)

    def add_exception(self, name, scope, scope_path):
        return self._store.add_exception(name, scope, scope_path)

    def remove_exception(self, index):
        return self._store.remove_exception(index)

    def clear_exceptions(self):
        return self._store.clear_exceptions()

    def add_global_exception(self, name):
        return self._store.add_global_exception(name)

    def remove_global_exception(self, index):
        return self._store.remove_global_exception(index)

    def toggle_global_exception(self, index):
        return self._store.toggle_global_exception(index)
