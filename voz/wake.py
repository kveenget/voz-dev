import threading
import time

from voz import config as cfg
from voz.widget_ctl import set_widget_state, set_widget_visible


class WakeWordEngine:
    """Detecta 'Hey Mike' con Porcupine en un hilo separado.

    Soporta reconexión automática si el mic se desconecta.
    """

    def __init__(
        self,
        access_key: str,
        keyword_path: str,
        sensitivity: float = 0.5,
        on_detect=None,
    ):
        self._access_key = access_key
        self._keyword_path = keyword_path
        self._sensitivity = max(0.0, min(1.0, sensitivity))
        self._on_detect = on_detect
        self._thread: threading.Thread | None = None
        self._running = False
        self._porcupine = None
        self._recorder = None
        self._detected = threading.Event()

    # ── Ciclo de vida ────────────────────────────────────────────────────────

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._detected.clear()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="wake-word"
        )
        self._thread.start()
        print("😴 Esperando 'Hey Mike'...")
        set_widget_state("idle")

    def stop(self) -> None:
        self._running = False
        self._detected.set()  # desbloquea wait_for_detection si está esperando
        self._cleanup()

    def wait_for_detection(self) -> None:
        """Bloquea hasta que se detecte el wake word o se llame stop()."""
        self._detected.wait()
        self._detected.clear()

    # ── Hilo de detección ────────────────────────────────────────────────────

    def _run(self) -> None:
        import pvporcupine
        import pvrecorder

        while self._running:
            try:
                self._porcupine = pvporcupine.create(
                    access_key=self._access_key,
                    keyword_paths=[self._keyword_path],
                    sensitivities=[self._sensitivity],
                )
                self._recorder = pvrecorder.PvRecorder(
                    frame_length=self._porcupine.frame_length
                )
                self._recorder.start()

                while self._running:
                    pcm = self._recorder.read()
                    result = self._porcupine.process(pcm)
                    if result >= 0:
                        print("\n🎙️  Hey Mike detectado!")
                        if self._on_detect:
                            self._on_detect()
                        self._detected.set()

            except Exception as e:
                if self._running:
                    print(f"⚠️  WakeWordEngine error: {e} — reintentando en 3s")
                    time.sleep(3)
            finally:
                self._cleanup()

    def _cleanup(self) -> None:
        if self._recorder:
            try:
                self._recorder.stop()
            except Exception:
                pass
        if self._porcupine:
            try:
                self._porcupine.delete()
            except Exception:
                pass
        self._recorder = None
        self._porcupine = None


# ── Función pública compatible con app.py ───────────────────────────────────

def escuchar_wake_word() -> None:
    """Bloquea hasta detectar 'Hey Mike' con Porcupine y hace visible el widget."""
    if not cfg.PICOVOICE_ACCESS_KEY:
        raise RuntimeError(
            "Falta PICOVOICE_ACCESS_KEY en .env — regístrate en console.picovoice.ai"
        )

    import os
    if not os.path.isfile(cfg.WAKE_KEYWORD_PATH):
        raise FileNotFoundError(
            f"Keyword no encontrada: {cfg.WAKE_KEYWORD_PATH}\n"
            "Genera 'hey-mike_mac.ppn' en console.picovoice.ai y ponlo en models/"
        )

    engine = WakeWordEngine(
        access_key=cfg.PICOVOICE_ACCESS_KEY,
        keyword_path=cfg.WAKE_KEYWORD_PATH,
        sensitivity=cfg.WAKE_SENSITIVITY,
    )
    engine.start()
    engine.wait_for_detection()
    engine.stop()
    set_widget_visible(True)
