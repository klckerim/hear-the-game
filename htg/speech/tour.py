"""Voice lines of the sound tour: one Azure clip per step and language, from the table in `web/tour.json`.

    HTG_ENV=azure python -m htg.speech.tour                       # every step
    HTG_ENV=azure python -m htg.speech.tour --only teams goal     # only these steps; other clips are left alone

Writes `data/cache/tour/<id>_<lang>.mp3` (same voices as the narration). A full run deletes clips of steps that are gone.
"""
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from htg.env import load_env

ROOT = Path(__file__).resolve().parents[2]
TABLE = ROOT / "web" / "tour.json"
OUT = ROOT / "data" / "cache" / "tour"
LANGS = ("en", "tr")


def main(only: list[str] | None = None) -> None:
    load_env()
    from htg.speech.azure import AzureSpeech

    steps = json.loads(TABLE.read_text())["steps"]
    if only:
        unknown = set(only) - {s["id"] for s in steps}
        if unknown:
            raise SystemExit(f"unknown step(s): {', '.join(sorted(unknown))}")
        steps = [s for s in steps if s["id"] in only]
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        speech = AzureSpeech(cache_dir=Path(tmp))  # the tour clips live in their own folder, not in the narration clip cache
        wanted = set()
        for step in steps:
            for lang in LANGS:
                name = f"{step['id']}_{lang}.mp3"
                audio = speech.synthesize(step[lang], lang)
                if audio is None:
                    raise SystemExit(f"TTS failed for {name}")
                (OUT / name).write_bytes(audio)
                wanted.add(name)
    for old in OUT.glob("*.mp3") if not only else ():
        if old.name not in wanted:
            old.unlink()
    print(f"{len(wanted)} clips in {OUT.relative_to(ROOT)}, {sum((OUT / n).stat().st_size for n in wanted) // 1024} KB")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", nargs="+", help="step ids to regenerate")
    main(ap.parse_args().only)
