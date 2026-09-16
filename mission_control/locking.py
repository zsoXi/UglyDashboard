"""Persistent advisory locks for local credential transactions.

The lock file is never removed: removing an inode that another process has
opened creates two independent locks. The OS releases the lock on process exit.
"""

import errno
import os
import stat
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl

# Credential transactions are rare. One process-local mutex avoids platform
# differences in advisory locks held by separate handles in the same process.
_THREAD_LOCK = threading.RLock()


@contextmanager
def secret_lock(path: Path, timeout: float = 10.0) -> Iterator[None]:
    """Serialize cooperating readers/writers, with a finite acquisition timeout."""
    deadline = time.monotonic() + timeout
    if not _THREAD_LOCK.acquire(timeout=max(0.0, timeout)):
        raise TimeoutError("Timed out waiting for credential transaction")
    fd = None
    locked = False
    try:
        flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_BINARY", 0)
        flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(str(path), flags, 0o600)
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise OSError("Credential lock must be a regular file")
        while True:
            try:
                if sys.platform == "win32":
                    os.lseek(fd, 0, os.SEEK_SET)
                    # _locking explicitly supports locking a range past EOF.
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                else:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
                break
            except OSError as exc:
                if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                    raise
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("Timed out waiting for credential lock") from exc
                time.sleep(min(0.02, remaining))
        yield
    finally:
        try:
            if locked and fd is not None:
                if sys.platform == "win32":
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            try:
                if fd is not None:
                    os.close(fd)
            finally:
                _THREAD_LOCK.release()
