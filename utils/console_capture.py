import io
import logging
from collections import deque

MAX_LINES = 2000

_buffer: deque[str] = deque(maxlen=MAX_LINES)


class BufferHandler(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.INFO)
        self.setFormatter(logging.Formatter(
            "[%(asctime)s] [%(levelname)s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S",
        ))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            _buffer.append(self.format(record))
        except Exception:
            pass


def install() -> None:
    root = logging.getLogger()
    if any(isinstance(h, BufferHandler) for h in root.handlers):
        return
    root.addHandler(BufferHandler())


def get_lines(limit: int = MAX_LINES) -> list[str]:
    return list(_buffer)[-limit:]


def get_text(limit: int = MAX_LINES) -> str:
    return "\n".join(get_lines(limit))


def get_file(limit: int = MAX_LINES) -> io.BytesIO:
    text = get_text(limit)
    if not text:
        text = "No console output captured yet."
    buffer = io.BytesIO(text.encode("utf-8"))
    buffer.seek(0)
    return buffer


def clear() -> None:
    _buffer.clear()
