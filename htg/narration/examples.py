"""Hand-written few-shot examples for the narrator: one per Insight kind, EN and TR, numbers from a fixed fixture.

The fixture teams (Greens, Whites) and players never appear in a generated match, so the model cannot copy a name or number
into a real sentence without the Verifier catching it. A test checks every example passes the Verifier against its own facts.
"""
from __future__ import annotations

TEAMS = {"team_en": "the Greens", "team_tr": "Yeşiller", "opponent_en": "the Whites", "opponent_tr": "Beyazlar"}
NAMES = ["the Greens", "Yeşiller", "the Whites", "Beyazlar", "Varga", "Duran"]

EXAMPLES: dict[str, dict] = {
    "pressure_shift": {
        "facts": {**TEAMS, "share_now_pct": 41, "share_before_pct": 24, "recent_min": 5},
        "en": "The Greens press harder: 41% of the Whites' play is under pressure in the last 5 minutes, 24% earlier.",
        "tr": ("Yeşiller baskıyı artırdı: son 5 dakikada Beyazlar'ın hareketlerinin yüzde 41'i baskı altında, "
               "maçın önceki bölümünde yüzde 24'tü."),
    },
    "tempo_change": {
        "facts": {**TEAMS, "gap_now_s": 2.3, "gap_before_s": 1.5, "slower_pct": 53, "recent_min": 7},
        "en": "The Greens are slowing it down: about 2.3 seconds on every touch in the last 7 minutes, 1.5 earlier.",
        "tr": "Yeşiller oyunu soğutuyor: son 7 dakikada her dokunuşta yaklaşık 2,3 saniye, maçın önceki bölümünde 1,5 saniyeydi.",
    },
    "flank_overload": {
        "facts": {**TEAMS, "side": "right", "side_tr": "sağ", "share_now_pct": 58, "share_before_pct": 27, "recent_min": 8},
        "en": "The Greens keep going down the right: 58% of their passes end there in the last 8 minutes, 27% earlier.",
        "tr": "Yeşiller sağ kanada yükleniyor: son 8 dakikada paslarının yüzde 58'i orada bitiyor, önceki bölümde yüzde 27'ydi.",
    },
    "physical_drop": {
        "facts": {**TEAMS, "player": "Varga", "hsr_now_pct": 45, "recent_min": 8},
        "en": "Varga is tiring for the Greens: high-speed running over the last 8 minutes is down to 45% of earlier.",
        "tr": "Yeşiller'de Varga yoruluyor: son 8 dakikadaki yüksek tempolu koşuları, maçın önceki bölümünün yüzde 45'i kadar.",
    },
    "goal": {
        "facts": {**TEAMS, "player": "Duran", "home_score": 2, "away_score": 1},
        "en": "Goal! Duran scores for the Greens, and it's 2-1!",
        "tr": "Gol! Duran Yeşiller için ağları sarsıyor, skor 2-1!",
    },
    "chance:shot": {
        "facts": {**TEAMS, "source": "shot", "player": "Varga", "outcome": "saved"},
        "en": "Chance for the Greens, Varga shoots, and the keeper saves!",
        "tr": "Yeşiller için fırsat: Varga vuruyor, kaleci çıkarıyor!",
    },
    "chance:danger": {
        "facts": {**TEAMS, "source": "danger"},
        "en": "The Greens are bearing down on goal!",
        "tr": "Yeşiller kaleye yaklaşıyor, tehlikeli geliyorlar!",
    },
}


def example_for(insight: dict) -> dict | None:
    """The example for this Insight's kind (chance is split by its source), or None for a kind without one."""
    ty = insight["type"]
    return EXAMPLES.get(f"{ty}:{insight['claim_facts'].get('source')}" if ty == "chance" else ty)
