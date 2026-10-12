"""One renderer per session, and how to tell whether one is up.

Both programs need this answer. The renderer takes the lock so that a second
copy cannot start and draw every key press twice; the settings window asks
whether the lock is held, because a preview request that nothing is listening
for is indistinguishable from a broken button.

The lock itself is what answers the question: a leftover file proves nothing,
but only a live process can be holding it.
"""
import fcntl
import os


def lock_path():
    """Where the per-session lock lives.

    XDG_RUNTIME_DIR is cleared at logout, which is the right lifetime for a
    process that lives and dies with the session.
    """
    runtime = os.environ.get('XDG_RUNTIME_DIR') or '/tmp'
    return os.path.join(runtime, 'mifs-osd-kde.%d.lock' % os.getuid())


def acquire():
    """Take the lock.

    Returns a handle on success, or None if another renderer already holds it.
    The handle has to stay referenced: closing it, or letting it be collected,
    drops the lock -- which is exactly how a crash releases it.
    """
    try:
        handle = open(lock_path(), 'w')
    except OSError:
        # No runtime directory to write to. Refusing to start would be worse
        # than running without the guard.
        return None
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle


def is_running():
    """True when a renderer holds the lock.

    Finding out means trying to take the lock and letting go again. Opening
    the file is not enough and never was: it survives the process that made it.
    """
    try:
        handle = open(lock_path(), 'w')
    except OSError:
        return False
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return True
    handle.close()
    return False
