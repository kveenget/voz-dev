"""Una sola instancia del agente en segundo plano."""

import os
import sys
import tempfile

MAIN_PID_FILE = os.path.join(tempfile.gettempdir(), "vozdev_main.pid")


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def acquire_main_instance() -> bool:
    """True si somos la instancia principal; False si ya hay otra."""
    pid = os.getpid()
    if os.path.isfile(MAIN_PID_FILE):
        try:
            old = int(open(MAIN_PID_FILE, encoding="utf-8").read().strip())
            if old != pid and _pid_alive(old):
                return False
        except (OSError, ValueError):
            pass
    with open(MAIN_PID_FILE, "w", encoding="utf-8") as f:
        f.write(str(pid))
    return True


def release_main_instance() -> None:
    try:
        if os.path.isfile(MAIN_PID_FILE):
            if int(open(MAIN_PID_FILE, encoding="utf-8").read().strip()) == os.getpid():
                os.remove(MAIN_PID_FILE)
    except (OSError, ValueError):
        pass


def other_instance_pid() -> int | None:
    if not os.path.isfile(MAIN_PID_FILE):
        return None
    try:
        pid = int(open(MAIN_PID_FILE, encoding="utf-8").read().strip())
        return pid if _pid_alive(pid) else None
    except (OSError, ValueError):
        return None
