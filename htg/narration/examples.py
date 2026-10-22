"""Hand-written few-shot examples for the narrator: one per Insight kind and persona, EN and TR, numbers from a fixed fixture.

The fixture clubs (Eastbrook, Westmere) and players never appear in a generated match, so the model cannot copy a name or number
into a real sentence without the Verifier catching it. A test checks every example passes the Verifier against its own facts.
`fan` sentences carry at most one number (the score of a goal counts as one) and say the trend in words; `analyst` sentences
give the key numbers and the comparison with earlier.
"""
from __future__ import annotations

# Club names, not colours: "the Greens are pressing ... the Whites are feeling it" tripped Azure's content filter on the prompt.
TEAMS = {"team_en": "Eastbrook", "team_tr": "Eastbrook", "opponent_en": "Westmere", "opponent_tr": "Westmere"}
NAMES = ["Eastbrook", "Westmere", "Varga", "Duran"]

EXAMPLES: dict[str, dict] = {
    "pressure_shift": {
        "facts": {**TEAMS, "share_now_pct": 41, "share_before_pct": 24, "recent_min": 5},
        "fan": {"en": "Eastbrook are pressing much harder now, and Westmere are under real pressure!",
                "tr": "Eastbrook baskının dozunu artırdı, Westmere artık çok daha fazla baskı altında!"},
        "analyst": {"en": "Eastbrook press harder: 41% of Westmere's play is under pressure in the last 5 minutes, 24% earlier.",
                    "tr": "Eastbrook baskıyı artırdı: son 5 dakikada Westmere için baskı oranı yüzde 41, maçın önceki bölümünde yüzde 24."},
    },
    "tempo_change": {
        "facts": {**TEAMS, "gap_now_s": 2.3, "gap_before_s": 1.5, "slower_pct": 53, "recent_min": 7},
        "fan": {"en": "Eastbrook are taking the sting out of it, slowing everything right down.",
                "tr": "Eastbrook oyunu iyice soğutuyor, topu ağır ağır çeviriyorlar."},
        "analyst": {"en": "Eastbrook are slowing it down: about 2.3 seconds on every touch in the last 7 minutes, 1.5 earlier.",
                    "tr": (
                        "Eastbrook oyunu soğutuyor: son 7 dakikada her dokunuşta yaklaşık 2,3 saniye, maçın önceki bölümünde 1,5 saniye.")},
    },
    "flank_overload": {
        "facts": {**TEAMS, "side": "right", "side_tr": "sağ", "share_now_pct": 58, "share_before_pct": 27, "recent_min": 8},
        "fan": {"en": "Eastbrook keep pouring forward down the right now!",
                "tr": "Eastbrook ısrarla sağ kanattan yükleniyor!"},
        "analyst": {"en": "Eastbrook keep going down the right: 58% of their passes end there in the last 8 minutes, 27% earlier.",
                    "tr": "Eastbrook sağ kanada yükleniyor: son 8 dakikada pasların yüzde 58 kadarı orada bitiyor, önceden yüzde 27."},
    },
    "physical_drop": {
        "facts": {**TEAMS, "player": "Varga", "hsr_now_pct": 45, "recent_min": 8},
        "fan": {"en": "Varga is tiring for Eastbrook, far fewer of those quick runs now.",
                "tr": "Eastbrook'ta Varga yoruluyor, o hızlı koşular artık çok daha seyrek."},
        "analyst": {"en": "Varga is tiring for Eastbrook: high-speed running over the last 8 minutes is down to 45% of earlier.",
                    "tr": (
                        "Eastbrook'ta Varga yoruluyor: son 8 dakikadaki yüksek tempolu koşuları, maçın önceki bölümünün yüzde 45 kadarı.")},
    },
    "goal": {
        "facts": {"team_en": "Eastbrook", "team_tr": "Eastbrook", "player": "Duran", "home_score": 2, "away_score": 1},
        "fan": {"en": "Goal! Duran scores for Eastbrook, and it's 2-1!",
                "tr": "Gol! Duran Eastbrook için ağları sarsıyor, skor 2-1!"},
        "analyst": {"en": "Goal for Eastbrook, scored by Duran; the score is now 2-1.",
                    "tr": "Eastbrook golü buldu, golü atan Duran; skor şimdi 2-1."},
    },
    "chance:shot": {
        "facts": {**TEAMS, "source": "shot", "player": "Varga", "outcome": "saved"},
        "fan": {"en": "Chance for Eastbrook! Varga shoots, and the keeper saves!",
                "tr": "Eastbrook için fırsat! Varga vuruyor, kaleci çıkarıyor!"},
        "analyst": {"en": "Shot from Varga for Eastbrook, saved by the keeper.",
                    "tr": "Eastbrook adına Varga şutunu çekiyor, kaleci kurtarıyor."},
    },
    "chance:danger": {
        "facts": {**TEAMS, "source": "danger"},
        "fan": {"en": "Eastbrook are bearing down on goal!", "tr": "Eastbrook kaleye yaklaşıyor, tehlikeli geliyorlar!"},
        "analyst": {"en": "Eastbrook have the ball close to Westmere's goal.", "tr": "Eastbrook top rakip kaleye yakınken oyunu kuruyor."},
    },
}


def example_for(insight: dict, persona: str = "fan") -> dict | None:
    """{"facts", "en", "tr"}: the example for this Insight's kind (chance is split by its source) and persona, or None."""
    ty = insight["type"]
    ex = EXAMPLES.get(f"{ty}:{insight['claim_facts'].get('source')}" if ty == "chance" else ty)
    return {"facts": ex["facts"], **ex[persona]} if ex else None
