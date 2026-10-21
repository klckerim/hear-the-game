"""Azure AI Speech text-to-speech: MP3 bytes, cached on disk by (text, voice)."""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from xml.sax.saxutils import escape

CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "cache" / "audio"
LOCALE = {"en": "en-GB", "tr": "tr-TR"}
# Spoken form of names the voice mispronounces: {"Lindqvist": "Lindkvist"}. Fill after listening; never rename players.
ALIASES: dict[str, dict[str, str]] = {"en": {}, "tr": {}}
SSML_VERSION = 2  # part of the clip cache key: bump when ssml() changes how the same text sounds
# Turkish integers are spoken from words: "yüzde 23." was read as an ordinal ("yirmi üçüncü") and say-as cardinal is not
# supported for tr-TR. Decimals ("2,3") and scores ("1-2") are left alone; the voice reads them correctly.
TR_INTEGER = re.compile(r"(?<![\d,.\-])\d{1,3}(?![\d\-]|[.,]\d)")
TR_ONES = ["", "bir", "iki", "üç", "dört", "beş", "altı", "yedi", "sekiz", "dokuz"]
TR_TENS = ["", "on", "yirmi", "otuz", "kırk", "elli", "altmış", "yetmiş", "seksen", "doksan"]
GOAL_PROSODY = {"rate": "+10%", "pitch": "+6%"}  # goals only: a little faster and higher, still the same neutral voice


def tr_words(n: int) -> str:
    """0-999 as Turkish words: 23 -> "yirmi üç", 105 -> "yüz beş"."""
    if n == 0:
        return "sıfır"
    hundreds, rest = divmod(n, 100)
    head = [] if not hundreds else ["yüz"] if hundreds == 1 else [f"{TR_ONES[hundreds]} yüz"]
    return " ".join(p for p in head + [TR_TENS[rest // 10], TR_ONES[rest % 10]] if p)


def ssml(text: str, lang: str, voice: str, goal: bool = False) -> str:
    body = escape(text)
    if lang == "tr":
        body = TR_INTEGER.sub(lambda m: f'<sub alias="{tr_words(int(m.group()))}">{m.group()}</sub>', body)
    for name, alias in ALIASES[lang].items():
        body = body.replace(name, f'<sub alias="{escape(alias)}">{name}</sub>')
    if goal:
        body = f'<prosody rate="{GOAL_PROSODY["rate"]}" pitch="{GOAL_PROSODY["pitch"]}">{body}</prosody>'
    return (f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="{LOCALE[lang]}">'
            f'<voice name="{voice}">{body}</voice></speak>')


def clip_name(text: str, voice: str, goal: bool = False) -> str:
    key = f"{voice}|{text}" + ("|goal" if goal else "") + f"|ssml{SSML_VERSION}"
    return f"{hashlib.sha256(key.encode()).hexdigest()[:32]}.mp3"


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

    def synthesize(self, text: str, lang: str, goal: bool = False) -> bytes | None:
        voice = self.voices[lang]
        path = self.cache_dir / clip_name(text, voice, goal)
        if path.exists():
            return path.read_bytes()
        try:
            result = self.synth.speak_ssml_async(ssml(text, lang, voice, goal)).get()
        except Exception:
            return None
        if result.reason != self.sdk.ResultReason.SynthesizingAudioCompleted:
            return None
        self.characters += len(text)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path.write_bytes(result.audio_data)
        return result.audio_data
