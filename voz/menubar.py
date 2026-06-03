"""Icono 🎙️ en la barra de menú — activar sin atajo (siempre funciona en Mac)."""

from __future__ import annotations

import sys
import threading


def run_with_menubar(hotkey_loop_fn) -> None:
    if sys.platform != "darwin":
        hotkey_loop_fn()
        return

    try:
        import rumps
    except ImportError:
        print("ℹ️  Sin rumps: pip install rumps  (menú 🎙️ opcional)")
        hotkey_loop_fn()
        return

    from voz.hotkey import trigger_activate

    class MikeApp(rumps.App):
        def __init__(self):
            super().__init__("Mike", title="🎙️", quit_button=None)
            self.menu = ["Activar ahora", None, "Salir"]

        @rumps.clicked("Activar ahora")
        def activar(self, _):
            trigger_activate("menú 🎙️")

        @rumps.clicked("Salir")
        def salir(self, _):
            import os

            os._exit(0)

    threading.Thread(target=hotkey_loop_fn, daemon=True).start()
    print("   Menú 🎙️ arriba a la derecha → «Activar ahora» (no requiere Accesibilidad)")
    MikeApp().run()
