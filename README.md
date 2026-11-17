# gta6-twitch-ccu-forecast

[![make.fun · gta6-twitch-ccu-forecast-01](https://make.fun/badge/gta6-twitch-ccu-forecast-01.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![rank](https://make.fun/badge/gta6-twitch-ccu-forecast-01/mitsukikun/gta6-twitch-ccu-forecast/rank.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![reward](https://make.fun/badge/gta6-twitch-ccu-forecast-01/mitsukikun/gta6-twitch-ccu-forecast/reward.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)

A forecaster for the make.fun competition
**"Forecast GTA VI's launch-day Twitch viewers hour by hour"**
(`gta6-twitch-ccu-forecast-01`, $250 prize pool).

It reads one case — everything recorded up to the end of the release day's
first hour, that hour's Twitch viewer count included — and writes, for each
of hours 2 to 24 of 2026-11-19 (UTC), five quantiles of that hour's
concurrent viewers in the "Grand Theft Auto VI" Twitch category.

## Method

A launch-day curve is a shape: each past launch's hourly viewers, divided
by its own hour-1 print, transfer across launches of different sizes.

- Anchor on the case's hour-1 print `p1`.
- For every comparable past launch, take its release-day hourly curve as
  log-ratios to its own hour-1 print, `ln(viewers_h / viewers_1)`.
- Weight each comparable by resemblance to GTA VI: drop the target-history
  pseudo-launch and front-loaded global-unlock launches (release day peaks
  in hour 1–2); double-weight console-only launches; weight by launch
  scale with a Gaussian kernel in log10(hour-1 viewers) around `p1`.
- Per hour, the median is `p1 * exp(weighted median log-ratio)`; the
  spread is 0.7× the weighted standard deviation of the log-ratios
  (floored 0.25, capped 1.2), and the five quantiles sit at the standard
  normal quantiles around that median. Hours with too few comparables fall
  back to the house persistence shape.

## Local practice check

Scored locally on the kit's four practice launches (Marvel's Wolverine,
Red Dead Redemption 2, God of War Ragnarök, Marvel's Spider-Man 2) against
their SullyGnome hourly averages, with the contest's own pinball loss on
the log scale:

| Entry | Mean loss | p00 | p01 | p02 | p03 |
|---|---:|---:|---:|---:|---:|
| This forecaster | **0.211** | 0.385 | 0.165 | 0.124 | 0.173 |
| House persistence baseline | 0.387 | 0.744 | 0.287 | 0.215 | 0.303 |

Typical miss about 45% (Wolverine's 9x evening rise is the hard case),
90% coverage about 0.97. The practice pays
nothing and is no guide to the final — it only shows the shape model beats
flat persistence on past launches of the same kind.

## Run

Standard library only, Python 3.13, deterministic (two runs write
byte-identical forecasts), well inside the 8-second limit:

```sh
mkdir -p out && MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```
