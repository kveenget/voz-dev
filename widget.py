import os
import sys
import tempfile
import threading
import time

import webview

_DEPRECATED_WK_KEYS = (
    "self.webview.setValue_forKey_(True, 'drawsTransparentBackground')",
    "self.webview.setValue_forKey_(False, 'drawsBackground')",
)
_WK_TRANSPARENCY_COMMENT = (
    "            # No usar KVC drawsTransparentBackground/drawsBackground: trace trap en macOS 13+"
)


def _patch_pywebview_cocoa_transparency():
    """Evita KVC en WKWebView que provoca trace trap en macOS recientes."""
    try:
        from webview.platforms import cocoa
    except ImportError:
        return
    path = getattr(cocoa, "__file__", None)
    if not path:
        return
    try:
        with open(path, encoding="utf-8") as f:
            src = f.read()
    except OSError:
        return
    changed = False
    for deprecated in _DEPRECATED_WK_KEYS:
        if deprecated in src:
            src = src.replace(deprecated, _WK_TRANSPARENCY_COMMENT)
            changed = True
    if not changed:
        return
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(src)
        import importlib

        importlib.reload(cocoa)
    except OSError:
        pass


_patch_pywebview_cocoa_transparency()

STATE_FILE   = os.path.join(tempfile.gettempdir(), "vozdev_state.txt")
SHOW_FILE    = os.path.join(tempfile.gettempdir(), "vozdev_show.txt")
VOICE_FILE   = os.path.join(tempfile.gettempdir(), "vozdev_voice.txt")
STOP_FILE    = os.path.join(tempfile.gettempdir(), "vozdev_stop.txt")
PID_FILE     = os.path.join(tempfile.gettempdir(), "vozdev_widget.pid")
CMD_FILE     = os.path.join(tempfile.gettempdir(), "vozdev_cmd.txt")
PROJECT_FILE = os.path.join(tempfile.gettempdir(), "vozdev_project.txt")
ACTIVATE_FILE = os.path.join(tempfile.gettempdir(), "vozdev_activate.txt")

W, H = 368, 64


def _acquire_single_instance():
    if os.path.isfile(PID_FILE):
        try:
            old = int(open(PID_FILE, encoding="utf-8").read().strip())
            os.kill(old, 0)
            print("[voz widget] Ya hay un widget en ejecución.")
            sys.exit(0)
        except (OSError, ValueError):
            pass
    with open(PID_FILE, "w", encoding="utf-8") as f:
        f.write(str(os.getpid()))


def _release_single_instance():
    try:
        os.remove(PID_FILE)
    except OSError:
        pass

_HTML_PATH = os.path.join(os.path.dirname(__file__), "widget-electron", "index.html")
with open(_HTML_PATH, encoding="utf-8") as _f:
    HTML = _f.read()


def set_state(state):
    try:
        with open(STATE_FILE, "w") as f:
            f.write(state)
    except OSError:
        pass


class Api:
    _window = None  # inyectado en run_widget() después de crear la ventana

    def get_state(self):
        try:
            with open(STATE_FILE) as f:
                return f.read().strip()
        except OSError:
            return "idle"

    def activate(self):
        try:
            activate_path = os.path.join(tempfile.gettempdir(), "vozdev_activate.txt")
            with open(activate_path, "w", encoding="utf-8") as f:
                f.write(str(time.time()))
        except OSError:
            pass
        return "ok"

    def get_voice(self):
        try:
            with open(VOICE_FILE, encoding="utf-8") as f:
                return f.read().strip()
        except OSError:
            return ""

    def set_voice(self, voice: str):
        try:
            with open(VOICE_FILE, "w", encoding="utf-8") as f:
                f.write(voice.strip())
        except OSError:
            pass
        return "ok"

    def stop_session(self):
        try:
            with open(STOP_FILE, "w", encoding="utf-8") as f:
                f.write(str(time.time()))
        except OSError:
            pass
        return "ok"

    def move_by(self, dx: int, dy: int):
        """Mueve la ventana dx/dy píxeles (drag manual desde JS)."""
        if not self._window:
            return "ok"
        try:
            native = getattr(self._window, "native", None)
            if native is not None:
                frame = native.frame()
                native.setFrameOrigin_((frame.origin.x + int(dx), frame.origin.y - int(dy)))
        except Exception:
            pass
        return "ok"

    def expand(self, height: int):
        """Expande la ventana hacia abajo para mostrar el popup del menú."""
        if self._window:
            try:
                self._window.resize(W, int(height))
            except Exception:
                pass
        return "ok"

    def collapse(self):
        """Colapsa la ventana de vuelta al tamaño normal del pill."""
        if self._window:
            try:
                self._window.resize(W, H)
            except Exception:
                pass
        return "ok"

    def send_command(self, cmd: str):
        """Inyecta un comando de texto en la sesión activa y activa si no hay sesión."""
        try:
            with open(CMD_FILE, "w", encoding="utf-8") as f:
                f.write(cmd.strip())
        except OSError:
            pass
        try:
            with open(ACTIVATE_FILE, "w", encoding="utf-8") as f:
                f.write(str(time.time()))
        except OSError:
            pass
        return "ok"

    def get_project(self):
        """Devuelve el proyecto activo (archivo temporal o variable de entorno)."""
        try:
            p = open(PROJECT_FILE, encoding="utf-8").read().strip()
            if p:
                return p
        except OSError:
            pass
        return os.path.expanduser(os.getenv("VOZ_PROJECT_ROOT", "~"))

    def pick_project(self):
        """Abre el Finder nativo para seleccionar carpeta de proyecto."""
        if not self._window:
            return ""
        try:
            result = self._window.create_file_dialog(
                webview.FOLDER_DIALOG,
                allow_multiple=False,
            )
            if result:
                path = result[0]
                with open(PROJECT_FILE, "w", encoding="utf-8") as f:
                    f.write(path)
                return path
        except Exception:
            pass
        return ""


def _notch_position():
    """Centrado arriba (zona notch). pywebview: y=0 es el borde superior."""
    if sys.platform != "darwin":
        return 100, 8

    from AppKit import NSScreen

    screen = NSScreen.mainScreen()
    frame = screen.frame()
    sw = int(frame.size.width)
    x = int(frame.origin.x + (sw - W) / 2)
    y = 8
    return x, y


def _poll_show_hide(window, x, y, stop_event):
    """Lee archivos de estado y empuja cambios directamente al JS via evaluate_js."""
    last_show = None
    last_state = None
    while not stop_event.is_set():
        # --- visibilidad ---
        try:
            with open(SHOW_FILE, encoding="utf-8") as f:
                cmd = f.read().strip()
        except OSError:
            cmd = ""

        if cmd != last_show:
            last_show = cmd
            if cmd == "show":
                try:
                    window.move(x, y)
                    window.show()
                except Exception:
                    pass
                try:
                    with open(SHOW_FILE, "w", encoding="utf-8") as f:
                        f.write("shown")
                except OSError:
                    pass
            elif cmd in ("hide", "hidden"):
                try:
                    window.hide()
                except Exception:
                    pass
                try:
                    with open(SHOW_FILE, "w", encoding="utf-8") as f:
                        f.write("hidden")
                except OSError:
                    pass

        # --- estado: Python lee el archivo y empuja al JS ---
        try:
            with open(STATE_FILE, encoding="utf-8") as f:
                state = f.read().strip()
        except OSError:
            state = ""

        if state and state != last_state:
            last_state = state
            try:
                window.evaluate_js(f"setState('{state}')")
            except Exception:
                pass

        time.sleep(0.08)


def _start_poll(window, x, y, stop_poll, poll_started):
    if poll_started.is_set():
        return
    poll_started.set()
    threading.Thread(
        target=_poll_show_hide,
        args=(window, x, y, stop_poll),
        daemon=True,
    ).start()


def _keep_notch_position(window, x, y):
    def apply():
        try:
            window.move(x, y)
        except Exception:
            pass

    apply()
    threading.Timer(0.15, apply).start()


def run_widget():
    _acquire_single_instance()
    set_state("idle")
    try:
        with open(SHOW_FILE, "w", encoding="utf-8") as f:
            f.write("show")
    except OSError:
        pass

    x, y = _notch_position()
    stop_poll = threading.Event()
    poll_started = threading.Event()

    api = Api()
    window = webview.create_window(
        title="",
        html=HTML,
        width=W,
        height=H,
        x=x,
        y=y,
        resizable=True,
        frameless=True,
        transparent=True,
        background_color="#000000",
        shadow=False,
        on_top=True,
        easy_drag=False,
        js_api=api,
    )
    api._window = window

    def on_ready():
        _keep_notch_position(window, x, y)
        _start_poll(window, x, y, stop_poll, poll_started)
        try:
            native = getattr(window, "native", None)
            if native is not None:
                native.setHasShadow_(False)
                native.setOpaque_(False)
                try:
                    from AppKit import NSColor

                    native.setBackgroundColor_(NSColor.clearColor())
                except Exception:
                    pass
            window.move(x, y)
            window.show()
        except Exception:
            pass

    window.events.shown += on_ready
    window.events.loaded += on_ready

    try:
        webview.start(debug=False)
    finally:
        stop_poll.set()
        _release_single_instance()


if __name__ == "__main__":
    run_widget()
