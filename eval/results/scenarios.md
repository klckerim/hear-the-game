# Scenario detection, seeds 11-30 (20 matches)

| Scenario | Insight | Scenarios | Recall | Insights | Precision | Median delay (s) |
|---|---|---|---|---|---|---|
| press_increase | pressure_shift | 20 | 17/20 (85%) | 58 | 21/58 (36%) | 264 |
| tempo_drop | tempo_change | 20 | 17/20 (85%) | 37 | 25/37 (68%) | 283 |
| flank_overload | flank_overload | 20 | 8/20 (40%) | 84 | 9/84 (11%) | 336 |
| fatigue | physical_drop | 20 | 19/20 (95%) | 40 | 24/40 (60%) | 589 |

Other insights per match: chance 37.6, goal 2.4.

True positive: same type and team (and player), Insight time in [start, end + 120 s]. Recall and delay per scenario, precision per Insight.
