# Day-0 sound prototype

Proof that the sound design works before the real pipeline existed. Kept for reference; the live client in `web/` replaces it.

* `generate_match.py` writes a hand-scripted 60-second excerpt to `data/match.json`.
* `render_audio.py tr|en|key` renders it offline to `out/*.mp3` (needs `ffmpeg` and `espeak-ng`; the robotic voice is a placeholder for Azure neural TTS).
* `web/template.html` is the browser version: the same sounds synthesized live with the Web Audio API. Build it with the data embedded:

```bash
python -c "import json;d=json.load(open('data/match.json'));t=open('web/template.html').read();open('web/hear-the-game.html','w').write(t.replace('__DATA__',json.dumps(d,ensure_ascii=False)))"
```
