# CMP-003 Experiment · New Onboarding Flow

## Recommendation

**Roll out the new onboarding flow in stages across markets.**

The new flow increased completed orders during the first 30 days by
**+49%** (+15.9 orders per
restaurant; 95% CI: +27% to
+72%;
p = 0.0000). After adjustment for market, cuisine,
acquisition channel, and signup cohort, the estimated effect is
**+50%** (95% CI:
+28% to
+76%).

## Experiment design

| | |
|---|---|
| Randomisation unit | Restaurant |
| Assignment | Randomised within market, city size, and chain status |
| Signup period | 2025-10-02 to 2026-06-29 |
| Sample | 148 control / 136 treatment |
| Primary metric | Completed orders in the first 30 days |
| Guardrail | Support tickets in the first 30 days |

## Results

| Metric | Control | Treatment | Difference | p-value |
|---|---|---|---|---|
| 30-day orders | 32.4 | 48.3 | +49.2% | 0.0000 |
| 30-day GMV (EUR) | 977 | 1440 | +47.4% | 0.0000 |
| 7-day activation | 93.9% | 100.0% | +6.1 pp | 0.0035 |
| 90-day retention | 88.1% | 91.2% | +3.0 pp | 0.4421 |
| 30-day support tickets | 0.97 | 0.90 | -7.0% | 0.6398 |

## Limitations

1. **Power.** The sample of 284 restaurants can detect effects of roughly
   31% or more at 80% power. Confirming a +10%
   uplift would require about 1,388
   restaurants per group.
2. **Short outcome window.** Thirty days measures initial activation, not
   long-term customer value. The 90-day retention result has a smaller eligible sample.
3. **Novelty effect.** Part of the uplift may reflect additional attention during
   the pilot rather than the workflow alone.
4. **Seasonality.** Signups run from October through June. A summer rollout may
   perform differently even though cohorts are balanced between groups.
5. **Cost not observed.** The analysis does not include the operating cost of the
   new flow; the recommendation assumes that cost is comparable to the current process.

## Next step

Use a staged market rollout with the same primary and guardrail metrics, and add
cost per activated restaurant so that incremental return can be measured.
