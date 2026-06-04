import os
import ssl

import certifi
from dotenv import load_dotenv

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WIDGET_SCRIPT = os.path.join(ROOT_DIR, "widget.py")

load_dotenv(os.path.join(ROOT_DIR, ".env"))

ssl_context = ssl.create_default_context(cafile=certifi.where())
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

CHUNK = 2048
RATE = 24000

VOZ_VAD_THRESHOLD = float(os.getenv("VOZ_VAD_THRESHOLD", "0.38"))
VOZ_VOICE_GATE_RMS = float(os.getenv("VOZ_VOICE_GATE_RMS", "0"))
VOZ_MIC_GAIN = float(os.getenv("VOZ_MIC_GAIN", "1.5"))
VOZ_MIC_TARGET_RMS = float(os.getenv("VOZ_MIC_TARGET_RMS", "3200"))
VOZ_MIC_MAX_GAIN = float(os.getenv("VOZ_MIC_MAX_GAIN", "4.0"))
VOZ_NOISE_REDUCTION = os.getenv("VOZ_NOISE_REDUCTION", "far_field").strip().lower()
VOZ_VOICE = os.getenv("VOZ_VOICE", "cedar").strip().lower()
VOZ_INPUT_DEVICE = os.getenv("VOZ_INPUT_DEVICE", "").strip()
VOZ_HALF_DUPLEX = os.getenv("VOZ_HALF_DUPLEX", "1").lower() not in ("0", "false", "no")
VOZ_ECHO_COOLDOWN_S = float(os.getenv("VOZ_ECHO_COOLDOWN_S", "0.4"))
VOZ_ALLOW_BARGE_IN = os.getenv("VOZ_ALLOW_BARGE_IN", "").lower() in ("1", "true", "yes")
VOZ_INTERRUPT_RESPONSE = os.getenv("VOZ_INTERRUPT_RESPONSE", "").lower() in (
    "1",
    "true",
    "yes",
)

PROJECT_ROOT = os.path.expanduser(os.getenv("VOZ_PROJECT_ROOT", ROOT_DIR))
LIST_MICS = os.getenv("VOZ_LIST_MICS", "").lower() in ("1", "true", "yes")
# option+a (⌥A) — Mac; alternativas: cmd+shift+space, f19
HOTKEY_KEYS = os.getenv("VOZ_HOTKEY_KEYS", "option+a").strip()
GREET_ON_ACTIVATE = os.getenv("VOZ_GREET_ON_ACTIVATE", "1").lower() not in (
    "0",
    "false",
    "no",
)
GREETING_MESSAGE = os.getenv("VOZ_GREETING_MESSAGE", "").strip()


def activation_mode() -> str:
    """hotkey (default) | always | wake"""
    if "VOZ_ACTIVATION" in os.environ:
        raw = os.environ["VOZ_ACTIVATION"].strip().lower()
        if raw in ("always", "hotkey", "wake"):
            return raw
    if os.getenv("VOZ_WAKE_WORD", "").lower() in ("1", "true", "yes"):
        return "wake"
    if os.getenv("VOZ_HOTKEY", "").lower() in ("1", "true", "yes"):
        return "hotkey"
    return "hotkey"


# Compat con código que usaba WAKE_ENABLED
WAKE_ENABLED = activation_mode() == "wake"
HOTKEY_ENABLED = activation_mode() == "hotkey"

# ── Wake Word (Porcupine) ────────────────────────────────────────────────────
PICOVOICE_ACCESS_KEY = os.getenv("PICOVOICE_ACCESS_KEY", "")
WAKE_SENSITIVITY = float(os.getenv("MIKE_SENSITIVITY", "0.5"))
# Keyword built-in (ej: "jarvis", "alexa", "hey google") o vacío para usar .ppn
WAKE_KEYWORD = os.getenv("MIKE_KEYWORD", "jarvis")
WAKE_KEYWORD_PATH = os.path.join(ROOT_DIR, "models", "hey-mike_mac.ppn")
