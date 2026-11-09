
import os
import base64
import binascii
import wave
from pathlib import Path

import requests
from dotenv import load_dotenv


# ==================================================
# CONFIGURATION
# ==================================================

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

GNANI_API_KEY = os.getenv("GNANI_API_KEY")

STT_URL = "https://api.vachana.ai/stt/v3"
TTS_URL = "https://api.vachana.ai/api/v1/tts/inference"

# Must match the TTS audio_config below.
SAMPLE_RATE = 48000
CHANNELS = 1
SAMPLE_WIDTH = 2


# ==================================================
# HEADERS
# ==================================================

def get_headers():
    if not GNANI_API_KEY:
        raise ValueError(
            "GNANI_API_KEY is missing. Check the root .env file."
        )

    return {"X-API-Key-ID": GNANI_API_KEY}


# ==================================================
# GNANI PRISMA - SPEECH TO TEXT
# ==================================================

def transcribe_audio(audio_path, language_code="hi-IN"):
    """Transcribe an audio file using Gnani Prisma STT."""

    file_path = Path(audio_path)

    if not file_path.is_file():
        raise FileNotFoundError(
            f"Audio file not found: {file_path}"
        )

    headers = get_headers()

    with file_path.open("rb") as audio_file:
        files = {
            "audio_file": (file_path.name, audio_file)
        }

        data = {
            "language_code": language_code
        }

        response = requests.post(
            STT_URL,
            headers=headers,
            files=files,
            data=data,
            timeout=90
        )

    if not response.ok:
        raise RuntimeError(
            f"Gnani STT error {response.status_code}: "
            f"{response.text[:1000]}"
        )

    return response.json()


# ==================================================
# TTS RESPONSE DECODING
# ==================================================

def extract_audio_bytes(response):
    """
    Extract audio bytes from Gnani TTS response.

    Supports:
    1. Direct WAV/audio responses.
    2. Raw PCM responses.
    3. JSON responses containing base64 audio.
    """

    content_type = response.headers.get(
        "content-type", ""
    ).lower()

    body = response.content

    if not body:
        raise RuntimeError(
            "Gnani TTS returned an empty response."
        )

    # Check whether the response is JSON, even if
    # the server returned an unexpected content type.
    if (
        "json" in content_type
        or body.lstrip().startswith(b"{")
    ):
        try:
            result = response.json()
        except ValueError as error:
            raise RuntimeError(
                "Gnani TTS returned invalid JSON."
            ) from error

        audio_base64 = None

        for key in (
            "audio",
            "audio_content",
            "audio_base64"
        ):
            value = result.get(key)

            if isinstance(value, str) and value.strip():
                audio_base64 = value.strip()
                break

        if not audio_base64:
            raise RuntimeError(
                "Audio data missing in Gnani TTS response. "
                f"Response keys: {list(result.keys())}"
            )

        # Support data URI format.
        if audio_base64.startswith("data:"):
            audio_base64 = audio_base64.split(",", 1)[-1]

        try:
            body = base64.b64decode(
                audio_base64,
                validate=True
            )
        except (binascii.Error, ValueError) as error:
            raise RuntimeError(
                "Could not decode base64 audio from Gnani."
            ) from error

    if not body:
        raise RuntimeError(
            "Gnani TTS returned empty audio data."
        )

    return body


# ==================================================
# WAV VALIDATION AND PCM CONVERSION
# ==================================================

def save_as_wav(audio_bytes, output_path):
    """
    Save valid WAV data directly.

    If Gnani returns raw 16-bit PCM instead,
    add a standard WAV header.
    """

    destination = Path(output_path)
    destination.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    # A valid WAV file starts with RIFF and WAVE.
    if (
        audio_bytes.startswith(b"RIFF")
        and audio_bytes[8:12] == b"WAVE"
    ):
        destination.write_bytes(audio_bytes)

    # Other common audio containers should not be
    # incorrectly labelled as WAV.
    elif (
        audio_bytes.startswith(b"ID3")
        or audio_bytes.startswith(b"OggS")
        or audio_bytes.startswith(b"fLaC")
    ):
        raise RuntimeError(
            "Gnani returned a non-WAV audio format, "
            "although WAV was requested. "
            "Please inspect the API response format."
        )

    else:
        # Raw linear PCM: wrap it in a WAV container.
        if len(audio_bytes) % SAMPLE_WIDTH != 0:
            raise RuntimeError(
                "Gnani returned PCM data with an invalid "
                "sample length."
            )

        with wave.open(str(destination), "wb") as wav_file:
            wav_file.setnchannels(CHANNELS)
            wav_file.setsampwidth(SAMPLE_WIDTH)
            wav_file.setframerate(SAMPLE_RATE)
            wav_file.writeframes(audio_bytes)

    # Verify the resulting file.
    with wave.open(str(destination), "rb") as wav_file:
        if wav_file.getnchannels() != CHANNELS:
            raise RuntimeError("Unexpected WAV channel count.")

        if wav_file.getframerate() != SAMPLE_RATE:
            raise RuntimeError("Unexpected WAV sample rate.")

        if wav_file.getsampwidth() != SAMPLE_WIDTH:
            raise RuntimeError("Unexpected WAV sample width.")

        if wav_file.getnframes() == 0:
            raise RuntimeError("Generated WAV contains no audio.")

    return str(destination)


# ==================================================
# GNANI TIMBRE - TEXT TO SPEECH
# ==================================================

def generate_speech(
    text,
    output_path,
    language_code="hi-IN",
    voice="Kaveri"
):
    """Generate and save spoken audio using Gnani Timbre."""

    if not text or not text.strip():
        raise ValueError("Text cannot be empty.")

    payload = {
        "text": text.strip(),
        "model": "timbre-v2.5",
        "voice": voice,
        "language": language_code,
        "audio_config": {
            "format": "wav",
            "encoding": "linear_pcm",
            "channels": CHANNELS,
            "sample_rate": SAMPLE_RATE,
            "sample_width": SAMPLE_WIDTH
        }
    }

    response = requests.post(
        TTS_URL,
        headers={
            **get_headers(),
            "Content-Type": "application/json"
        },
        json=payload,
        timeout=90
    )

    if not response.ok:
        raise RuntimeError(
            f"Gnani TTS error {response.status_code}: "
            f"{response.text[:1000]}"
        )

    audio_bytes = extract_audio_bytes(response)

    return save_as_wav(
        audio_bytes,
        output_path
    )
