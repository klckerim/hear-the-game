# Submission drafts (Inside the Game hackathon)

Submitted on 2026-10-27 (Innovation Studio project page). This file is the record of the submitted texts.

Draft texts for the submission form. Every number comes from `README.md` or `eval/results/`. Sentences marked `<!-- UI -->`
describe the screen layout and may change if the start screen changes.

## Links
- Live demo: https://ca-engine.proudflower-32a91b05.swedencentral.azurecontainerapps.io/
- Demo video: https://www.youtube.com/watch?v=Ezog8P1DRto
- Code: https://github.com/klckerim/hear-the-game

## Project name
Hear the Game

## Tagline (one line)
Follow a football match by sound: spatial audio made on your device, plus live commentary that only says what the data supports.

## Elevator pitch (~100 words)
Live audio description of football depends on trained human describers, so blind and partially sighted fans get it for few matches
and few languages. Hear the Game turns a live stream of match events into spatial sound synthesised on the listener's own device
(danger as pitch, the flank as left/right, pressure as a heartbeat) and adds short spoken commentary in English or Turkish.
Microsoft Foundry writes every sentence from facts computed in code, a deterministic Verifier rejects any number or name that is
not in those facts, and Azure AI Speech (including MAI-Voice) speaks it. It runs on Azure Container Apps, traced in Application
Insights.

## Description (~300 words)
A score app tells a blind fan the result, not the shape of the game: who is pressing, which wing is being attacked, whether a player
is tiring. Hear the Game gives that shape back by ear, in real time.

**Sound first.** The server sends small state packets; the browser makes all match sound itself with Web Audio. A ball tick rises
in pitch with danger (an Expected Threat model) and moves left or right with the flank; a heartbeat follows pressure on the ball;
passes, shots, saves, whistles and goals have their own sounds. The sound never waits for a model.

**Words second, and only verified ones.** Detectors find tactical stories (pressing surges, tempo drops, flank overloads, fatigue)
and compute every number. A Microsoft Foundry model (gpt-5-mini) turns those facts into one radio-style sentence in English and
Turkish; a plain-Python Verifier rejects any number, name or invented detail outside the facts, and a template sentence takes over
when the model fails twice. In the fan modes a live commentator adds 0-2 lines per stretch of play inside a 20 s broadcast delay
(p50 2.71 s from the end of the play), and short callouts name the players. A Foundry Agent Service prompt agent with four function
tools answers "Catch me up" with 2-3 verified sentences.

**Measured, not claimed.** Detectors are tuned on seeds 1-10 and reported on seeds 11-30 against hidden scenarios (pressing recall
85%, precision 36%; the flank detector's 11% precision is stated, not hidden). Narration passed the Verifier on the first draft for
100% of 100 Insights in both languages at p50 1.58 s; Foundry's groundedness evaluator scored the shipping prompt 4.66-4.92 of 5. With commentator and
callouts, 97% of 30-second windows contain speech, against 21% for tactical narration alone.

Everything runs on synthetic data: six fictional clubs, six matches, calibrated on real open data. Listeners pick a match, watch it
live from any minute or as highlights, in English or Turkish. The app opens in a listening view built for screen readers, with
the pitch and data one tap away. The author tried it with VoiceOver on one iPhone; it has not been validated with blind users.

## Category: Best Use of Microsoft Foundry
Foundry is the part of the system that writes words, and it is used where an LLM earns its place and nowhere else: one model call per
tactical Insight, one per stretch of live play, and one Foundry Agent Service prompt agent whose job is choosing which match tools
to call for a recap. Every model sentence is grounded in computed facts and passes a deterministic Verifier before it is spoken,
and the results are measured with Foundry evaluations (groundedness 4.72 / 4.66 EN / TR for the fan persona, 4.92 / 4.92 for the analyst) and traced in Application Insights through
Foundry tracing (`htg.narrate_insight` and `htg.recap` spans with the Verifier's attempts and reasons). Setting the reasoning effort
to `minimal` cut narration latency on the same prompt from p50 10.73 s to 1.87 s, which is what made live narration possible.

## Testing instructions for judges
1. Open https://ca-engine.proudflower-32a91b05.swedencentral.azurecontainerapps.io/ in a desktop or phone browser. **Use headphones**: left/right position is part of the information.
   The app opens in the **listening view**, made for following the match without looking at the screen (VoiceOver works). <!-- UI -->
2. Optional: take the 60-second sound tour offered on the first visit; it plays each sound with a short spoken explanation.
3. Press **Start listening** (or Space), or tap a match in the list to start it. The default match is Northport v Valemont from
   kick-off; the first goal comes at 23'. The commentator starts after the 20 s broadcast delay fills. <!-- UI -->
4. Try **Next moment** (or N) to jump to 30 s before the next goal, saved shot or card. <!-- UI -->
5. Switch **Live** to **Highlights** and press Start: every moment of the match back to back (about 12 minutes for the default
   match), with a half-time and a full-time recap. <!-- UI -->
6. Press **Catch me up** for a recap of the last 10 minutes from the Recap agent. <!-- UI -->
7. The listening view speaks the device's language (English or Turkish); `?lang=tr` opens Turkish. The desk (next step) has the
   language switch in its header: screen and commentary change together. <!-- UI -->
8. Press **Show the pitch & data** to open the broadcast desk; it is the same session, so the sound keeps playing. There, switch the
   listening mode: **Audio only** (pitch hidden), **Casual** (live commentary feed), **Analyst** (no delay, no commentator; sparse
   tactical notes plus team stats and an event log on screen), and select a marker on the timeline. <!-- UI -->
9. Select a played Insight on the timeline to see **Why?**: the facts the sentence rests on and its evidence on the pitch. <!-- UI -->

Session limits: one listener session per browser tab, at most 4 at once from one network address and 20 per server replica. A hidden tab stops listening 2 minutes after the
browser suspends its audio (and after 45 minutes hidden even if the sound plays); Start picks up where it stopped.

## Technologies
- Microsoft Foundry: gpt-5-mini deployment (narrator, live commentator), Foundry Agent Service (Recap agent, Responses API),
  Foundry evaluations (groundedness, fluency), Foundry tracing
- Azure AI Speech: neural voices (en-GB, tr-TR) with SSML; MAI-Voice-2.1 / MAI-Voice-2 with speaking styles for commentary and
  callouts
- Azure Container Apps, Azure Container Registry, managed identity, Application Insights + Log Analytics (OpenTelemetry)
- Azure Developer CLI (azd) + Bicep, GitHub Actions
- Python 3.11+ (engine, detectors, Director, Verifier), WebSocket; vanilla JavaScript + Web Audio client, no build step
