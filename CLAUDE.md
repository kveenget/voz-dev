# voz-dev — Contexto para Claude

Pair programming por voz en macOS. El usuario habla en español con `⌥A`, el agente responde por audio usando **OpenAI gpt-realtime-2** (WebSocket) y ejecuta herramientas (git, edición de archivos, búsqueda web, capturas de pantalla, etc.).

## Cómo correr

```bash
source venv/bin/activate
python main.py          # modo hotkey (⌥A), con menubar
python main.py --now    # sesión directa sin hotkey
./dev.sh now            # equivalente a --now vía script
./dev.sh logs           # logs del servicio en background
```

Requiere `.env` con `OPENAI_API_KEY`. Ver `README.md` para todas las variables.

## Modos de activación (`VOZ_ACTIVATION`)

- `hotkey` (default) — `⌥A` desde cualquier app, vía CGEvent tap (Quartz) + pynput como fallback
- `always` — sesión continua sin hotkey
- `wake` — wake word con openWakeWord (`hey_jarvis`), sin API key

## Arquitectura del pipeline de audio

**Entrada (mic → servidor):**
`stream_in` (PyAudio) → `capturar_y_enviar()` → WebSocket

**Salida (servidor → altavoz):**
WebSocket → `recibir_eventos()` → `_pcm_q` (queue.Queue) → `_audio_out_thread()` (daemon) → `stream_out` (PyAudio)

**Regla crítica**: El audio delta va DIRECTO a `_pcm_q` sin pasar por ninguna asyncio Queue. El scheduler del event loop crea gaps que vacían el buffer de PyAudio → choppy audio. No reintroducir una capa asyncio en el camino del audio.

El hilo `_audio_out_thread` batcha chunks hasta 100ms antes de escribir a PyAudio para evitar underruns.

## Reglas de la sesión (`session.update`)

- gpt-realtime-2 requiere el config completo en cada `session.update` — no acepta updates parciales sin `"type": "realtime"`.
- Para cambiar de voz en tiempo real: enviar session.update con todo el config EXCEPTO `audio.input` (si se re-envía `audio.input`, el servidor resetea el VAD y corta el audio).

## Módulos clave

| Archivo | Responsabilidad |
|---|---|
| `voz/realtime.py` | WebSocket con OpenAI, pipeline de audio, tool calls |
| `voz/audio.py` | Captura mic, ganancia, resample, half-duplex gate |
| `voz/config.py` | Variables de entorno (todo lo configurable vive aquí) |
| `voz/hotkey.py` | CGEvent tap (primario) + pynput (fallback) |
| `voz/wake.py` | openWakeWord engine — `WakeWordEngine` class |
| `voz/app.py` | Lógica de modos (hotkey/wake/always), loop principal |
| `widget-electron/index.html` | UI del widget — Design System en `:root {}` |

## Widget

El widget es una ventana `pywebview` (`widget.py`) que carga `widget-electron/index.html`. Se comunica con `voz/widget_ctl.py` mediante archivos temporales en `$TMPDIR` (`vozdev_*.txt`). Estados: `idle`, `user`, `thinking`, `ai`.

El CSS usa custom properties en `:root {}` — no usar hex hardcodeados.

## Dependencias importantes

```
openai, pyaudio, websockets, pywebview, openwakeword, pyobjc-framework-Quartz, numpy, rumps
```

openWakeWord descarga ~5MB de modelo ONNX en el primer uso (requiere internet).
Quartz se usa solo en macOS para el CGEvent tap del hotkey.

## Convenciones

- Código y comentarios en español (igual que el proyecto)
- Sin type hints exhaustivos — duck typing donde sea obvio
- `cfg.*` para toda configuración — no hardcodear valores
- `set_widget_state()` para cambios de estado del widget desde cualquier hilo
- `loop.call_soon_threadsafe()` para llamar funciones asyncio desde hilos daemon
