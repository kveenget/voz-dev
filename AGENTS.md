# voz-dev - Guia para agentes

Pair programming por voz en macOS. El usuario habla en espanol con `Option+A`, el agente responde por audio usando **OpenAI gpt-realtime-2** via WebSocket y puede ejecutar herramientas como git, edicion de archivos, busqueda web y capturas de pantalla.

## Como correr

```bash
source venv/bin/activate
python main.py          # modo hotkey (Option+A), con menubar
python main.py --now    # sesion directa sin hotkey
./dev.sh now            # equivalente a --now via script
./dev.sh logs           # logs del servicio en background
```

Requiere `.env` con `OPENAI_API_KEY`. Ver `README.md` para el resto de variables.

## Modos de activacion

`VOZ_ACTIVATION` controla el modo principal:

- `hotkey`: modo default, usa `Option+A` desde cualquier app via CGEvent tap de Quartz y `pynput` como fallback.
- `always`: sesion continua sin hotkey.
- `wake`: wake word con openWakeWord (`hey_jarvis`), sin API key.

## Arquitectura de audio

Entrada:

```text
stream_in (PyAudio) -> capturar_y_enviar() -> WebSocket
```

Salida:

```text
WebSocket -> recibir_eventos() -> _pcm_q (queue.Queue) -> _audio_out_thread() -> stream_out (PyAudio)
```

Regla critica: el audio delta debe ir directo a `_pcm_q`, sin pasar por una `asyncio.Queue`. El scheduler del event loop puede crear gaps que vacian el buffer de PyAudio y producen audio entrecortado.

El hilo `_audio_out_thread` agrupa chunks hasta 100 ms antes de escribir a PyAudio para evitar underruns.

## Session update

- `gpt-realtime-2` requiere el config completo en cada `session.update`; no acepta updates parciales sin `"type": "realtime"`.
- Para cambiar la voz en tiempo real, enviar `session.update` con todo el config excepto `audio.input`. Si se reenvia `audio.input`, el servidor resetea el VAD y corta el audio.

## Modulos clave

- `voz/realtime.py`: WebSocket con OpenAI, pipeline de audio y tool calls.
- `voz/audio.py`: captura de microfono, ganancia, resample y half-duplex gate.
- `voz/config.py`: variables de entorno. Toda configuracion debe vivir en `cfg.*`.
- `voz/hotkey.py`: CGEvent tap principal y fallback con `pynput`.
- `voz/wake.py`: motor openWakeWord, clase `WakeWordEngine`.
- `voz/app.py`: logica de modos (`hotkey`, `wake`, `always`) y loop principal.
- `widget.py`: ventana `pywebview` del widget.
- `widget-electron/index.html`: UI del widget y design system en `:root`.
- `voz/widget_ctl.py`: control del widget mediante archivos temporales en `$TMPDIR`.

## Widget

El widget carga `widget-electron/index.html` y comunica estado via archivos temporales `vozdev_*.txt` en `$TMPDIR`.

Estados conocidos:

- `idle`
- `user`
- `thinking`
- `ai`

Usar `set_widget_state()` para cambios de estado desde cualquier hilo.

En `widget-electron/index.html`, el CSS debe usar custom properties definidas en `:root`; evitar colores hex hardcodeados.

## Dependencias importantes

```text
openai
pyaudio
websockets
pywebview
openwakeword
pyobjc-framework-Quartz
numpy
rumps
```

Notas:

- openWakeWord descarga un modelo ONNX de aproximadamente 5 MB en el primer uso.
- Quartz se usa solo en macOS para el CGEvent tap del hotkey.

## Convenciones del proyecto

- Escribir codigo y comentarios en espanol, siguiendo el estilo existente.
- Evitar type hints exhaustivos cuando el duck typing sea obvio.
- Usar `cfg.*` para toda configuracion; no hardcodear valores configurables.
- Usar `set_widget_state()` para cambiar el estado del widget desde cualquier hilo.
- Usar `loop.call_soon_threadsafe()` cuando un hilo daemon necesite llamar funciones asyncio.
- Mantener los cambios acotados al comportamiento solicitado.
- No reintroducir colas asyncio en el camino critico de salida de audio.
