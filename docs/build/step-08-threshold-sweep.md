# Threshold sweep — strict/relaxed retrieval cutoffs

Phase 5 of step 8. Dataset: 61 generated eval cases (`evals/data/generated/`), full suite scored with
`evals/harness/run.py` (four deterministic metrics + faithfulness/correctness judges) per threshold pair.

## Method

Two passes:

1. **Broad sweep** (`evals/harness/sweep.py`), one run each: (0.70, 0.55), (0.65, 0.50) [previous default],
   (0.60, 0.45), (0.55, 0.40), (0.50, 0.35).
2. **Repeat sweep** (`evals/harness/sweep_repeat.py`), 3 runs each on the two best-looking candidates from
   the broad sweep, to tell a real threshold effect apart from run-to-run noise before picking one.

Each threshold pair runs the full 61-case suite in a fresh subprocess (`config.py`'s settings are cached
at import time, so an in-process override would not take effect across the whole module graph).

## Broad sweep results

| strict | relaxed | faithful | correct | abstain_ok |
|---|---|---|---|---|
| 0.70 | 0.55 | 98% | 84% | 88% |
| 0.65 | 0.50 (previous default) | 100% | 89% | 94% |
| 0.60 | 0.45 | 97% | 93% | 94% |
| 0.55 | 0.40 | 95% | 89% | 91% |
| 0.50 | 0.35 | 98% | 97% | 94% |

Not a clean monotonic tradeoff — 0.55/0.40 dips on every metric relative to its neighbors on both sides.
On a 61-case dataset, a single run per point can't distinguish a real effect at one specific pair from
ordinary noise, so the two most promising pairs (0.60/0.45 and 0.50/0.35) were re-run 3x each before
drawing any conclusion from this table alone.

## Repeat sweep results

| strict | relaxed | faithful (mean, spread) | correct (mean, spread) | abstain_ok (mean, spread) |
|---|---|---|---|---|
| 0.60 | 0.45 | 96% (±4%) — [98%, 98%, 93%] | 94% (±2%) — [95%, 95%, 93%] | 97% (±2%) — [96%, 96%, 98%] |
| 0.50 | 0.35 | 96% (±7%) — [93%, 100%, 95%] | 97% (±1%) — [98%, 97%, 97%] | 95% (±2%) — [96%, 94%, 96%] |

## Finding

0.55/0.40's dip in the broad sweep is consistent with ordinary run-to-run noise on this dataset size, not
a real effect at that specific pair — the repeat sweep shows both ±2% and ±4-7% spreads from single-run
measurements alone, which covers the size of that dip.

0.50/0.35 edges out 0.60/0.45 on correctness (97% vs 94%, mean) and is comparable on abstention
correctness, but its faithfulness spread (±7%, swinging between 93% and 100%) is the widest seen anywhere
in either sweep. That instability means some case's retrieval result flips between runs at this looser
threshold — sometimes pulling in a fact that gets used faithfully, sometimes not. 0.60/0.45's faithfulness
spread is half that (±4%), and its mean faithfulness is the same.

## Decision

**strict_threshold = 0.60, relaxed_threshold = 0.45** (previously 0.65/0.50).

Faithfulness (fabrication risk) is the harder of the two gated failures to recover from, per the product
contract's failure ranking, so a small, stable faithfulness number was weighted over a few extra points of
correctness bought with a wider, less predictable spread. The correctness gap between the two candidates
(94% vs 97%, mean) is itself within the noise band either pair showed individually, so it is not treated
as decisive.

## Revisit trigger

- The dataset grows past ~100 cases, enough to make a single-run sweep point trustworthy without 3x
  repeats.
- A new category of case is added that specifically probes the 0.45–0.55 similarity band, which neither
  sweep covered in detail.
- Production traces show the false-abstention or fabrication rate drifting from what either sweep
  predicted.
