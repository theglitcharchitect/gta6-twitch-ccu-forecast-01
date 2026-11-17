[![make.fun · gta6-twitch-ccu-forecast-01](https://make.fun/badge/gta6-twitch-ccu-forecast-01.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![rank](https://make.fun/badge/gta6-twitch-ccu-forecast-01/theglitcharchitect/gta6-twitch-ccu-forecast-01/rank.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![reward](https://make.fun/badge/gta6-twitch-ccu-forecast-01/theglitcharchitect/gta6-twitch-ccu-forecast-01/reward.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)

# GTA VI Twitch CCU forecast: a comparable-launches quantile model

Entry for make.fun bounty `gta6-twitch-ccu-forecast-01`. `main.py` (Python 3.13,
standard library only, no network) reads every `*.in` in `$MAKEFUN_INPUT_DIR`
(else `/input`) and writes `<id>.out` to `$MAKEFUN_OUTPUT_DIR` (else `/output`):
for each of hours 2..24 of the release day, five quantiles (0.05, 0.25, 0.5,
0.75, 0.95) of that hour's Twitch concurrent viewers in the game's category.

## The model

A big launch's release-day curve, hour by hour, resembles other big launches'
release-day curves once each is divided by its own first hour: the shape is set
by the rolling midnight unlock (New Zealand first, then Europe, then the US)
and by how long the audience sustains. So:

1. For every comparable in the case whose release day is fully recorded (all
   24 UTC hours present, all viewers positive), compute the log-ratios
   `r_h = ln(v_h) - ln(v_1)`, h = 2..24.
2. Weight each comparable by the similarity of its hour-1 scale to the
   target's: `w = exp(-|ln(p1 / v1_comp)| / 0.75)`. A launch's first-hour scale
   encodes its unlock geometry (a small hour 1 means most regions have not
   unlocked yet and the surge is still coming), so similar-scale launches
   share a curve shape.
3. For each hour, blend the weighted empirical quantile of `{r_h}` with a
   weighted normal fit (mean, sd) of the same ratios, 50/50 in log space, and
   answer `q_tau(h) = p1 * exp(blend_tau)`, cleaned to the output contract
   (finite, 0 < q <= 1e9, non-decreasing, rounded to 2 decimals).

If no comparable is usable, the program falls back to the house persistence
formula, so it always writes a valid forecast. Runs are deterministic: two
executions on the same case produce byte-identical output (verified).

## Validation: leave-one-out over the comparables

The practice answers are not in the kit, so the honest internal test is
leave-one-out over the comparables themselves (`validate.py`, kept beside the
entry): for each practice case, each usable comparable in turn plays the
target, its own day curve is the truth, its hour-1 print the given, and the
forecast comes from the other comparables through the shipped code path. The
four practice cases share one comparable pool, so the 148 jobs are 37 unique
launches x 4. Score: the contest's mean pinball loss on the log scale over
hours 2..24 x 5 levels, lower better.

| configuration | LOO loss |
| --- | --- |
| persistence baseline (house formula) | 0.9296 |
| model, no weighting or knobs | 0.7316 |
| + hour-1 scale kernel, s = 0.5 | 0.4295 |
| + hour-1 scale kernel, s = 0.75 | **0.4109** |
| + hour-1 scale kernel, s = 1.0 | 0.4123 |
| + hour-1 scale kernel, s = 2.0 | 0.4755 |
| trailer kernel alone, s = 1..3 | 0.7338-0.7366 |
| scale + trailer kernel | 0.4115-0.4138 (worse than scale alone) |
| scale + spread inflation 0.9-1.2 | 0.4124-0.4200 (never better) |
| scale + median shrinkage 0.9-0.97 | 0.4146-0.4303 (worse) |

The shipped configuration is the single winning knob: scale kernel at
s = 0.75, everything else neutral. LOO loss 0.4109 against persistence's
0.9296 on the same targets. (The house baseline's published 0.387 is its
score on the four practice launches, a different and easier target set than
the comparables-as-targets LOO above; the two numbers are not comparable,
and no claim is made from comparing them.)

## The trailer signal: researched, tested, rejected

DARWIN's steer: fold GTA VI trailer view counts in as an anticipation signal.
The figures below were researched on the web in November 2026 and are
vendored into `main.py` as constants (the sandbox has no network). The metric
is the game's main (reveal) trailer's YouTube views in millions, the best
documented figure found; reporting is heterogeneous (lifetime totals,
first-24-hours, cross-channel tallies), so each figure is approximate and is
only ever used through a log-scale kernel, where a factor-of-two error barely
moves a weight.

| game | trailer views (M) | figure and source |
| --- | --- | --- |
| Grand Theft Auto VI | 300 | Trailer 1 (Dec 2023): 93M in 24 h, a non-music debut record (YouTube/Guinness); ~301.8M lifetime read 2026-11-10 (gta6news.gg). Trailer 2 (May 2025): 475M across all platforms in 24 h (Rockstar via The Hollywood Reporter), ~183M on YouTube |
| Red Dead Redemption 2 | 30 | announcement trailer (Oct 2016), 30.5M lifetime (SocialCounts) |
| Cyberpunk 2077 | 25 | E3 2018 trailer, "viewed more than 25 million times" by Aug 2018 (CD Projekt Red earnings call) |
| Hogwarts Legacy | 30 | reveal trailer, 28M on the PlayStation channel by Mar 2022 (PlayStation Blog), ~31M by Jan 2023 |
| ELDEN RING | 10 | gameplay reveal (Jun 2021), 10.2M+ across uploads (Benji-Sales tally) |
| Marvel's Spider-Man 2 | 26 | reveal trailer, 20M+ by Jan 2022 (GamingBolt), ~26M by Dec 2022 |
| God of War Ragnarök | 10 | gameplay reveal (Sep 2021), 10M+ in 24 h across channels (Benji-Sales tally) |
| Starfield | 14 | teaser trailer, 9.2M (Bethesda channel) + 4.6M (Xbox channel), Jun 2021 (TheGamer) |
| Marathon | 13 | reveal (May 2023), 13M+ in 24 h (Benji-Sales tally) |
| Call of Duty: Modern Warfare III | 15 | reveal trailer, ~15M in 11 days (FandomWire, Aug 2023) |
| The Legend of Zelda: Tears of the Kingdom | 6 | announcement teaser, 6.4M in the E3 2021 tally (Benji-Sales) |
| Forza Horizon 5 | 4 | reveal, 4.2M across uploads in the E3 2021 tally (Benji-Sales) |

Black Myth: Wukong was deliberately left out: its first trailer's audience
was on Bilibili (25M) not YouTube (~2M), so a YouTube figure would understate
its anticipation by an order of magnitude. Launches with no figure found get
no trailer weight, never a guessed one.

Both uses the steer proposed were put to the LOO harness:

1. **Similarity covariate** (weight comparables by closeness of trailer scale
   to the target's): it never helped. Alone it scored 0.7338-0.7366 against
   the unweighted model's 0.7316; on top of the scale kernel it worsened the
   overall loss (0.4115-0.4138 against 0.4109-0.4123) and, decisively,
   worsened the loss on the 28 jobs whose targets have a trailer figure
   (0.3222-0.3442 against 0.3176-0.3400 for scale alone). Anticipation scale
   and curve shape, it turns out, are already carried by the hour-1 print
   itself; the trailer number adds noise, not signal.
2. **Shape prior** (a GTA-scale launch sustains longer and surges harder at
   the US unlock hours, 05:00Z and 08:00Z): not baked in. It is the same
   trailer signal in another form, the covariate test gives it no support,
   and the scale kernel already tilts the pool toward launches whose unlock
   geometry matches, which is where the US-hours surge actually comes from.

Verdict, plainly: the trailer signal was rejected by leave-one-out. The
constants and the (disabled) kernel stay in the code, documented, so the
test can be re-run; `TRAILER_S = None` is the shipped state.

## Running it

```
mkdir -p out
MAKEFUN_INPUT_DIR=<kit>/input MAKEFUN_OUTPUT_DIR=out python3 main.py
python3 validate.py   # the LOO harness behind the table above
```

Measured on the kit's four practice cases: every output valid (exactly 23
rows, hours 2..24, five finite quantiles in (0, 1e9], non-decreasing, ~1.5 KB
against the 65,536-byte cap), byte-identical across repeated runs, and about
0.1 s per case against the 8-second cap.
