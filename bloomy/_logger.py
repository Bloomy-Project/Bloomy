import datetime
import gzip
import logging.handlers
import os
from pathlib import Path

import colorlog

from bloomy.util.file import creation_file_date

__all__ = [
    "BloomyStreamHandler",
    "BloomyFileHandler",
    "DaysRotatingFileHandler",
    "PackageNameInserter",
]


class BloomyStreamHandler(logging.StreamHandler):
    def __init__(self, spacing_size: int = 30):
        super().__init__()
        prefix = "{log_color}[\033[90m{asctime}{log_color}] " \
                 "\033[90m{lineno:4} {log_color}| " \
                 "\033[90m{logname} {log_color}"

        self.addFilter(PackageNameInserter(spacing_size))
        # noinspection PyTypeChecker
        self.setFormatter(colorlog.LevelFormatter(
            fmt=dict(DEBUG=f"{prefix}| D: {{message}}",
                     INFO=f"{prefix}| I: {{message}}",
                     WARNING=f"{prefix}| W: {{message}}",
                     ERROR=f"{prefix}| E: {{message}}",
                     CRITICAL=f"{prefix}| E: {{message}}"),
            log_colors=dict(DEBUG="purple", INFO="white", WARNING="yellow", ERROR="red", CRITICAL="red"),
            datefmt="%H:%M:%S", style="{", reset=True))


class DaysRotatingFileHandler(logging.handlers.TimedRotatingFileHandler):
    HANDLERS = []

    def __init__(self, latest_name):
        self.rotate_latest(Path(latest_name))
        logging.handlers.TimedRotatingFileHandler.__init__(
            self, latest_name, when="midnight", encoding="utf-8", delay=True)
        DaysRotatingFileHandler.HANDLERS.append(self)

    def rotate(self, source, dest):
        creation = creation_file_date(source)
        handlers = self.close_all()
        os.rename(source, dest)

        parent = Path(dest).parent
        with open(dest, "rb") as f_in:
            with gzip.open(parent / "{0.year:04}-{0.month:02}-{0.day:02}.log.gz".format(creation), "wb") as f_out:
                f_out.writelines(f_in)

        os.remove(dest)
        self.open_all(handlers)

    @staticmethod
    def rotate_latest(path: Path):
        if not path.is_file():
            return
        creation = creation_file_date(path)

        if creation.date() >= datetime.date.today():
            return

        parent = Path(path.parent)

        with path.open("rb") as f_in:
            with gzip.open(parent / "{0.year:04}-{0.month:02}-{0.day:02}.log.gz".format(creation), "wb") as f_out:
                f_out.writelines(f_in)

        os.remove(str(path))

    def close_all(self):
        filename = self.baseFilename
        handlers = []

        for handler in DaysRotatingFileHandler.HANDLERS:
            if isinstance(handler, logging.FileHandler):
                if filename == handler.baseFilename:
                    handler.close()
                    handlers.append(handler)

        return handlers

    # noinspection PyMethodMayBeStatic,PyProtectedMember
    def open_all(self, handlers: list[logging.FileHandler]):
        for handler in handlers:
            handler._open()


class BloomyFileHandler(DaysRotatingFileHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setFormatter(logging.Formatter(
            fmt="[{asctime}/{levelname}/{name}/{lineno}] {message}",
            datefmt="%Y-%m-%d/%H:%M:%S", style="{"))


class PackageNameInserter(logging.Filter):
    CACHES = {}

    def __init__(self, size=30):
        logging.Filter.__init__(self)
        self.size = size

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            name = self.CACHES[record.name]
        except KeyError:
            name = record.name
            parts = name.split(".")
            idx = 1
            while self.size < len(".".join(parts)) and idx < len(parts):
                parts[idx] = parts[idx][:2]
                idx += 1

            name = ".".join(parts)
            name += " " * (self.size - len(name))
            self.CACHES[record.name] = name

        record.logname = name
        return True
