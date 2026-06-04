import asyncio
import base64
import json
import os
import tempfile
import time

import pyaudio
import websockets

from agent_tools.constants import SHUTDOWN_SENTINEL

from voz import config as cfg
from voz.audio import (
    abrir_microfono,
    mic_en_mute,
    pcm_rms,
    procesar_entrada_mic,
    resample_pcm16,
)
from voz.exceptions import ShutdownAgent
from voz.prompts import activation_opening_user_message, system_prompt
from voz.tools_runtime import ejecutar_funcion, session_tools
from voz.widget_ctl import set_widget_state

_VOICE_FILE   = os.path.join(tempfile.gettempdir(), "vozdev_voice.txt")
_STOP_FILE    = os.path.join(tempfile.gettempdir(), "vozdev_stop.txt")
_CMD_FILE     = os.path.join(tempfile.gettempdir(), "vozdev_cmd.txt")
_PROJECT_FILE = os.path.join(tempfile.gettempdir(), "vozdev_project.txt")
_MUTE_FILE    = os.path.join(tempfile.gettempdir(), "vozdev_mute.txt")

# RMS mínimo para detectar voz en el cliente (sin esperar el VAD del servidor).
# Valor bajo a propósito: muestra "user" en cuanto hay audio, el servidor confirma después.
_PRE_VAD_RMS = float(cfg.__dict__.get("VOZ_PRE_VAD_RMS", 380))


async def _enviar_saludo_inicial(ws) -> None:
    texto = activation_opening_user_message(cfg.GREETING_MESSAGE)
    set_widget_state("thinking")
    await ws.send(
        json.dumps(
            {
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": texto}],
                },
            }
        )
    )
    await ws.send(json.dumps({"type": "response.create"}))


async def conectar_realtime(*, saludo_inicial: bool = False) -> None:
    uri = "wss://api.openai.com/v1/realtime?model=gpt-realtime-2"
    headers = {"Authorization": f"Bearer {cfg.OPENAI_API_KEY}"}

    print("🎙️  Conectando con GPT Realtime 2...")
    async with websockets.connect(uri, additional_headers=headers, ssl=cfg.ssl_context) as ws:
        print("✅ Conectado!\n")

        audio_input = {
            "format": {"type": "audio/pcm", "rate": 24000},
            "transcription": {
                "model": "gpt-4o-transcribe",
                "language": "es",
                "prompt": (
                    "Transcripción fiel en español. El usuario es desarrollador; "
                    "puede mezclar términos en inglés (git, commit, Python, API)."
                ),
            },
            "turn_detection": {
                "type": "server_vad",
                "threshold": cfg.VOZ_VAD_THRESHOLD,
                "prefix_padding_ms": 800,
                "silence_duration_ms": 1400,
                "create_response": True,
                "interrupt_response": cfg.VOZ_INTERRUPT_RESPONSE,
            },
        }
        if cfg.VOZ_NOISE_REDUCTION in ("near_field", "far_field"):
            audio_input["noise_reduction"] = {"type": cfg.VOZ_NOISE_REDUCTION}
            print(f"🔇 Reducción de ruido: {cfg.VOZ_NOISE_REDUCTION}")

        gate_txt = "off" if cfg.VOZ_VOICE_GATE_RMS <= 0 else str(int(cfg.VOZ_VOICE_GATE_RMS))
        duplex = "mic pausa mientras habla (anti-eco)" if cfg.VOZ_HALF_DUPLEX else "mic siempre activo"
        print(
            f"🎚️  VAD={cfg.VOZ_VAD_THRESHOLD}  ganancia={cfg.VOZ_MIC_GAIN}  "
            f"fondo={gate_txt}  {duplex}"
        )

        voz_inicial = _leer_archivo_str(_VOICE_FILE) or cfg.VOZ_VOICE

        _session_cfg = {
            "type": "realtime",
            "instructions": system_prompt(),
            "output_modalities": ["audio"],
            "audio": {
                "input": audio_input,
                "output": {
                    "format": {"type": "audio/pcm", "rate": 24000},
                    "voice": voz_inicial,
                },
            },
            "tools": session_tools(),
            "tool_choice": "auto",
        }

        await ws.send(json.dumps({"type": "session.update", "session": _session_cfg}))

        p = pyaudio.PyAudio()
        stream_in, capture_rate = abrir_microfono(p)
        stream_out = p.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=cfg.RATE,
            output=True,
            frames_per_buffer=cfg.CHUNK * 2,
        )

        state = {
            "activo": True,
            "call_id": None,
            "call_name": None,
            "call_args": "",
            "reproduciendo": False,
            "interrumpir": False,
            "shutdown": False,
            "pendiente_fin": False,
            "mute_hasta": 0.0,
            "limpiar_buffer_mic": False,
            "saludo_pendiente": saludo_inicial and cfg.GREET_ON_ACTIVATE,
            # Flags de sincronización de widget
            "pre_vad": False,          # el cliente detectó voz antes del servidor
            "ejecutando_tool": False,  # hay una tool corriendo ahora mismo
            "esperando_respuesta": False,  # tool terminó, esperando que el modelo responda
            "user_muted": _leer_archivo_str(_MUTE_FILE) == "1",
        }
        audio_queue = asyncio.Queue(maxsize=1024)
        loop = asyncio.get_event_loop()

        # ── Helpers de estado ───────────────────────────────────────────────

        def _widget(s: str) -> None:
            """Actualiza el widget solo si el estado lógico lo permite."""
            # No pisar "ai" ni "user" con estados de menor prioridad
            # Prioridad: ai > user > thinking > idle
            prioridad = {"ai": 4, "user": 3, "thinking": 2, "connecting": 2,
                         "capturing": 2, "analyzing": 2, "idle": 1}
            actual = state.get("_widget_actual", "idle")
            if prioridad.get(s, 0) >= prioridad.get(actual, 0) or s == "idle":
                state["_widget_actual"] = s
                set_widget_state(s)

        def _widget_force(s: str) -> None:
            """Actualiza sin importar prioridades (para transiciones explícitas)."""
            state["_widget_actual"] = s
            set_widget_state(s)

        def _fin_reproduccion() -> None:
            state["reproduciendo"] = False
            state["pendiente_fin"] = False
            state["interrumpir"] = False
            state["pre_vad"] = False
            state["mute_hasta"] = time.time() + cfg.VOZ_ECHO_COOLDOWN_S
            state["limpiar_buffer_mic"] = True
            # Si hay una tool corriendo, no pisar el estado
            if not state["ejecutando_tool"] and not state["esperando_respuesta"]:
                _widget_force("idle")

        def _drain_audio_queue() -> None:
            while True:
                try:
                    audio_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

        # ── Corrutinas ──────────────────────────────────────────────────────

        async def reproducir_audio():
            while state["activo"]:
                pcm = await audio_queue.get()
                if state["interrumpir"]:
                    continue
                _widget_force("ai")
                try:
                    await loop.run_in_executor(None, stream_out.write, pcm)
                except OSError:
                    pass
                if state["pendiente_fin"] and audio_queue.empty():
                    _fin_reproduccion()

        async def capturar_y_enviar():
            while state["activo"]:
                raw = await loop.run_in_executor(
                    None, lambda: stream_in.read(cfg.CHUNK, exception_on_overflow=False)
                )

                if state["user_muted"]:
                    continue  # lee el mic para evitar overflow pero no envía

                rms = pcm_rms(raw)

                # ── Barge-in: interrumpir al agente mientras habla ──────────
                if cfg.VOZ_ALLOW_BARGE_IN and state["reproduciendo"] and rms > 1800:
                    print("\n⚡ Interrumpiendo...")
                    state["interrumpir"] = True
                    state["pendiente_fin"] = False
                    _drain_audio_queue()
                    _fin_reproduccion()
                    _widget_force("user")
                    state["pre_vad"] = True
                    await ws.send(json.dumps({"type": "response.cancel"}))
                    await asyncio.sleep(0.2)

                # ── Pre-VAD cliente: muestra "user" antes del servidor ──────
                # Solo cuando el mic no está en mute y no está el agente hablando
                if not state["reproduciendo"] and not state["pendiente_fin"] \
                        and time.time() > state["mute_hasta"] \
                        and not state["ejecutando_tool"]:
                    if rms > _PRE_VAD_RMS:
                        if not state["pre_vad"]:
                            state["pre_vad"] = True
                            _widget_force("user")
                    else:
                        # Silencio sostenido — reset pre-VAD sin cambiar widget
                        # (el servidor confirma el estado real)
                        if state["pre_vad"] and rms < _PRE_VAD_RMS * 0.35:
                            state["pre_vad"] = False

                if mic_en_mute(state, audio_queue):
                    continue

                if state.pop("limpiar_buffer_mic", False):
                    await ws.send(json.dumps({"type": "input_audio_buffer.clear"}))

                data = procesar_entrada_mic(raw)
                if capture_rate != cfg.RATE:
                    data = resample_pcm16(data, capture_rate, cfg.RATE)

                await ws.send(
                    json.dumps(
                        {
                            "type": "input_audio_buffer.append",
                            "audio": base64.b64encode(data).decode("utf-8"),
                        }
                    )
                )

        async def recibir_eventos():
            async for mensaje in ws:
                evento = json.loads(mensaje)
                tipo = evento.get("type", "")

                # ── Audio del agente ────────────────────────────────────────
                if tipo == "response.output_audio.delta":
                    if not state["interrumpir"]:
                        state["reproduciendo"] = True
                        state["pendiente_fin"] = False
                        state["esperando_respuesta"] = False
                        pcm = base64.b64decode(evento["delta"])
                        await audio_queue.put(pcm)

                elif tipo == "response.output_audio.done":
                    state["pendiente_fin"] = True
                    if audio_queue.empty():
                        _fin_reproduccion()

                # ── Transcripción del agente (solo log) ────────────────────
                elif tipo == "response.output_audio_transcript.delta":
                    print(evento.get("delta", ""), end="", flush=True)

                elif tipo == "response.output_audio_transcript.done":
                    print()

                # ── Tool calls ──────────────────────────────────────────────
                elif tipo == "response.function_call_arguments.delta":
                    state["call_args"] += evento.get("delta", "")

                elif tipo == "response.output_item.added":
                    item = evento.get("item", {})
                    if item.get("type") == "function_call":
                        state["call_id"] = item.get("call_id")
                        state["call_name"] = item.get("name")
                        state["call_args"] = ""
                        state["ejecutando_tool"] = True
                        print(f"\n🔧 Tool: {item.get('name')}")
                        _widget_force("thinking")

                elif tipo == "response.done":
                    if state["call_id"]:
                        # Ejecutar la tool
                        try:
                            args = json.loads(state["call_args"]) if state["call_args"] else {}
                        except json.JSONDecodeError:
                            args = {}

                        resultado = ejecutar_funcion(state["call_name"], args)

                        state["ejecutando_tool"] = False

                        if resultado == SHUTDOWN_SENTINEL:
                            state["activo"] = False
                            state["shutdown"] = True
                            return

                        # Enviar resultado — el modelo está procesando
                        state["esperando_respuesta"] = True
                        _widget_force("thinking")

                        await ws.send(
                            json.dumps(
                                {
                                    "type": "conversation.item.create",
                                    "item": {
                                        "type": "function_call_output",
                                        "call_id": state["call_id"],
                                        "output": str(resultado),
                                    },
                                }
                            )
                        )
                        await ws.send(json.dumps({"type": "response.create"}))

                        state["call_id"] = None
                        state["call_name"] = None
                        state["call_args"] = ""
                    else:
                        # Respuesta sin tool: el modelo terminó de planear / hablar
                        state["esperando_respuesta"] = False

                # ── Transcripción del usuario ───────────────────────────────
                elif tipo in (
                    "conversation.item.input_audio_transcription.completed",
                    "conversation.item.input_audio_transcription.done",
                ):
                    transcript = (
                        evento.get("transcript")
                        or evento.get("item", {}).get("transcript")
                        or ""
                    ).strip()
                    if transcript:
                        print(f"\n📝 Tú: {transcript}\n")

                # ── VAD del servidor ────────────────────────────────────────
                elif tipo == "input_audio_buffer.speech_started":
                    print("\n🎤 Escuchando...")
                    state["pre_vad"] = True
                    _widget_force("user")

                elif tipo == "input_audio_buffer.speech_stopped":
                    print("⏎  Procesando...")
                    state["pre_vad"] = False
                    _widget_force("thinking")

                # ── Respuesta en generación (sin audio todavía) ─────────────
                elif tipo == "response.created":
                    if not state["reproduciendo"]:
                        _widget("thinking")

                elif tipo == "response.audio_transcript.delta":
                    # El modelo está generando — asegurar estado thinking si no hay audio aún
                    if not state["reproduciendo"]:
                        _widget("thinking")

                # ── Sesión ──────────────────────────────────────────────────
                elif tipo == "session.created":
                    print("📡 Sesión iniciada")

                elif tipo == "session.updated":
                    print("⚙️  Listo — ¡habla ahora!\n")
                    _widget_force("idle")
                    startup_cmd = _leer_archivo_str(_CMD_FILE)
                    if startup_cmd:
                        try:
                            open(_CMD_FILE, "w").close()
                        except OSError:
                            pass
                        print(f"\n⚡ Comando de inicio: {startup_cmd}")
                        await ws.send(json.dumps({
                            "type": "conversation.item.create",
                            "item": {
                                "type": "message",
                                "role": "user",
                                "content": [{"type": "input_text", "text": startup_cmd}],
                            },
                        }))
                        await ws.send(json.dumps({"type": "response.create"}))
                        _widget_force("thinking")
                    elif state.pop("saludo_pendiente", False):
                        await _enviar_saludo_inicial(ws)

                elif tipo == "error":
                    err = evento.get("error", {})
                    print(f"\n❌ Error: {err.get('message', '')} [{err.get('code', '')}]")
                    # No dejar el widget colgado en thinking si hay error
                    if not state["reproduciendo"]:
                        _widget_force("idle")

        async def vigilar_widget():
            """Detecta cambios de voz, stop, comandos rápidos y proyecto desde el widget."""
            voz_activa = voz_inicial
            stop_ts = _leer_ts(_STOP_FILE)
            try:
                cmd_mtime = os.path.getmtime(_CMD_FILE)
            except OSError:
                cmd_mtime = 0.0

            while state["activo"]:
                await asyncio.sleep(0.5)

                # Cambio de voz en tiempo real
                nueva_voz = _leer_archivo_str(_VOICE_FILE)
                if nueva_voz and nueva_voz != voz_activa:
                    voz_activa = nueva_voz
                    print(f"\n🎙️  Cambiando voz → {nueva_voz}")
                    # Solo audio.output — no re-enviar audio.input para no
                    # resetear VAD ni transcripción (evita corte de audio)
                    cfg_voz = {
                        "type": _session_cfg["type"],
                        "instructions": _session_cfg["instructions"],
                        "output_modalities": _session_cfg["output_modalities"],
                        "audio": {
                            "output": {
                                **_session_cfg["audio"]["output"],
                                "voice": nueva_voz,
                            },
                        },
                        "tools": _session_cfg["tools"],
                        "tool_choice": _session_cfg["tool_choice"],
                    }
                    await ws.send(json.dumps({"type": "session.update", "session": cfg_voz}))

                # Señal de detener sesión desde el widget
                nuevo_stop_ts = _leer_ts(_STOP_FILE)
                if nuevo_stop_ts and nuevo_stop_ts != stop_ts:
                    stop_ts = nuevo_stop_ts
                    print("\n⏹  Stop desde widget")
                    state["activo"] = False
                    return

                # Comando rápido desde quick actions
                try:
                    mtime = os.path.getmtime(_CMD_FILE)
                    if mtime > cmd_mtime:
                        cmd_mtime = mtime
                        cmd = _leer_archivo_str(_CMD_FILE)
                        if cmd and not state.get("reproduciendo") and not state.get("ejecutando_tool"):
                            try:
                                open(_CMD_FILE, "w").close()
                            except OSError:
                                pass
                            print(f"\n⚡ Comando rápido: {cmd}")
                            await ws.send(json.dumps({
                                "type": "conversation.item.create",
                                "item": {
                                    "type": "message",
                                    "role": "user",
                                    "content": [{"type": "input_text", "text": cmd}],
                                },
                            }))
                            await ws.send(json.dumps({"type": "response.create"}))
                            _widget_force("thinking")
                except OSError:
                    pass

                # Mute del mic desde el widget
                nuevo_mute = _leer_archivo_str(_MUTE_FILE) == "1"
                if nuevo_mute != state["user_muted"]:
                    state["user_muted"] = nuevo_mute
                    if nuevo_mute:
                        print("\n🔇 Mic silenciado")
                        await ws.send(json.dumps({"type": "input_audio_buffer.clear"}))
                    else:
                        print("\n🎙️  Mic activo")

                # Cambio de proyecto activo
                nueva_proj = _leer_archivo_str(_PROJECT_FILE)
                if nueva_proj and nueva_proj != cfg.PROJECT_ROOT:
                    cfg.PROJECT_ROOT = nueva_proj
                    print(f"\n📁 Proyecto → {nueva_proj}")

        try:
            await asyncio.gather(
                capturar_y_enviar(),
                recibir_eventos(),
                reproducir_audio(),
                vigilar_widget(),
            )
        finally:
            state["activo"] = False
            stream_in.stop_stream()
            stream_in.close()
            stream_out.stop_stream()
            stream_out.close()
            p.terminate()

        if state.get("shutdown"):
            raise ShutdownAgent()


def _leer_archivo_str(path: str) -> str:
    try:
        return open(path, encoding="utf-8").read().strip()
    except OSError:
        return ""


def _leer_ts(path: str) -> str:
    """Lee un archivo de timestamp; retorna '' si no existe."""
    return _leer_archivo_str(path)
