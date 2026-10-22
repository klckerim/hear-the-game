"""Callouts: short pre-generated clips in the commentary voice that the client strings together ("Okafor... shot... saved!").

    HTG_ENV=azure python -m htg.speech.callouts

Writes `data/cache/callouts/<lang>_<tone>_<id>.mp3` for every word, club and squad surname, in two tones (normal = `neutral`,
excited = `excited`), and `callouts.json`: {"voices": {lang: voice}, "clips": {lang: {tone: {key: file}}}}. A key is a word id
("shot", "yellow_card"), a club name or a player name, exactly as the client gets them in `hello`. No LLM: the words are fixed.
"""
from __future__ import annotations

import json
import tempfile
import unicodedata
from pathlib import Path

from htg.env import load_env
from htg.generate import SQUADS

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "cache" / "callouts"
LANGS = ("en", "tr")
TONES = {"normal": "neutral", "excited": "excited"}  # tone -> voice style
WORDS = {
    "shot": {"en": "Shot", "tr": "Şut"},
    "saved": {"en": "Saved", "tr": "Kurtardı"},
    "goal": {"en": "Goal", "tr": "Gol"},
    "foul": {"en": "Foul", "tr": "Faul"},
    "yellow_card": {"en": "Yellow card", "tr": "Sarı kart"},
    "red_card": {"en": "Red card", "tr": "Kırmızı kart"},
    "corner": {"en": "Corner", "tr": "Korner"},
    "free_kick": {"en": "Free kick", "tr": "Serbest vuruş"},
    "throw_in": {"en": "Throw-in", "tr": "Taç"},
    "goal_kick": {"en": "Goal kick", "tr": "Aut"},
    "out": {"en": "Out", "tr": "Dışarıda"},
    "blocked": {"en": "Blocked", "tr": "Bloke edildi"},
    "wide": {"en": "Wide", "tr": "Az farkla dışarı"},
}


def slug(text: str) -> str:
    """"Şahin" -> "sahin", "Yıldız" -> "yildiz": ASCII file names (the dotless ı has no decomposition, so it is mapped by hand)."""
    ascii_ = unicodedata.normalize("NFKD", text.replace("ı", "i")).encode("ascii", "ignore").decode()
    return "".join(c if c.isalnum() else "_" for c in ascii_.lower())


def items() -> list[tuple[str, str, dict[str, str]]]:
    """(key, file id, text per language) for every clip: words, then club names, then surnames (names are said as they are)."""
    out = [(k, k, v) for k, v in WORDS.items()]
    out += [(s["name"]["en"], "c_" + slug(s["name"]["en"]), s["name"]) for s in SQUADS.values()]
    out += [(n, "p_" + slug(n), {"en": n, "tr": n}) for s in SQUADS.values() for n in s["players"]]
    return out


def spoken(text: str, tone: str) -> str:
    return text + ("!" if tone == "excited" else ".")


def main() -> None:
    load_env()
    from htg.speech.azure import AzureSpeech

    OUT.mkdir(parents=True, exist_ok=True)
    clips: dict[str, dict[str, dict[str, str]]] = {lang: {tone: {} for tone in TONES} for lang in LANGS}
    with tempfile.TemporaryDirectory() as tmp:
        speech = AzureSpeech(cache_dir=Path(tmp))  # callout clips live in their own folder, not in the narration clip cache
        print(f"commentary voices: {speech.commentary} (fallback {speech.commentary_fallback})")
        for key, fid, text in items():
            for lang in LANGS:
                for tone, style in TONES.items():
                    name = f"{lang}_{tone}_{fid}.mp3"
                    audio = speech.commentate(spoken(text[lang], tone), lang, style)
                    if audio is None:
                        raise SystemExit(f"TTS failed for {name}")
                    (OUT / name).write_bytes(audio)
                    clips[lang][tone][key] = name
    wanted = {n for lang in clips.values() for tone in lang.values() for n in tone.values()}
    for old in OUT.glob("*.mp3"):
        if old.name not in wanted:
            old.unlink()
    (OUT / "callouts.json").write_text(json.dumps({"voices": speech.commentary, "clips": clips}, ensure_ascii=False, indent=1) + "\n")
    kb = sum((OUT / n).stat().st_size for n in wanted) // 1024
    print(f"{len(wanted)} clips in {OUT.relative_to(ROOT)}, {kb} KB, {speech.characters} characters sent to TTS, "
          f"{speech.fallbacks} with the fallback voice")


if __name__ == "__main__":
    main()
