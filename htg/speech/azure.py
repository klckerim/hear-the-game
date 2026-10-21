"""Azure AI Speech text-to-speech: MP3 bytes, cached on disk by (text, voice)."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from xml.sax.saxutils import escape

CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "cache" / "audio"
LOCALE = {"en": "en-GB", "tr": "tr-TR"}
# Spoken form of names the voice mispronounces: {"Lindqvist": "Lindkvist"}. Fill after listening; never rename players.
ALIASES: dict[str, dict[str, str]] = {"en": {}, "tr": {}}


def ssml(text: str, lang: str, voice: str) -> str:
    body = escape(text)
    for name, alias in ALIASES[lang].items():
        body = body.replace(name, f'<sub alias="{escape(alias)}">{name}</sub>')
    return (f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="{LOCALE[lang]}">'
            f'<voice name="{voice}">{body}</voice></speak>')


class AzureSpeech:
    def __init__(self, cache_dir: Path = CACHE_DIR) -> None:
        import azure.cognitiveservices.speech as sdk

        self.sdk, self.cache_dir = sdk, cache_dir
        self.voices = {"en": os.environ.get("SPEECH_VOICE_EN", "en-GB-SoniaNeural"),
                       "tr": os.environ.get("SPEECH_VOICE_TR", "tr-TR-EmelNeural")}
        if os.environ.get("SPEECH_KEY") and os.environ.get("SPEECH_REGION"):  # local-only fallback
            cfg = sdk.SpeechConfig(subscription=os.environ["SPEECH_KEY"], region=os.environ["SPEECH_REGION"])
        else:
            from azure.identity import DefaultAzureCredential

            cfg = sdk.SpeechConfig(token_credential=DefaultAzureCredential(), endpoint=os.environ["SPEECH_ENDPOINT"])
        cfg.set_speech_synthesis_output_format(sdk.SpeechSynthesisOutputFormat.Audio24Khz48KBitRateMonoMp3)
        self.synth = sdk.SpeechSynthesizer(speech_config=cfg, audio_config=None)  # None: bytes in memory, no speaker
        self.characters = 0  # sent to TTS this run (cache hits excluded)

    def synthesize(self, text: str, lang: str) -> bytes | None:
        voice = self.voices[lang]
        path = self.cache_dir / f"{hashlib.sha256(f'{voice}|{text}'.encode()).hexdigest()[:32]}.mp3"
        if path.exists():
            return path.read_bytes()
        try:
            result = self.synth.speak_ssml_async(ssml(text, lang, voice)).get()
        except Exception:
            return None
        if result.reason != self.sdk.ResultReason.SynthesizingAudioCompleted:
            return None
        self.characters += len(text)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path.write_bytes(result.audio_data)
        return result.audio_data
