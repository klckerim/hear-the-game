"""Azure AI Speech text-to-speech: MP3 bytes, cached on disk by (text, voice, style).

Two voices per language: the narration voice (`SPEECH_VOICE_EN` / `_TR`) and the male commentary voice for callouts and live lines
(`SPEECH_VOICE_COMMENTARY_EN` / `_TR`, MAI-Voice, public preview). A commentary clip that fails is retried once with
`SPEECH_VOICE_COMMENTARY_FALLBACK_EN` / `_TR`, keeping the style only where that voice has it.
"""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from xml.sax.saxutils import escape

from htg import telemetry

CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "cache" / "audio"
COMMENTARY_VOICES = {"en": "en-US-Ethan:MAI-Voice-2.1-Flash", "tr": "tr-TR-Aydın:MAI-Voice-2-Flash"}  # dotted "ı": copy, never normalise
COMMENTARY_FALLBACK = {"en": "en-US-GuyNeural", "tr": "tr-TR-AhmetNeural"}
# Styles of the non-MAI voices we may fall back to (MAI-Voice: every style the commentary uses). Others are spoken without a style.
NEURAL_STYLES = {"en-US-GuyNeural": {"excited", "shouting"}}
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


def commentary_voices() -> tuple[dict[str, str], dict[str, str]]:
    """(primary, fallback) commentary voice per language, from the environment; switching voices is a config change."""
    env = os.environ.get
    return ({lang: env(f"SPEECH_VOICE_COMMENTARY_{lang.upper()}") or v for lang, v in COMMENTARY_VOICES.items()},
            {lang: env(f"SPEECH_VOICE_COMMENTARY_FALLBACK_{lang.upper()}") or v for lang, v in COMMENTARY_FALLBACK.items()})


def style_for(voice: str, style: str | None) -> str | None:
    """The style to ask `voice` for: MAI-Voice takes every style, a neural voice only the ones it has; else None (plain voice)."""
    if ":MAI-Voice" in voice:
        return style
    return style if style in NEURAL_STYLES.get(voice, ()) else None


def ssml(text: str, lang: str, voice: str, goal: bool = False, style: str | None = None) -> str:
    body = escape(text)
    if lang == "tr":
        body = TR_INTEGER.sub(lambda m: f'<sub alias="{tr_words(int(m.group()))}">{m.group()}</sub>', body)
    for name, alias in ALIASES[lang].items():
        body = body.replace(name, f'<sub alias="{escape(alias)}">{name}</sub>')
    if goal:
        body = f'<prosody rate="{GOAL_PROSODY["rate"]}" pitch="{GOAL_PROSODY["pitch"]}">{body}</prosody>'
    if style:
        body = f'<mstts:express-as style="{style}">{body}</mstts:express-as>'
    return (f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xmlns:mstts="http://www.w3.org/2001/mstts" '
            f'xml:lang="{voice[:5]}"><voice name="{voice}">{body}</voice></speak>')  # the voice's own locale: en-GB Sonia, en-US Ethan


def clip_name(text: str, voice: str, goal: bool = False, style: str | None = None) -> str:
    key = f"{voice}|{text}" + ("|goal" if goal else "") + (f"|{style}" if style else "") + f"|ssml{SSML_VERSION}"
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
        self.commentary, self.commentary_fallback = commentary_voices()
        self.characters = 0  # sent to TTS this run (cache hits excluded)
        self.fallbacks = 0  # commentary clips that needed the fallback voice

    def synthesize(self, text: str, lang: str, goal: bool = False, voice: str | None = None, style: str | None = None) -> bytes | None:
        voice = voice or self.voices[lang]
        style = style_for(voice, style)
        path = self.cache_dir / clip_name(text, voice, goal, style)
        if path.exists():
            return path.read_bytes()
        try:
            result = self.synth.speak_ssml_async(ssml(text, lang, voice, goal, style)).get()
        except Exception:
            return None
        if result.reason != self.sdk.ResultReason.SynthesizingAudioCompleted:
            return None
        self.characters += len(text)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path.write_bytes(result.audio_data)
        return result.audio_data

    def commentate(self, text: str, lang: str, style: str | None = None) -> bytes | None:
        """A line in the commentary voice; on a synthesis error (e.g. an unknown voice) once more with the fallback voice."""
        audio = self.synthesize(text, lang, voice=self.commentary[lang], style=style)
        if audio is None:
            telemetry.voice_fallback.add(1, {"lang": lang})
            self.fallbacks += 1
            audio = self.synthesize(text, lang, voice=self.commentary_fallback[lang], style=style)
        return audio
