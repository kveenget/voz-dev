import json
import os
import struct
import tempfile
import urllib.request
import wave

import pyaudio

from voz import config as cfg
from voz.widget_ctl import set_widget_state, set_widget_visible

WAKE_WORDS = [
    "hey mike",
    "hey mic",
    "ei mike",
    "hey my",
    "oye mike",
    "a mike",
    "mike",
    "hei mike",
    "hay mike",
    "hey maik",
    "ey mike",
    "hey mate",
    "hey mickey",
    "hey mick",
    "hey might",
    "hey mk",
    "hey nike",
    "hey bike",
    "hey like",
    "mãe",
    "hey mae",
    "ei mae",
    "hey mike!",
    "hey, mike",
    "hey, mike!",
]
CHUNK_SECS = 2


def escuchar_wake_word() -> None:
    print("😴 Esperando 'Hey Mike'...")
    set_widget_state("idle")

    p = pyaudio.PyAudio()
    stream = p.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=16000,
        input=True,
        frames_per_buffer=1024,
    )

    try:
        while True:
            frames = []
            for _ in range(0, int(16000 / 1024 * CHUNK_SECS)):
                data = stream.read(1024, exception_on_overflow=False)
                frames.append(data)

            all_samples = b"".join(frames)
            samples = struct.unpack_from(f"{len(all_samples) // 2}h", all_samples)
            rms = (sum(s * s for s in samples) / len(samples)) ** 0.5
            if rms < 200:
                continue

            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            wf = wave.open(tmp.name, "wb")
            wf.setnchannels(1)
            wf.setsampwidth(p.get_sample_size(pyaudio.paInt16))
            wf.setframerate(16000)
            wf.writeframes(all_samples)
            wf.close()

            try:
                with open(tmp.name, "rb") as f:
                    audio_data = f.read()

                boundary = "----WebKitFormBoundary"
                body = (
                    f"--{boundary}\r\n"
                    f'Content-Disposition: form-data; name="file"; filename="audio.wav"\r\n'
                    f"Content-Type: audio/wav\r\n\r\n"
                ).encode() + audio_data + (
                    f"\r\n--{boundary}\r\n"
                    f'Content-Disposition: form-data; name="model"\r\n\r\n'
                    f"whisper-1\r\n"
                    f"--{boundary}--\r\n"
                ).encode()

                req = urllib.request.Request(
                    "https://api.openai.com/v1/audio/transcriptions",
                    data=body,
                    headers={
                        "Authorization": f"Bearer {cfg.OPENAI_API_KEY}",
                        "Content-Type": f"multipart/form-data; boundary={boundary}",
                    },
                )
                with urllib.request.urlopen(req, context=cfg.ssl_context, timeout=5) as r:
                    result = json.loads(r.read())
                    texto = result.get("text", "").lower().strip()

                if texto:
                    print(f"  👂 {texto}")

                for ww in WAKE_WORDS:
                    if ww in texto:
                        print("\n🎙️  Hey Mike detectado!")
                        set_widget_visible(True)
                        stream.stop_stream()
                        stream.close()
                        p.terminate()
                        os.unlink(tmp.name)
                        return

            except Exception:
                pass

            try:
                os.unlink(tmp.name)
            except OSError:
                pass

    except KeyboardInterrupt:
        stream.stop_stream()
        stream.close()
        p.terminate()
        raise
