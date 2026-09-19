"""OS-held lock: a second launcher must not create competing Telegram pollers."""
import os
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def single_instance(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open('a+b')
    try:
        handle.seek(0, 2)
        if handle.tell() == 0:
            handle.write(b'0')
            handle.flush()
        handle.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError('A Marina ja esta aberta em outra janela. Use a janela existente.') from exc
        yield
    finally:
        handle.close()  # The OS releases the lock even after a crash.
