import os

from .logger import get_logger

log = get_logger(__name__)


class FolderMerger:
    def __init__(self, exclusions, cancel_target=None, progress_callback=None):
        self.exclusions = exclusions
        self._cancel_target = cancel_target
        self._cancel_requested = lambda: cancel_target is not None and getattr(cancel_target, '_cancel_requested', False)
        self._progress = progress_callback
        self.was_cancelled = False

    def merge(self, source_dir, output_file):
        if not os.path.isdir(source_dir):
            raise ValueError(f"Папка не найдена: {source_dir}")

        output_path = os.path.realpath(output_file)
        output_norm = os.path.normcase(output_path)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        log.info("Merge started: source=%s output=%s", source_dir, output_file)

        if self._progress:
            self._progress(0)

        processed_files = []
        walk_errors = []

        def on_error(err):
            walk_errors.append(str(err))
            log.warning("Walk error: %s", err)

        for root, dirs, files in os.walk(source_dir, onerror=on_error):
            if self._cancel_requested():
                self.was_cancelled = True
                log.info("Merge cancelled during walk")
                return 0, walk_errors
            rel_dir = os.path.relpath(root, source_dir)
            if rel_dir == ".":
                rel_dir = ""

            filtered_dirs = []
            for d in dirs:
                rel_full = os.path.join(rel_dir, d) if rel_dir else d
                level = self.exclusions.is_excluded(d, is_dir=True, rel_full_path=rel_full)
                if level:
                    self.exclusions.excluded_count -= 1
                    if level == "global":
                        self.exclusions.excluded_by_global -= 1
                    elif level == "local":
                        self.exclusions.excluded_by_local -= 1
                    abs_d = os.path.join(root, d)
                    inner = 0
                    for sub_root, sub_dirs, sub_files in os.walk(abs_d):
                        inner += len(sub_files)
                    self.exclusions.excluded_count += inner
                    if level == "global":
                        self.exclusions.excluded_by_global += inner
                    elif level == "local":
                        self.exclusions.excluded_by_local += inner
                else:
                    filtered_dirs.append(d)
            if len(filtered_dirs) != len(dirs):
                log.debug("Filtered dirs in %s: %d -> %d", rel_dir or ".", len(dirs), len(filtered_dirs))
            dirs[:] = filtered_dirs

            for file in files:
                if self._cancel_requested():
                    self.was_cancelled = True
                    log.info("Merge cancelled during file scan")
                    return 0, walk_errors
                rel_full = os.path.join(rel_dir, file) if rel_dir else file
                if self.exclusions.is_excluded(file, is_dir=False, rel_full_path=rel_full):
                    continue

                file_path = os.path.join(root, file)
                if os.path.normcase(os.path.abspath(file_path)) == output_norm:
                    continue
                try:
                    if os.path.samefile(file_path, output_path):
                        continue
                except OSError:
                    pass
                if os.path.islink(file_path):
                    continue
                rel_path = os.path.relpath(file_path, source_dir)
                processed_files.append((rel_path, file_path))

        if self._progress:
            self._progress(10)

        log.info("Walk complete: %d files to process, %d walk errors, %d exclusions",
                 len(processed_files), len(walk_errors), self.exclusions.excluded_count)

        processed_files.sort(key=lambda x: os.path.normcase(x[0]))
        total = len(processed_files)

        written = 0
        with open(output_path, "wb") as out:
            for i, (rel_path, abs_path) in enumerate(processed_files):
                if self._cancel_requested():
                    self.was_cancelled = True
                    log.info("Merge cancelled during write at file %d/%d", i, total)
                    return written, walk_errors

                written += 1
                if total > 0:
                    pct = 10 + int(90 * i / total)
                    if self._progress:
                        self._progress(pct)

                header = f"{'=' * 80}\nФайл: {rel_path}\n{'=' * 80}\n\n"
                out.write(header.encode("utf-8", "replace"))

                try:
                    with open(abs_path, "rb") as f:
                        while True:
                            if self._cancel_requested():
                                self.was_cancelled = True
                                log.info("Merge cancelled during read of %s", rel_path)
                                return written, walk_errors
                            chunk = f.read(65536)
                            if not chunk:
                                break
                            out.write(chunk)
                except Exception as e:
                    log.error("Read error %s: %s", rel_path, e)
                    out.write(f"[Ошибка чтения файла: {e}]\n".encode("utf-8", "replace"))

                out.write(b"\n\n")

        if self._progress:
            self._progress(100)

        log.info("Merge finished: %d files written", total)
        return total, walk_errors
