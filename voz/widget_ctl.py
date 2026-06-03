import os
import subprocess
import sys
import tempfile
import time

from voz.config import ROOT_DIR, WIDGET_SCRIPT

STATE_FILE = os.path.join(tempfile.gettempdir(), "vozdev_state.txt")
SHOW_FILE = os.path.join(tempfile.gettempdir(), "vozdev_show.txt")
ACTIVATE_FILE = os.path.join(tempfile.gettempdir(), "vozdev_activate.txt")
WIDGET_PID_FILE = os.path.join(tempfile.gettempdir(), "vozdev_widget.pid")

_widget_state_cache = None


def set_widget_state(s: str) -> None:
    global _widget_state_cache
    if s == _widget_state_cache:
        return
    _widget_state_cache = s
    try:
        with open(STATE_FILE, "w") as f:
            f.write(s)
    except OSError:
        pass


def signal_activate() -> None:
    """Lo llama el widget al hacer clic — despierta el modo hotkey."""
    try:
        with open(ACTIVATE_FILE, "w", encoding="utf-8") as f:
            f.write(str(time.time()))
    except OSError:
        pass


def begin_activation() -> None:
    """Muestra el widget y estado «conectando» en cuanto el usuario activa."""
    if not _widget_pid_alive():
        ensure_widget_running()
    set_widget_visible(True)
    set_widget_state("connecting")


def set_widget_visible(visible: bool) -> None:
    try:
        with open(SHOW_FILE, "w") as f:
            f.write("show" if visible else "hide")
    except OSError:
        pass


def _widget_pid_alive():
    try:
        with open(WIDGET_PID_FILE) as f:
            pid = int(f.read().strip())
        os.kill(pid, 0)
        return pid
    except (OSError, ValueError):
        return None


def ensure_widget_running() -> None:
    global _widget_state_cache
    if _widget_pid_alive():
        # Resetear cache para forzar escritura aunque el estado ya sea "idle"
        _widget_state_cache = None
        set_widget_visible(True)
        set_widget_state("idle")
        return

    if not os.path.isfile(WIDGET_SCRIPT):
        print("⚠️  No se encontró widget.py")
        return

    log_path = os.path.join(tempfile.gettempdir(), "vozdev_widget.log")
    print("🪟 Iniciando widget...")
    with open(log_path, "a", encoding="utf-8") as log:
        subprocess.Popen(
            [sys.executable, WIDGET_SCRIPT],
            cwd=ROOT_DIR,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    # Esperar hasta 10 s — pywebview + AppKit pueden tardar en el primer arranque
    for _ in range(50):
        if _widget_pid_alive():
            break
        time.sleep(0.2)

    set_widget_visible(True)
    set_widget_state("connecting")
    time.sleep(0.5)
    set_widget_state("idle")


def stop_widget() -> None:
    pid = _widget_pid_alive()
    if pid:
        try:
            os.kill(pid, 15)
        except OSError:
            pass
    try:
        os.remove(WIDGET_PID_FILE)
    except OSError:
        pass
