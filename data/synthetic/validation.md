# Synthetic data validation

30 synthetic matches vs. calibration source data (StatsBomb Open Data, Premier League 2015/16, 40 matches; SkillCorner Open Data, A-League 2024/25 broadcast tracking, 3 matches).

## Per match

| Metric | Real | Synthetic | Ratio |
|---|---|---|---|
| passes | 982.6 | 879.2 | 0.89 |
| carries | 609.0 | 546.5 | 0.90 |
| shots | 25.4 | 26.3 | 1.03 |
| goals | 2.6 | 2.5 | 0.93 |

## Distributions

KS statistic: 0 = identical distributions, below ~0.1 = close.

| Metric | Real median | Synthetic median | KS |
|---|---|---|---|
| Pass length (m) | 15.14 | 16.13 | 0.049 |
| Time between on-ball actions (s) | 1.40 | 1.61 | 0.100 |
| Moving ball speed (m/s) | 5.86 | 6.83 | 0.180 |

Action location along the pitch (12 bands): correlation real vs synthetic = 0.944

## Hidden scenarios leave a measurable trace

Inside = during the scenario window, outside = rest of the match.

| Match | Scenario | Team | Statistic | Inside | Outside | Change |
|---|---|---|---|---|---|---|
| match_0001 | S1 press_increase | AWAY | share of opponent actions under pressure | 0.450 | 0.230 | +95% |
| match_0001 | S2 flank_overload | AWAY | share of passes to the right flank | 0.804 | 0.378 | +113% |
| match_0001 | S3 tempo_drop | AWAY | median seconds between own actions | 2.470 | 1.660 | +49% |
| match_0001 | S4 fatigue | AWAY | high-speed running metres per minute | 3.064 | 6.003 | -49% |
| match_0002 | S1 press_increase | HOME | share of opponent actions under pressure | 0.414 | 0.232 | +78% |
| match_0002 | S2 flank_overload | HOME | share of passes to the left flank | 0.784 | 0.420 | +87% |
| match_0002 | S3 tempo_drop | HOME | median seconds between own actions | 3.430 | 1.560 | +120% |
| match_0002 | S4 fatigue | AWAY | high-speed running metres per minute | 3.067 | 7.406 | -59% |
| match_0003 | S1 press_increase | HOME | share of opponent actions under pressure | 0.521 | 0.253 | +106% |
| match_0003 | S2 flank_overload | AWAY | share of passes to the left flank | 0.756 | 0.317 | +138% |
| match_0003 | S3 tempo_drop | AWAY | median seconds between own actions | 2.720 | 1.600 | +70% |
| match_0003 | S4 fatigue | HOME | high-speed running metres per minute | 2.644 | 6.028 | -56% |
| match_0004 | S1 press_increase | AWAY | share of opponent actions under pressure | 0.440 | 0.278 | +58% |
| match_0004 | S2 flank_overload | AWAY | share of passes to the right flank | 0.590 | 0.453 | +30% |
| match_0004 | S3 tempo_drop | HOME | median seconds between own actions | 2.630 | 1.490 | +77% |
| match_0004 | S4 fatigue | HOME | high-speed running metres per minute | 2.257 | 6.496 | -65% |
| match_0005 | S1 press_increase | HOME | share of opponent actions under pressure | 0.493 | 0.249 | +98% |
| match_0005 | S2 flank_overload | AWAY | share of passes to the right flank | 0.810 | 0.410 | +97% |
| match_0005 | S3 tempo_drop | HOME | median seconds between own actions | 2.690 | 1.490 | +81% |
| match_0005 | S4 fatigue | HOME | high-speed running metres per minute | 2.706 | 5.806 | -53% |
| match_0006 | S1 press_increase | AWAY | share of opponent actions under pressure | 0.432 | 0.236 | +84% |
| match_0006 | S2 flank_overload | AWAY | share of passes to the left flank | 0.796 | 0.364 | +119% |
| match_0006 | S3 tempo_drop | HOME | median seconds between own actions | 2.570 | 1.725 | +49% |
| match_0006 | S4 fatigue | HOME | high-speed running metres per minute | 2.294 | 5.912 | -61% |
| match_0007 | S1 press_increase | AWAY | share of opponent actions under pressure | 0.329 | 0.270 | +22% |
| match_0007 | S2 flank_overload | AWAY | share of passes to the right flank | 0.800 | 0.362 | +121% |
| match_0007 | S3 tempo_drop | HOME | median seconds between own actions | 2.375 | 1.640 | +45% |
| match_0007 | S4 fatigue | HOME | high-speed running metres per minute | 3.341 | 7.695 | -57% |
| match_0008 | S1 press_increase | HOME | share of opponent actions under pressure | 0.471 | 0.265 | +78% |
| match_0008 | S2 flank_overload | AWAY | share of passes to the right flank | 0.697 | 0.315 | +121% |
| match_0008 | S3 tempo_drop | AWAY | median seconds between own actions | 2.805 | 1.580 | +78% |
| match_0008 | S4 fatigue | HOME | high-speed running metres per minute | 2.478 | 6.664 | -63% |
| match_0009 | S1 press_increase | AWAY | share of opponent actions under pressure | 0.407 | 0.283 | +44% |
| match_0009 | S2 flank_overload | AWAY | share of passes to the left flank | 0.667 | 0.421 | +58% |
| match_0009 | S3 tempo_drop | AWAY | median seconds between own actions | 2.330 | 1.500 | +55% |
| match_0009 | S4 fatigue | AWAY | high-speed running metres per minute | 2.936 | 8.090 | -64% |
| match_0010 | S1 press_increase | HOME | share of opponent actions under pressure | 0.475 | 0.270 | +76% |
| match_0010 | S2 flank_overload | AWAY | share of passes to the left flank | 0.839 | 0.375 | +124% |
| match_0010 | S3 tempo_drop | HOME | median seconds between own actions | 3.025 | 1.450 | +109% |
| match_0010 | S4 fatigue | HOME | high-speed running metres per minute | 2.212 | 7.145 | -69% |
| match_0011 | S1 press_increase | AWAY | share of opponent actions under pressure | 0.542 | 0.264 | +105% |
| match_0011 | S2 flank_overload | AWAY | share of passes to the left flank | 0.697 | 0.427 | +63% |
| match_0011 | S3 tempo_drop | HOME | median seconds between own actions | 2.565 | 1.620 | +58% |
| match_0011 | S4 fatigue | HOME | high-speed running metres per minute | 3.295 | 7.578 | -57% |
| match_0012 | S1 press_increase | AWAY | share of opponent actions under pressure | 0.455 | 0.239 | +91% |
| match_0012 | S2 flank_overload | HOME | share of passes to the right flank | 0.714 | 0.328 | +118% |
| match_0012 | S3 tempo_drop | HOME | median seconds between own actions | 2.650 | 1.560 | +70% |
| match_0012 | S4 fatigue | HOME | high-speed running metres per minute | 3.194 | 7.383 | -57% |
| match_0013 | S1 press_increase | AWAY | share of opponent actions under pressure | 0.475 | 0.224 | +112% |
| match_0013 | S2 flank_overload | AWAY | share of passes to the right flank | 0.596 | 0.333 | +79% |
| match_0013 | S3 tempo_drop | HOME | median seconds between own actions | 2.610 | 1.480 | +76% |
| match_0013 | S4 fatigue | AWAY | high-speed running metres per minute | 2.181 | 7.083 | -69% |
| match_0014 | S1 press_increase | AWAY | share of opponent actions under pressure | 0.467 | 0.234 | +99% |
| match_0014 | S2 flank_overload | HOME | share of passes to the left flank | 0.766 | 0.395 | +94% |
| match_0014 | S3 tempo_drop | AWAY | median seconds between own actions | 2.300 | 1.420 | +62% |
| match_0014 | S4 fatigue | HOME | high-speed running metres per minute | 2.427 | 6.130 | -60% |
| match_0015 | S1 press_increase | AWAY | share of opponent actions under pressure | 0.494 | 0.247 | +100% |
| match_0015 | S2 flank_overload | HOME | share of passes to the right flank | 0.655 | 0.387 | +69% |
| match_0015 | S3 tempo_drop | HOME | median seconds between own actions | 2.390 | 1.660 | +44% |
| match_0015 | S4 fatigue | AWAY | high-speed running metres per minute | 2.700 | 7.084 | -62% |
| match_0016 | S1 press_increase | AWAY | share of opponent actions under pressure | 0.412 | 0.232 | +77% |
| match_0016 | S2 flank_overload | AWAY | share of passes to the left flank | 0.790 | 0.329 | +140% |
| match_0016 | S3 tempo_drop | HOME | median seconds between own actions | 2.720 | 1.500 | +81% |
| match_0016 | S4 fatigue | HOME | high-speed running metres per minute | 2.971 | 6.875 | -57% |
| match_0017 | S1 press_increase | HOME | share of opponent actions under pressure | 0.271 | 0.256 | +6% |
| match_0017 | S2 flank_overload | AWAY | share of passes to the left flank | 0.792 | 0.360 | +120% |
| match_0017 | S3 tempo_drop | HOME | median seconds between own actions | 2.845 | 1.570 | +81% |
| match_0017 | S4 fatigue | HOME | high-speed running metres per minute | 2.261 | 6.234 | -64% |
| match_0018 | S1 press_increase | HOME | share of opponent actions under pressure | 0.402 | 0.275 | +46% |
| match_0018 | S2 flank_overload | HOME | share of passes to the right flank | 0.649 | 0.382 | +70% |
| match_0018 | S3 tempo_drop | HOME | median seconds between own actions | 2.810 | 1.640 | +71% |
| match_0018 | S4 fatigue | AWAY | high-speed running metres per minute | 2.569 | 5.849 | -56% |
| match_0019 | S1 press_increase | HOME | share of opponent actions under pressure | 0.447 | 0.240 | +86% |
| match_0019 | S2 flank_overload | AWAY | share of passes to the right flank | 0.754 | 0.361 | +109% |
| match_0019 | S3 tempo_drop | HOME | median seconds between own actions | 2.365 | 1.490 | +59% |
| match_0019 | S4 fatigue | HOME | high-speed running metres per minute | 2.853 | 8.897 | -68% |
| match_0020 | S1 press_increase | HOME | share of opponent actions under pressure | 0.390 | 0.258 | +51% |
| match_0020 | S2 flank_overload | HOME | share of passes to the left flank | 0.702 | 0.353 | +99% |
| match_0020 | S3 tempo_drop | AWAY | median seconds between own actions | 2.320 | 1.590 | +46% |
| match_0020 | S4 fatigue | HOME | high-speed running metres per minute | 2.977 | 6.325 | -53% |
| match_0021 | S1 press_increase | HOME | share of opponent actions under pressure | 0.467 | 0.231 | +102% |
| match_0021 | S2 flank_overload | HOME | share of passes to the right flank | 0.818 | 0.342 | +139% |
| match_0021 | S3 tempo_drop | HOME | median seconds between own actions | 2.640 | 1.570 | +68% |
| match_0021 | S4 fatigue | AWAY | high-speed running metres per minute | 2.711 | 7.940 | -66% |
| match_0022 | S1 press_increase | AWAY | share of opponent actions under pressure | 0.534 | 0.258 | +107% |
| match_0022 | S2 flank_overload | HOME | share of passes to the left flank | 0.824 | 0.546 | +51% |
| match_0022 | S3 tempo_drop | AWAY | median seconds between own actions | 2.600 | 1.575 | +65% |
| match_0022 | S4 fatigue | HOME | high-speed running metres per minute | 2.971 | 7.665 | -61% |
| match_0023 | S1 press_increase | HOME | share of opponent actions under pressure | 0.384 | 0.232 | +65% |
| match_0023 | S2 flank_overload | AWAY | share of passes to the right flank | 0.333 | 0.333 | +0% |
| match_0023 | S3 tempo_drop | HOME | median seconds between own actions | 3.185 | 1.495 | +113% |
| match_0023 | S4 fatigue | AWAY | high-speed running metres per minute | 3.055 | 6.775 | -55% |
| match_0024 | S1 press_increase | AWAY | share of opponent actions under pressure | 0.478 | 0.277 | +72% |
| match_0024 | S2 flank_overload | HOME | share of passes to the left flank | 0.821 | 0.461 | +78% |
| match_0024 | S3 tempo_drop | AWAY | median seconds between own actions | 2.690 | 1.420 | +89% |
| match_0024 | S4 fatigue | AWAY | high-speed running metres per minute | 2.700 | 6.579 | -59% |
| match_0025 | S1 press_increase | AWAY | share of opponent actions under pressure | 0.441 | 0.226 | +95% |
| match_0025 | S2 flank_overload | AWAY | share of passes to the left flank | 0.714 | 0.424 | +69% |
| match_0025 | S3 tempo_drop | HOME | median seconds between own actions | 2.055 | 1.680 | +22% |
| match_0025 | S4 fatigue | AWAY | high-speed running metres per minute | 2.715 | 6.583 | -59% |
| match_0026 | S1 press_increase | AWAY | share of opponent actions under pressure | 0.422 | 0.255 | +65% |
| match_0026 | S2 flank_overload | HOME | share of passes to the left flank | 0.754 | 0.379 | +99% |
| match_0026 | S3 tempo_drop | AWAY | median seconds between own actions | 2.730 | 1.630 | +67% |
| match_0026 | S4 fatigue | HOME | high-speed running metres per minute | 2.263 | 6.222 | -64% |
| match_0027 | S1 press_increase | HOME | share of opponent actions under pressure | 0.465 | 0.236 | +97% |
| match_0027 | S2 flank_overload | AWAY | share of passes to the left flank | 0.787 | 0.450 | +75% |
| match_0027 | S3 tempo_drop | HOME | median seconds between own actions | 2.310 | 1.500 | +54% |
| match_0027 | S4 fatigue | HOME | high-speed running metres per minute | 2.795 | 8.149 | -66% |
| match_0028 | S1 press_increase | HOME | share of opponent actions under pressure | 0.438 | 0.233 | +88% |
| match_0028 | S2 flank_overload | AWAY | share of passes to the right flank | 0.641 | 0.342 | +87% |
| match_0028 | S3 tempo_drop | HOME | median seconds between own actions | 2.855 | 1.590 | +80% |
| match_0028 | S4 fatigue | AWAY | high-speed running metres per minute | 2.764 | 5.190 | -47% |
| match_0029 | S1 press_increase | AWAY | share of opponent actions under pressure | 0.438 | 0.268 | +63% |
| match_0029 | S2 flank_overload | AWAY | share of passes to the right flank | 0.738 | 0.354 | +109% |
| match_0029 | S3 tempo_drop | HOME | median seconds between own actions | 2.500 | 1.530 | +63% |
| match_0029 | S4 fatigue | AWAY | high-speed running metres per minute | 2.405 | 6.864 | -65% |
| match_0030 | S1 press_increase | AWAY | share of opponent actions under pressure | 0.403 | 0.249 | +62% |
| match_0030 | S2 flank_overload | AWAY | share of passes to the left flank | 0.755 | 0.363 | +108% |
| match_0030 | S3 tempo_drop | AWAY | median seconds between own actions | 2.335 | 1.510 | +55% |
| match_0030 | S4 fatigue | HOME | high-speed running metres per minute | 2.958 | 7.252 | -59% |

Median change by scenario type: press_increase +81%, flank_overload +98%, tempo_drop +68%, fatigue -60%
