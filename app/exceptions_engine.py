import os
import fnmatch

from .logger import get_logger

log = get_logger(__name__)

SCOPE_ALL = "all"
SCOPE_ROOT = "root"
SCOPE_PATH = "path"


def _is_subpath(path, parent):
    path = os.path.normcase(os.path.normpath(path))
    parent = os.path.normcase(os.path.normpath(parent))
    if path == parent:
        return True
    return path.startswith(parent.rstrip(os.sep) + os.sep)


def _norm_rel_to_abs(rel_path, source_folder):
    if not source_folder:
        return ""
    return os.path.normcase(os.path.normpath(os.path.join(source_folder, rel_path)))


def is_excluded(rel_full_path, exceptions, source_folder=""):
    rel_full_path = os.path.normpath(rel_full_path.replace("/", os.sep).replace("\\", os.sep))
    item_name = os.path.basename(rel_full_path)
    rel_dir = os.path.dirname(rel_full_path)

    for entry in exceptions:
        ename = entry.get("name", "")
        scope = entry.get("scope", SCOPE_ALL)
        scope_path = entry.get("path", "")

        if scope == SCOPE_PATH and scope_path:
            if not source_folder:
                continue
            sp_norm = os.path.normcase(os.path.normpath(scope_path))
            if not os.path.isabs(scope_path):
                sp_norm = os.path.normcase(os.path.normpath(os.path.join(source_folder, scope_path)))
            target_abs = _norm_rel_to_abs(rel_dir or ".", source_folder)
            if not _is_subpath(target_abs, sp_norm):
                continue
        elif scope == SCOPE_ROOT:
            if rel_dir:
                continue
        elif scope == SCOPE_PATH and not scope_path:
            if rel_dir:
                continue

        if os.path.isabs(ename) and source_folder:
            abs_item = rel_full_path if os.path.isabs(rel_full_path) else os.path.join(source_folder, rel_full_path)
            abs_item = os.path.normcase(os.path.normpath(abs_item))
            pattern = os.path.normcase(os.path.normpath(ename))

            if fnmatch.fnmatch(abs_item, pattern):
                log.debug("Local EXCLUDED (abs path) %s", rel_full_path)
                return True

            if not any(ch in ename for ch in "*?["):
                if _is_subpath(abs_item, ename):
                    log.debug("Local EXCLUDED (subpath) %s", rel_full_path)
                    return True

        if fnmatch.fnmatch(os.path.normcase(rel_full_path), os.path.normcase(ename)):
            log.debug("Local EXCLUDED (full path) %s", rel_full_path)
            return True

        if fnmatch.fnmatch(os.path.normcase(item_name), os.path.normcase(ename)):
            log.debug("Local EXCLUDED (name) %s == %s", item_name, ename)
            return True

    return False


def format_entry(entry):
    name = entry.get("name", "")
    scope = entry.get("scope", SCOPE_ALL)
    scope_path = entry.get("path", "")

    if os.path.isabs(name):
        return f"[путь] {name}"

    if scope == SCOPE_ROOT:
        return f"[корень] {name}"
    elif scope == SCOPE_PATH and scope_path:
        return f"[{scope_path}] {name}"
    elif scope == SCOPE_PATH and not scope_path:
        return f"[корень] {name}"
    else:
        return f"[везде] {name}"


class Exclusions:
    def __init__(self, local_exceptions, global_exceptions, source_folder=""):
        self.local = local_exceptions
        self.global_exceptions = global_exceptions
        self.source = source_folder
        self.excluded_count = 0
        self.excluded_by_global = 0
        self.excluded_by_local = 0
        log.info(
            "Exclusions created: %d local, %d global | source=%s",
            len(local_exceptions), len(global_exceptions), source_folder
        )
        if global_exceptions:
            log.debug("Global rules: %s", [
                f"{e['name']}(enabled={e.get('enabled', True)})"
                for e in global_exceptions if isinstance(e, dict) and isinstance(e.get("name"), str)
            ])

    def is_excluded(self, name, is_dir, rel_full_path):
        for ex in self.global_exceptions:
            if not isinstance(ex, dict):
                continue
            if not ex.get("enabled", True):
                continue
            ename = ex.get("name")
            if not isinstance(ename, str):
                continue
            pattern = os.path.normcase(ename)
            if (
                fnmatch.fnmatch(os.path.normcase(name), pattern)
                or fnmatch.fnmatch(os.path.normcase(rel_full_path), pattern)
            ):
                self.excluded_count += 1
                self.excluded_by_global += 1
                log.debug("GLOBAL excluded: %s matched rule '%s'", name, ename)
                return "global"

        result = is_excluded(rel_full_path, self.local, self.source)
        if result:
            self.excluded_count += 1
            self.excluded_by_local += 1
            log.debug("LOCAL excluded: %s", name)
            return "local"
        return ""


def count_excluded(source_folder, local_exceptions, global_exceptions):
    """Pre-scan: count how many files would be excluded by current rules.

    When a directory is excluded, all files inside it are also counted.
    Returns dict: {total, global, local}.
    """
    exclusions = Exclusions(local_exceptions, global_exceptions, source_folder)
    log.info("Pre-scan counting excluded in %s ...", source_folder)
    for root, dirs, files in os.walk(source_folder):
        rel_dir = os.path.relpath(root, source_folder)
        if rel_dir == ".":
            rel_dir = ""
        filtered = []
        for d in dirs:
            rel_full = os.path.join(rel_dir, d) if rel_dir else d
            level = exclusions.is_excluded(d, is_dir=True, rel_full_path=rel_full)
            if level:
                exclusions.excluded_count -= 1
                if level == "global":
                    exclusions.excluded_by_global -= 1
                elif level == "local":
                    exclusions.excluded_by_local -= 1
                inner = 0
                for sub_root, sub_dirs, sub_files in os.walk(os.path.join(root, d)):
                    inner += len(sub_files)
                exclusions.excluded_count += inner
                if level == "global":
                    exclusions.excluded_by_global += inner
                elif level == "local":
                    exclusions.excluded_by_local += inner
            else:
                filtered.append(d)
        dirs[:] = filtered
        for file in files:
            rel_full = os.path.join(rel_dir, file) if rel_dir else file
            exclusions.is_excluded(file, is_dir=False, rel_full_path=rel_full)
    log.info("Pre-scan done: %d items excluded", exclusions.excluded_count)
    return {
        "total": exclusions.excluded_count,
        "global": exclusions.excluded_by_global,
        "local": exclusions.excluded_by_local,
    }
