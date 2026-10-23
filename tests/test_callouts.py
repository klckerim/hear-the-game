from htg.league import CLUBS
from htg.speech.callouts import LANGS, WORDS, items, slug, spoken


def test_every_word_club_and_surname_has_one_ascii_clip_id():
    rows = items()
    keys, ids = [k for k, _, _ in rows], [f for _, f, _ in rows]
    assert len(set(keys)) == len(keys) and len(set(ids)) == len(ids)
    assert set(WORDS) | {c["name"] for c in CLUBS.values()} | {n for c in CLUBS.values() for n in c["players"]} == set(keys)
    assert all(f.isascii() and f.replace("_", "").isalnum() for f in ids)
    assert all(text[lang] for _, _, text in rows for lang in LANGS)
    assert (slug("Şahin"), slug("Yıldız"), slug("Throw-in")) == ("sahin", "yildiz", "throw_in")
    assert (spoken("Gol", "excited"), spoken("Taç", "normal")) == ("Gol!", "Taç.")
