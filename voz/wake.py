import threading
import time

import numpy as np
import pyaudio

from voz import config as cfg
from voz.widget_ctl import set_widget_state, set_widget_visible

_CHUNK = 1280   # 80ms @ 16 kHz — tamaño que requiere openWakeWord
_RATE  = 16000


class WakeWordEngine:
    """Detecta la wake word con openWakeWord en un hilo separado.

    Sin API key ni registro. Modelos descargados automáticamente en
    el primer uso desde GitHub (requiere internet la primera vez).
    """

    def __init__(self, model: str = "hey_jarvis", threshold: float = 0.5, on_detect=None):
        self._model_name = model
        self._threshold  = max(0.0, min(1.0, threshold))
        self._on_detect  = on_detect
        self._running    = False
        self._thread: threading.Thread | None = None
        self._detected   = threading.Event()

    # ── Ciclo de vida ────────────────────────────────────────────────────────

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._detected.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="wake-word")
        self._thread.start()
        print(f"😴 Esperando '{self._model_name}'...")
        set_widget_state("idle")

    def stop(self) -> None:
        self._running = False
        self._detected.set()

    def wait_for_detection(self) -> None:
        self._detected.wait()
        self._detected.clear()

    # ── Hilo de detección ────────────────────────────────────────────────────

    def _run(self) -> None:
        from openwakeword.model import Model

        while self._running:
            p = None
            stream = None
            try:
                print(f"⏳ Cargando modelo '{self._model_name}' (primera vez descarga ~5MB)...")
                model = Model(wakeword_models=[self._model_name], inference_framework="onnx")
                print(f"✅ Modelo listo — di '{self._model_name}'")

                p = pyaudio.PyAudio()
                stream = p.open(
                    rate=_RATE,
                    channels=1,
                    format=pyaudio.paInt16,
                    input=True,
                    frames_per_buffer=_CHUNK,
                )

                while self._running:
                    audio = stream.read(_CHUNK, exception_on_overflow=False)
                    chunk = np.frombuffer(audio, dtype=np.int16)
                    scores = model.predict(chunk)

                    for name, score in scores.items():
                        if score >= self._threshold:
                            print(f"\n🎙️  Wake word detectado! ({name}: {score:.2f})")
                            if self._on_detect:
                                self._on_detect()
                            self._detected.set()
                            time.sleep(1.0)  # cooldown anti-doble disparo
                            break

            except Exception as e:
                if self._running:
                    print(f"⚠️  WakeWordEngine error: {e} — reintentando en 3s")
                    time.sleep(3)
            finally:
                if stream:
                    try:
                        stream.stop_stream()
                        stream.close()
                    except Exception:
                        pass
                if p:
                    try:
                        p.terminate()
                    except Exception:
                        pass


# ── Función pública compatible con app.py ───────────────────────────────────

def escuchar_wake_word() -> None:
    """Bloquea hasta detectar la wake word y muestra el widget."""
    engine = WakeWordEngine(
        model=cfg.WAKE_KEYWORD,
        threshold=cfg.WAKE_SENSITIVITY,
    )
    engine.start()
    engine.wait_for_detection()
    engine.stop()
    set_widget_visible(True)
