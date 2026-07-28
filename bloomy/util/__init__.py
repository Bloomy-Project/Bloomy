import asyncio
import logging
import os.path
import sys
import traceback
from pathlib import Path
from typing import Callable

__all__ = [
    "getbloomy",
    "traceback_format_simple",
    "with_error",
]
CURRENT_DIR = str(Path().resolve())


def getbloomy():
    from ..bloomy import Bloomy
    try:
        return Bloomy._inst
    except AttributeError:
        raise RuntimeError("Not instanced") from None


def traceback_format_simple(exc: BaseException):
    lines = ["Traceback (most recent call last):"]
    for filename, lineno, name, line in traceback.extract_tb(exc.__traceback__):
        if filename.startswith(CURRENT_DIR):
            filename = "." + os.path.sep + filename[len(CURRENT_DIR) + 1:]
        elif filename.startswith(sys.exec_prefix):
            filename = "(PY)" + os.path.sep + filename[len(sys.exec_prefix) + 1:]

        lines.append(f'  File "{filename}", line {lineno}, in {name}')
        if line:
            lines.append(f"    {line}")

    lines.append(f"{type(exc).__name__}: {exc}")
    return "\n".join(lines)


def with_error(
    log: logging.Logger,
    msg: str | Callable[[BaseException], str],
    *,
    level: int = logging.ERROR,
    exc_info=True,
):
    def callback(fn: asyncio.Future):
        if exc := fn.exception():
            if callable(msg):
                msg(exc)
            log.log(level, msg, exc_info=exc if exc_info else None)

    return callback
