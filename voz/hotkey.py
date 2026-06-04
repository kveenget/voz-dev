"""Atajo global + clic widget + menú barra (macOS)."""

from __future__ import annotations

import os
import sys
import threading
import time

from voz.widget_ctl import ACTIVATE_FILE

_pressed = threading.Event()
_listeners: list = []
_poll_stop = threading.Event()
_poll_thread: threading.Thread | None = None
_using_pynput = False
_last_trigger = 0.0
_DEBOUNCE_S = 0.6

_KEY_VKS: set[int] = {0, 97}


def _parse_spec(spec: str) -> tuple[set[str], str]:
    parts = [p.strip().lower() for p in spec.replace(" ", "").split("+") if p.strip()]
    mod_names = {"cmd", "command", "super", "shift", "ctrl", "control", "alt", "option"}
    mods: set[str] = set()
    key = None
    for part in parts:
        if part in mod_names:
            if part in ("command", "super"):
                mods.add("cmd")
            elif part in ("control",):
                mods.add("ctrl")
            elif part == "option":
                mods.add("alt")
            else:
                mods.add(part)
        else:
            key = part
    if not key:
        raise ValueError(f"Atajo inválido: {spec}")
    return mods, key


def _accessibility_trusted() -> bool | None:
    try:
        import ctypes

        lib = ctypes.CDLL(
            "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
        )
        lib.AXIsProcessTrusted.restype = ctypes.c_bool
        return bool(lib.AXIsProcessTrusted())
    except Exception:
        return None


def prompt_accessibility() -> None:
    if sys.platform != "darwin":
        return
    print("\n⚠️  Para ⌥A en TODO el Mac, activa Accesibilidad:")
    print(f"   1) {sys.executable}")
    print("   2) O «Python» en la lista")
    print("   3) O «Cursor» si corres desde ahí")
    print("   Sin eso: usa 🎙️ en la barra de menú o clic en Mike\n")
    os.system(
        'open "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"'
    )


def trigger_activate(source: str = "hotkey") -> None:
    global _last_trigger
    now = time.time()
    if now - _last_trigger < _DEBOUNCE_S:
        return
    _last_trigger = now
    print(f"\n⌨️  Activación ({source})…", flush=True)
    try:
        from voz.widget_ctl import begin_activation

        begin_activation()
    except Exception:
        pass
    _pressed.set()


_trigger = trigger_activate  # alias interno


def _poll_activate_file() -> None:
    last_mtime = 0.0
    while not _poll_stop.is_set():
        try:
            mtime = os.path.getmtime(ACTIVATE_FILE)
            if mtime > last_mtime:
                last_mtime = mtime
                trigger_activate("clic en Mike")
        except (FileNotFoundError, OSError):
            pass
        time.sleep(0.1)


def _start_activate_poller() -> None:
    global _poll_thread
    _poll_stop.clear()
    if _poll_thread and _poll_thread.is_alive():
        return
    _poll_thread = threading.Thread(target=_poll_activate_file, daemon=True)
    _poll_thread.start()


def _identify_key(key, key_char: str) -> str | None:
    from pynput.keyboard import Key

    if key in (Key.alt, Key.alt_l, Key.alt_r):
        return "alt"
    if key in (Key.cmd, Key.cmd_l, Key.cmd_r):
        return "cmd"
    if key in (Key.ctrl, Key.ctrl_l, Key.ctrl_r):
        return "ctrl"
    if key in (Key.shift, Key.shift_l, Key.shift_r):
        return "shift"
    if hasattr(key, "char") and key.char:
        return key.char.lower()
    if hasattr(key, "vk") and key.vk is not None and key.vk in _KEY_VKS:
        return key_char
    return None


def _start_pynput_listener(spec: str) -> None:
    global _listeners, _using_pynput
    from pynput.keyboard import Listener

    required_mods, key_char = _parse_spec(spec)
    active: set[str] = set()

    def on_press(key):
        kid = _identify_key(key, key_char)
        if not kid:
            return
        if kid in ("alt", "cmd", "ctrl", "shift"):
            active.add(kid)
            return
        if kid == key_char and required_mods <= active:
            trigger_activate(f"teclado {spec}")

    def on_release(key):
        kid = _identify_key(key, key_char)
        if kid in ("alt", "cmd", "ctrl", "shift"):
            active.discard(kid)

    listener = Listener(on_press=on_press, on_release=on_release)
    listener.start()
    _listeners.append(listener)
    _using_pynput = True


def _start_keyboard_lib(spec: str) -> bool:
    """Librería keyboard (suele ir bien en Apple Silicon)."""
    try:
        import keyboard
    except ImportError:
        return False
    parts = spec.replace(" ", "").lower().split("+")
    mapped = []
    for p in parts:
        if p in ("option", "alt"):
            mapped.append("alt")
        elif p == "command":
            mapped.append("cmd")
        else:
            mapped.append(p)
    combo = "+".join(mapped)
    try:
        keyboard.add_hotkey(combo, lambda: trigger_activate("keyboard"))
        return True
    except Exception:
        return False


def _start_cgevent_listener(spec: str) -> bool:
    """CGEvent tap via Quartz — más fiable que pynput en macOS 14+.

    Usa listen-only mode: no requiere Accessibility para atajos con modificadores.
    """
    try:
        from Quartz import (
            CGEventTapCreate,
            CGEventGetFlags,
            CGEventGetIntegerValueField,
            kCGSessionEventTap,
            kCGHeadInsertEventTap,
            kCGEventTapOptionListenOnly,
            kCGEventKeyDown,
            CFMachPortCreateRunLoopSource,
            CFRunLoopAddSource,
            CFRunLoopGetCurrent,
            CFRunLoopRun,
            kCFRunLoopDefaultMode,
            CGEventMaskBit,
        )
    except ImportError:
        return False

    try:
        required_mods, key_char = _parse_spec(spec)
    except ValueError:
        return False

    _KEY_CODES: dict[str, int] = {
        "a": 0, "b": 11, "c": 8, "d": 2, "e": 14, "f": 3,
        "g": 5, "h": 4, "i": 34, "j": 38, "k": 40, "l": 37,
        "m": 46, "n": 45, "o": 31, "p": 35, "q": 12, "r": 15,
        "s": 1, "t": 17, "u": 32, "v": 9, "w": 13, "x": 7,
        "y": 16, "z": 6, "space": 49,
    }
    target_vk = _KEY_CODES.get(key_char)
    if target_vk is None:
        return False

    kCGEventFlagMaskAlternate = 0x080000
    kCGEventFlagMaskShift     = 0x020000
    kCGEventFlagMaskControl   = 0x040000
    kCGEventFlagMaskCommand   = 0x100000
    kCGKeyboardEventKeycode   = 9

    mod_mask = 0
    if "alt"   in required_mods: mod_mask |= kCGEventFlagMaskAlternate
    if "shift" in required_mods: mod_mask |= kCGEventFlagMaskShift
    if "ctrl"  in required_mods: mod_mask |= kCGEventFlagMaskControl
    if "cmd"   in required_mods: mod_mask |= kCGEventFlagMaskCommand

    def _callback(proxy, event_type, event, refcon):
        try:
            flags = CGEventGetFlags(event)
            vk    = CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode)
            if int(vk) == target_vk and (int(flags) & mod_mask) == mod_mask:
                trigger_activate(f"cgevent {spec}")
        except Exception:
            pass
        return event

    event_mask = CGEventMaskBit(kCGEventKeyDown)
    tap = CGEventTapCreate(
        kCGSessionEventTap,
        kCGHeadInsertEventTap,
        kCGEventTapOptionListenOnly,
        event_mask,
        _callback,
        None,
    )
    if not tap:
        return False

    source = CFMachPortCreateRunLoopSource(None, tap, 0)

    def _run_loop():
        CFRunLoopAddSource(CFRunLoopGetCurrent(), source, kCFRunLoopDefaultMode)
        CFRunLoopRun()

    t = threading.Thread(target=_run_loop, daemon=True, name="cgevent-tap")
    t.start()
    return True


def start_hotkey_listener(spec: str, extra_spec: str | None = None) -> str:
    global _using_pynput
    _using_pynput = False
    _listeners.clear()
    _start_activate_poller()

    trusted = _accessibility_trusted()
    lines = [f"   Atajos: {spec}"]

    # Intenta CGEvent tap primero (más fiable en macOS 14+, no necesita Accessibility)
    if sys.platform == "darwin" and _start_cgevent_listener(spec):
        lines.append(f"   CGEvent tap: {spec}")

    if _pynput_available():
        try:
            _start_pynput_listener(spec)
            lines.append(f"   Listener pynput: {spec}")
        except Exception as e:
            print(f"⚠️  pynput listener: {e}")

    alt = extra_spec or os.getenv("VOZ_HOTKEY_ALT", "cmd+shift+u")
    if alt and alt != spec:
        try:
            _start_pynput_listener(alt)
            lines.append(f"   Listener pynput: {alt}")
        except Exception:
            pass
        _start_keyboard_lib(alt)

    _start_keyboard_lib(spec)

    if trusted is False:
        prompt_accessibility()
        lines.append("   Sin Accesibilidad: usa 🎙️ menú superior o clic Mike")
    else:
        lines.append("   También: icono 🎙️ barra de menú / clic Mike")

    for line in lines:
        print(line)
    return spec


def esperar_hotkey() -> None:
    _pressed.wait()
    _pressed.clear()


def stop_hotkey_listener() -> None:
    global _using_pynput
    _poll_stop.set()
    for listener in _listeners:
        try:
            listener.stop()
        except Exception:
            pass
    _listeners.clear()
    _using_pynput = False
    try:
        import keyboard

        keyboard.unhook_all()
    except Exception:
        pass


def hotkey_available() -> bool:
    return _pynput_available() or sys.platform == "darwin"


def _pynput_available() -> bool:
    try:
        import pynput  # noqa: F401

        return True
    except ImportError:
        return False


def describe_backend() -> str:
    if _using_pynput:
        return "pynput+keyboard"
    return "clic/menú"
