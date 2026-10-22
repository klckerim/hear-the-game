# Listening test

A small, honest check: can someone follow a match by ear alone? This is not a user study. Report n and the answers as they
are; do not generalise from them.

**Status: not run yet.** (Replace this line with the date and n when it has happened.)

## Setup

- 1-3 participants, one at a time. Headphones (stereo matters: the wing is the left/right ear).
- Seed 7 from minute 13, run locally: `HTG_ENV=azure python -m services.engine.run_local --seed 7 --start-minute 13`, then open
  `web/live.html` (the deployed chapters start at 0', 19' and 76', not 13'; narration between 15' and 19' is not in the demo cache and is
  written live).
  Mode **casual**, language the participant's choice (TR or EN). Screen hidden or turned away.
- Listen for **10 minutes** (match minutes 13-23). The task said 5 minutes, but the demo's goal comes at 22:36, about
  9.5 minutes in; with 5 minutes the goal question has no answer.
- Say only this before starting (one sentence):
  - TR: "Bu bir futbol maçının sesi; Northport ve Valemont oynuyor, sadece dinle ve sonra birkaç soru soracağım."
  - EN: "This is the sound of a football match between Northport and Valemont; just listen, and I will ask a few questions after."
- Do not explain the sound mapping. Whether it is understood without explanation is part of what we learn.
- Write answers down in the participant's words. Ask for permission before quoting.

## Questions (after listening, in this order)

| # | TR | EN |
|---|---|---|
| 1 | Hangi takım daha çok hücum etti? | Which team attacked more? |
| 2 | Hücumlar daha çok hangi taraftan geldi (sol / sağ / orta)? | Which side did the attacks mostly come from (left / right / middle)? |
| 3 | Gol oldu mu? Olduysa kim, hangi takım için attı? | Was there a goal? If so, who scored, for which team? |
| 4 | Taktik olarak bir şey değişti mi? | Did anything change tactically? |
| 5 | Anlatım: çok fazla / çok az / tam kararında? | Narration: too much / too little / about right? |
| 6 | Ses yorucu muydu? | Was the sound tiring? |
| 7 | (serbest) En çok ne yardımcı oldu, ne kafa karıştırdı? | (open) What helped most, what was confusing? |

## What actually happened (answer key, from the match data)

Computed from `data/synthetic/match_0007/events.jsonl` and the narration the Director spoke in casual mode
(not from `truth.json`). Minutes 13:00-23:00.

| # | Answer |
|---|---|
| 1 | Depends on the stretch. Minutes 13-18: **Northport** (51 vs 33 on-ball actions, 12 vs 8 passes into the final third). Over the full 10 minutes: **Valemont** (115 vs 80 on-ball actions, 24 vs 18 final-third passes), and they scored. Either answer with a reason counts; note which. |
| 2 | Both teams mostly down **their right** flank, which the listener hears in the **right ear** (the pan is the attacker's left/right). Passes ending in the attacking half: Valemont 22 right / 11 centre / 9 left; Northport 19 right / 17 centre / 1 left. Narrated at 14' (Valemont, right) and 17' (Northport, right). |
| 3 | **Yes. Baptiste, for Valemont, at 22:36. 0-1.** |
| 4 | Narrated: Northport slowed the game down (13' and 21'), and Polat (Northport) was tiring (20'). Shots: Northport 2 (both blocked), Valemont 1 off target plus the goal. |
| 5-7 | No answer key: opinion. |

## Results

| Participant | Self-described sight | Language | Q1 | Q2 | Q3 | Q4 | Q5 | Q6 | Quote (with permission) |
|---|---|---|---|---|---|---|---|---|---|
| P1 | sighted / low vision / blind | | | | | | | | |
| P2 | | | | | | | | | |
| P3 | | | | | | | | | |

No names. Self-described: sighted, low vision or blind, in the participant's own words.

## How to report it

- In the README: n, how many participants were blind or low vision, and the results per question against the answer key.
  For example: "2 of 3 named the scorer; 1 of 3 placed the attacks on the right."
- If no blind or low-vision participant took part, say so plainly: "tested with sighted listeners with the screen hidden;
  not validated with blind users."
- A participant from a local association for blind and partially sighted people is worth more than anything else here.
  Their answers are reported the same way, without claims beyond what they said.
