import array
import struct
import time
from asyncio import Queue, QueueEmpty

import pyaudio

from voz import config as cfg


def pcm_rms(data: bytes) -> float:
    n = len(data) // 2
    if not n:
        return 0.0
    samples = struct.unpack_from(f"{n}h", data)
    return (sum(s * s for s in samples) / n) ** 0.5


def resample_pcm16(data: bytes, from_rate: int, to_rate: int) -> bytes:
    if from_rate == to_rate:
        return data
    n_in = len(data) // 2
    if n_in < 2:
        return data
    samples_in = struct.unpack_from(f"{n_in}h", data)
    ratio = to_rate / from_rate
    n_out = max(1, int(n_in * ratio))
    out = array.array("h")
    for i in range(n_out):
        src = i / ratio
        idx = int(src)
        frac = src - idx
        if idx >= n_in - 1:
            s = samples_in[n_in - 1]
        else:
            s = int(samples_in[idx] * (1 - frac) + samples_in[idx + 1] * frac)
        out.append(max(-32768, min(32767, s)))
    return out.tobytes()


def amplificar_mic(data: bytes, gain: float) -> bytes:
    if gain == 1.0:
        return data
    samples = array.array("h", struct.unpack_from(f"{len(data) // 2}h", data))
    for i in range(len(samples)):
        v = int(samples[i] * gain)
        samples[i] = max(-32768, min(32767, v))
    return samples.tobytes()


def atenuar_ruido_suave(data: bytes, gate_rms: float) -> bytes:
    rms = pcm_rms(data)
    if rms >= gate_rms:
        return data
    ratio = max(0.2, (rms / gate_rms) * 0.65)
    samples = array.array("h", struct.unpack_from(f"{len(data) // 2}h", data))
    for i in range(len(samples)):
        v = int(samples[i] * ratio)
        samples[i] = max(-32768, min(32767, v))
    return samples.tobytes()


def mic_en_mute(state: dict, audio_queue: Queue) -> bool:
    if not cfg.VOZ_HALF_DUPLEX:
        return False
    if state["reproduciendo"] or state["pendiente_fin"]:
        return True
    if not audio_queue.empty():
        return True
    if time.time() < state.get("mute_hasta", 0):
        return True
    return False


def procesar_entrada_mic(data: bytes) -> bytes:
    rms = pcm_rms(data)
    gain = cfg.VOZ_MIC_GAIN
    if rms >= 80:
        gain *= min(cfg.VOZ_MIC_MAX_GAIN, max(1.0, cfg.VOZ_MIC_TARGET_RMS / rms))
    data = amplificar_mic(data, gain)
    if cfg.VOZ_VOICE_GATE_RMS > 0:
        data = atenuar_ruido_suave(data, cfg.VOZ_VOICE_GATE_RMS)
    return data


def abrir_microfono(pa: pyaudio.PyAudio):
    device_index = None
    if cfg.VOZ_INPUT_DEVICE:
        device_index = int(cfg.VOZ_INPUT_DEVICE)

    kwargs = dict(
        format=pyaudio.paInt16,
        channels=1,
        input=True,
        frames_per_buffer=cfg.CHUNK,
    )
    if device_index is not None:
        kwargs["input_device_index"] = device_index

    try:
        stream = pa.open(rate=cfg.RATE, **kwargs)
        capture_rate = cfg.RATE
    except OSError:
        if device_index is not None:
            info = pa.get_device_info_by_index(device_index)
        else:
            info = pa.get_default_input_device_info()
        capture_rate = int(info["defaultSampleRate"])
        stream = pa.open(rate=capture_rate, **kwargs)

    if device_index is not None:
        info = pa.get_device_info_by_index(device_index)
    else:
        info = pa.get_default_input_device_info()
    print(f"🎤 {info['name']} — captura {capture_rate} Hz → envío {cfg.RATE} Hz")
    return stream, capture_rate
