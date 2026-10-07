# Predictor rebuild protocol — September 24, 2026

Recorded before running model selection or scoring the final holdout.

## Research basis

- [UBC's NBA minutes prediction project](https://github.com/UBC-MDS-2019-20/NBA-Minutes-Predictor) motivates testing playing time separately. Its results are not evidence that this implementation works.
- [Scikit-learn calibration guidance](https://scikit-learn.org/1.6/modules/calibration.html) requires calibration predictions independent of fitting. We use later calendar dates, not random player-game splits.
- [Conformalized quantile regression](https://arxiv.org/abs/1905.03222) motivates held-out residual adjustment of uncertainty. NBA observations are dependent and drifting; we measure empirical coverage and do not claim exchangeable-data guarantees.
- [Scikit-learn histogram gradient boosting](https://scikit-learn.org/1.6/modules/generated/sklearn.ensemble.HistGradientBoostingRegressor.html) supports bounded-complexity, pooled nonlinear models. Complexity is selected against simpler baselines.
- [The Odds API historical-data specification](https://the-odds-api.com/historical-odds-data/) establishes that timestamped historical prop offers are a separate input. Box scores alone cannot establish realized betting return.

## Data and cutoffs

Public ESPN Analytics box scores collected by [llimllib/nba_data](https://github.com/llimllib/nba_data), joined to NBA schedule/game-log dates. Pin the upstream revision and SHA-256 file hashes in a local manifest. Use regular-season games only, strictly positive minutes, and at least ten prior appearances. Exclude same-date and future history. Preserve cross-season history using a bounded rolling window, with explicit season/gap/team-change features in both training and serving. Forecasts are conditional on participation; missing availability is not a predicted DNP.

1. Fit candidates on 2021–22 and 2022–23.
2. Select per-stat specifications using 2023–24 only.
3. Refit the selected specifications on all games before July 1, 2024.
4. Calibrate the exact refitted model on October–December 2024.
5. Score once on January 2025 onward, reporting 2024–25 and 2025–26 separately. Models remain frozen; causal player histories update with completed games.

## Candidates and selection

Baselines: L5, L10, L20, trailing-60 mean, EWMA10, and the six-feature ridge specification used by the existing pooled model. Challengers: pooled regularized regression over causal history/role features; bounded histogram boosting; and predicted minutes × predicted per-minute production. Compare a small fixed set, without tuning against the final holdout. Select by validation MAE per stat, including the simple baselines as eligible winners. Evaluate minutes separately. PRA is modeled directly, preserving its observed component dependence in residuals.

Inputs are only historical box-score summaries plus known game date, home/away and team. Do not use the target game's starter status, minutes, usage, opponent outcome, final score, or realized injury information as inputs. No fabricated injury/lineup histories. This first rebuild cannot claim an advantage from live injury or bookmaker information it did not observe.

## Distribution and evaluation

Use later-period standardized residuals to form a nonnegative empirical predictive distribution, including integer push mass. Report MAE/RMSE, 80% interval coverage and width, and CRPS. Compare model losses on identical rows using date-cluster bootstrap confidence intervals. Score chronological/season-opening/high-minute subgroups, reporting sample sizes. Artificial lines may be used only for mechanical tests, never as evidence of betting profitability.

Offer evaluation requires an exact line, side, price, quote time, event start and event/player identity. Expected net return per unit risked is `P(win) × (decimal_odds − 1) − P(loss)`; pushes return stake. Reject stale, mismatched, future-dated or in-play quotes. Historical odds, if supplied, must be replayed strictly as of each prediction timestamp, with one prespecified selection rule and no post-holdout threshold optimization.

No automatic production promotion based only on lower stat error. Report the measured winner and limitations, expose the new engine for research, and keep the existing betting-release gate off until priced forward evidence supports enabling recommendations.
