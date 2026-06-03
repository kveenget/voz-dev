import asyncio
import os
import sys
import time

import pyaudio

from agent_tools.registry import list_tools

from voz import config as cfg
from voz import hotkey as hotkey_mod
from voz.exceptions import ShutdownAgent
from voz.instance import acquire_main_instance, other_instance_pid, release_main_instance
from voz.realtime import conectar_realtime
from voz.tools_runtime import bootstrap
from voz.wake import escuchar_wake_word
from voz.widget_ctl import (
    begin_activation,
    ensure_widget_running,
    set_widget_state,
    set_widget_visible,
    stop_widget,
)

_BACKGROUND = os.getenv("VOZ_BACKGROUND", "").lower() in ("1", "true", "yes")
_LOG_PATH = os.path.join(os.environ.get("TMPDIR", "/tmp"), "vozdev.log")


def _log(msg: str) -> None:
    if _BACKGROUND:
        try:
            with open(_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(msg + "\n")
        except OSError:
            pass
    print(msg, flush=True)


def _notify_mac(title: str, text: str) -> None:
    if sys.platform != "darwin":
        return
    safe = text.replace('"', "'")
    os.system(
        f"osascript -e 'display notification \"{safe}\" with title \"{title}\"' 2>/dev/null"
    )


def _run_hotkey_loop() -> None:
    """Un atajo = widget + agente + saludo. El proceso vive en segundo plano."""
    ensure_widget_running()
    set_widget_visible(True)
    set_widget_state("idle")

    if not hotkey_mod.hotkey_available():
        _log("⚠️  Falta pynput: venv/bin/pip install pynput")
        raise SystemExit(1)

    hotkey_mod.start_hotkey_listener(cfg.HOTKEY_KEYS)
    _log(f"🎙️  Mike listo")
    _log(f"   ⌥A = {cfg.HOTKEY_KEYS}  |  ⌘⇧U = alternativo  |  🎙️ menú  |  clic Mike")
    _notify_mac("Voz-dev", "🎙️ menú o ⌘⇧U para activar")

    try:
        while True:
            set_widget_state("idle")
            hotkey_mod.esperar_hotkey()
            _log("✅ Conectando…")
            try:
                asyncio.run(
                    conectar_realtime(saludo_inicial=cfg.GREET_ON_ACTIVATE)
                )
            except ShutdownAgent:
                _log("👋 Cerrado.")
                stop_widget()
                break
            except Exception as e:
                _log(f"Sesión terminada: {e}")
            set_widget_state("idle")
            time.sleep(0.2)
    finally:
        hotkey_mod.stop_hotkey_listener()


def _run_always_or_wake(mode: str) -> None:
    ensure_widget_running()
    set_widget_visible(True)

    if mode == "hotkey":
        hotkey_mod.start_hotkey_listener(cfg.HOTKEY_KEYS)

    try:
        while True:
            saludo = False
            if mode == "wake":
                escuchar_wake_word()
                begin_activation()
                saludo = True
            elif mode == "hotkey":
                set_widget_state("idle")
                _log(f"Esperando ⌥A o clic en Mike…")
                hotkey_mod.esperar_hotkey()
                saludo = True

            asyncio.run(conectar_realtime(saludo_inicial=saludo))
    except ShutdownAgent:
        stop_widget()
    except KeyboardInterrupt:
        _log("👋 Hasta luego!")
        stop_widget()
    finally:
        if mode == "hotkey":
            hotkey_mod.stop_hotkey_listener()


def _run_now() -> None:
    """Sesión de voz directa: conecta inmediatamente sin hotkey."""
    # El tercer argumento (si existe y es directorio) es el proyecto activo
    args = sys.argv[1:]
    if "--now" in args:
        idx = args.index("--now")
        if idx + 1 < len(args):
            candidate = os.path.realpath(os.path.expanduser(args[idx + 1]))
            if os.path.isdir(candidate):
                cfg.PROJECT_ROOT = candidate

    print("=" * 50)
    print("🎙️  VOZ-DEV — Sesión directa (--now)")
    print("=" * 50)
    print(f"📁 Proyecto: {cfg.PROJECT_ROOT}")
    print()
    bootstrap()
    print(f"🔧 Tools: {len(list_tools())}")
    print()
    ensure_widget_running()
    set_widget_visible(True)
    set_widget_state("idle")
    try:
        asyncio.run(conectar_realtime(saludo_inicial=cfg.GREET_ON_ACTIVATE))
    except ShutdownAgent:
        print("👋 Sesión terminada.")
        stop_widget()
    except KeyboardInterrupt:
        print("\n👋 Hasta luego!")
    finally:
        # Solo llegar a idle; el widget se mantiene vivo para la próxima sesión
        set_widget_state("idle")
        set_widget_visible(True)


def run() -> None:
    if "--now" in sys.argv:
        _run_now()
        return

    if not acquire_main_instance():
        pid = other_instance_pid()
        _log(f"ℹ️  voz-dev ya está activo (PID {pid}). Pulsa ⌥A.")
        if not _BACKGROUND:
            _log("   Logs: ./dev.sh logs")
        raise SystemExit(0)

    try:
        if not _BACKGROUND:
            print("=" * 50)
            print("🖥️  VOZ-DEV — Compañero de codificación por voz")
            print("=" * 50)
            print(f"📁 Proyecto: {cfg.PROJECT_ROOT}")
            print()
            print("  Mac (recomendado, una sola vez):")
            print("    ./dev.sh install")
            print("  Después: ⌥A en cualquier app — sin abrir terminal.")
            print()

        bootstrap()

        if not _BACKGROUND:
            print(f"🔧 Tools: {len(list_tools())}")
            if cfg.LIST_MICS:
                pa = pyaudio.PyAudio()
                print("\nMicrófonos:")
                for i in range(pa.get_device_count()):
                    info = pa.get_device_info_by_index(i)
                    if info["maxInputChannels"] > 0:
                        print(f"  [{i}] {info['name']}")
                pa.terminate()
                print()

        mode = cfg.activation_mode()

        if mode == "hotkey":
            if sys.platform == "darwin":
                from voz.menubar import run_with_menubar

                run_with_menubar(_run_hotkey_loop)
            else:
                _run_hotkey_loop()
            return

        if not _BACKGROUND:
            print(f"Modo: {mode}  |  Voz: {cfg.VOZ_VOICE}  |  Ctrl+C salir\n")
        _run_always_or_wake(mode)
    finally:
        release_main_instance()
