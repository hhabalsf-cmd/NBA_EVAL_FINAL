#!/usr/bin/env python3
"""Audit the ELO game predictor in `game_predictor.py` against trivial baselines.

Read-only. Touches no production code, writes nothing to the database.

What it does
------------
1. Pulls every row of `game_predictions` and its graded outcome.
2. Reconstructs each game's true result from BallDontLie.
3. Scores the model and four trivial baselines on the *same* games.
4. Reports Wilson (not normal-approximation) intervals on every rate, an exact
   McNemar test on each paired comparison, Brier scores, a reliability table,
   and a series-clustered bootstrap.
5. Reports coverage: which scheduled games never got a prediction row.

Lookahead policy (enforced, not assumed)
----------------------------------------
Every baseline is built from games whose completion date is *strictly before*
the predicted game's date — `completed_date < game_date`, never `<=`. That is
the same as `.shift(1)` semantics at day granularity. NBA teams play at most
once per day, so a strict date cutoff cannot admit the game being predicted or
any later game. The cutoff is applied in one place (`_games_before`) so it can
be audited by reading a single function. `--verify-cutoff` asserts it directly.

Usage
-----
    NBA_EVAL_DISABLE_TF=1 python3 scripts/audit_game_predictor.py
    NBA_EVAL_DISABLE_TF=1 python3 scripts/audit_game_predictor.py --refresh
    NBA_EVAL_DISABLE_TF=1 python3 scripts/audit_game_predictor.py --verify-cutoff

The BDL season fetch takes ~2 minutes, so it is cached under `cache/`
(gitignored). `--refresh` forces a re-fetch.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

CACHE_PATH = REPO_ROOT / "cache" / "audit_game_predictor_games.json"

# Mirrors EloTracker in game_predictor.py. Duplicated deliberately: this script
# must be able to score the model without importing (and thereby depending on)
# the module under audit.
ELO_K_FAST = 20
ELO_HOME_ADVANTAGE = 100
ELO_INITIAL = 1500


# ── Statistics ─────────────────────────────────────────────────

def wilson(k: int, n: int, z: float = 1.959963985) -> tuple[float, float, float]:
    """Wilson score interval for a binomial proportion.

    Returns (point_estimate, lower, upper). Correct at small n, unlike the
    normal approximation, which is why it is used everywhere in this report.
    """
    if n == 0:
        return (float("nan"), float("nan"), float("nan"))
    p = k / n
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = (z / denom) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (p, max(0.0, centre - half), min(1.0, centre + half))


def binom_two_sided_p(b: int, c: int) -> float:
    """Exact two-sided binomial p-value for McNemar's test on discordant pairs.

    b = model right / baseline wrong, c = model wrong / baseline right.
    Under H0 each discordant pair is a fair coin.
    """
    n = b + c
    if n == 0:
        return 1.0
    def pmf(k: int) -> float:
        return math.comb(n, k) * (0.5 ** n)
    obs = pmf(b)
    # Sum probabilities of outcomes no more likely than the observed one.
    tol = 1e-12
    return min(1.0, sum(pmf(k) for k in range(n + 1) if pmf(k) <= obs + tol))


def brier(probs: list[float], outcomes: list[int]) -> float:
    """Mean squared error of probabilistic forecasts. Lower is better."""
    if not probs:
        return float("nan")
    return sum((p - y) ** 2 for p, y in zip(probs, outcomes)) / len(probs)


def auc(scores: list[float], labels: list[int]) -> float:
    """Area under the ROC curve via the Mann-Whitney U statistic (ties = 0.5)."""
    pos = [s for s, y in zip(scores, labels) if y == 1]
    neg = [s for s, y in zip(scores, labels) if y == 0]
    if not pos or not neg:
        return float("nan")
    wins = sum(
        1.0 if a > b else 0.5 if a == b else 0.0
        for a in pos for b in neg
    )
    return wins / (len(pos) * len(neg))


def cluster_bootstrap_diff(
    records: list[dict], key_a: str, key_b: str, cluster_key: str,
    n_iter: int = 20000, seed: int = 20260824,
) -> tuple[float, float, float]:
    """Bootstrap the accuracy difference (a - b), resampling whole clusters.

    Playoff games are not independent: the same two teams meet up to seven
    times. Resampling individual games would understate the uncertainty, so
    entire series are resampled with replacement instead.
    """
    rng = random.Random(seed)
    by_cluster: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        by_cluster[r[cluster_key]].append(r)
    clusters = list(by_cluster)
    if not clusters:
        return (float("nan"),) * 3

    point = (
        sum(r[key_a] for r in records) - sum(r[key_b] for r in records)
    ) / len(records)

    diffs = []
    for _ in range(n_iter):
        drawn = [by_cluster[rng.choice(clusters)] for _ in clusters]
        flat = [r for group in drawn for r in group]
        if not flat:
            continue
        diffs.append(
            (sum(r[key_a] for r in flat) - sum(r[key_b] for r in flat)) / len(flat)
        )
    diffs.sort()
    lo = diffs[int(0.025 * len(diffs))]
    hi = diffs[int(0.975 * len(diffs)) - 1]
    return (point, lo, hi)


# ── Data loading ───────────────────────────────────────────────

def load_predictions() -> list[dict]:
    """Read every row of `game_predictions`. Read-only; no writes, no grading."""
    from dotenv import load_dotenv
    # Required: without override=True a stale env var yields a misleading
    # "password authentication failed for user postgres".
    load_dotenv(override=True)
    import db

    with db.borrow_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, timestamp, game_date, home_team, away_team,
                   predicted_winner, home_win_prob, away_win_prob, confidence,
                   actual_winner, correct, model_version, extended_data
            FROM game_predictions
            ORDER BY game_date, id
            """
        )
        return [dict(r) for r in cur.fetchall()]


def load_season_games(season: int, refresh: bool = False) -> list[dict]:
    """All final games of a season from BallDontLie, cached to disk."""
    if CACHE_PATH.exists() and not refresh:
        payload = json.loads(CACHE_PATH.read_text())
        if payload.get("season") == season:
            return payload["games"]

    from dotenv import load_dotenv
    load_dotenv(override=True)
    from bdl_client import get_bdl_client

    print(f"  fetching season {season} from BallDontLie (~2 min)...", flush=True)
    raw = get_bdl_client().get_games(seasons=[season]) or []
    games = []
    for g in raw:
        if str(g.get("status") or "").lower() != "final":
            continue
        home = g.get("home_team") or {}
        away = g.get("visitor_team") or {}
        hs, as_ = g.get("home_team_score"), g.get("visitor_team_score")
        if hs is None or as_ is None:
            continue
        games.append({
            "id": g.get("id"),
            "date": str(g.get("date") or "")[:10],
            "home": str(home.get("abbreviation") or "").upper(),
            "away": str(away.get("abbreviation") or "").upper(),
            "home_pts": int(hs),
            "away_pts": int(as_),
            "postseason": bool(g.get("postseason")),
        })
    games.sort(key=lambda x: (x["date"], x["id"]))
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps({"season": season, "games": games}))
    return games


# ── The single lookahead cutoff ────────────────────────────────

def _games_before(games: list[dict], game_date: str) -> list[dict]:
    """Every completed game strictly before `game_date`.

    THIS IS THE ONLY PLACE a cutoff is applied. `<` not `<=`: a team plays at
    most once per day, so this cannot admit the game being predicted, and no
    later game can precede it in date order.
    """
    return [g for g in games if g["date"] < game_date]


def records_asof(games: list[dict], game_date: str, regular_only: bool) -> dict[str, list[int]]:
    """Win/loss record for every team as of the morning of `game_date`."""
    rec: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for g in _games_before(games, game_date):
        if regular_only and g["postseason"]:
            continue
        hw = g["home_pts"] > g["away_pts"]
        rec[g["home"]][0 if hw else 1] += 1
        rec[g["away"]][1 if hw else 0] += 1
    return rec


def elo_asof(games: list[dict], game_date: str) -> dict[str, float]:
    """Elo ratings rebuilt from scratch over games strictly before `game_date`.

    A deliberately plain implementation: fast track only, margin-of-victory
    multiplier, no season reversion (single season). This is the "five-line
    script" the 71-feature stack has to beat.
    """
    elo: dict[str, float] = defaultdict(lambda: float(ELO_INITIAL))
    for g in _games_before(games, game_date):
        h, a = g["home"], g["away"]
        he = elo[h] + ELO_HOME_ADVANTAGE
        ae = elo[a]
        exp_h = 1.0 / (1.0 + 10 ** ((ae - he) / 400.0))
        margin = g["home_pts"] - g["away_pts"]
        actual = 1.0 if margin > 0 else 0.0
        mult = math.log(abs(margin) + 1) * (2.2 / ((he - ae) * 0.001 + 2.2))
        k = ELO_K_FAST * mult
        elo[h] += k * (actual - exp_h)
        elo[a] += k * (exp_h - actual)
    return elo


def verify_cutoff(games: list[dict], preds: list[dict]) -> None:
    """Assert no baseline input can see the game being predicted, or later."""
    print("Verifying lookahead cutoff...")
    checked = 0
    for p in preds:
        gd = str(p["game_date"])[:10]
        prior = _games_before(games, gd)
        for g in prior:
            assert g["date"] < gd, f"cutoff admitted {g['date']} for {gd}"
            same_matchup = {g["home"], g["away"]} == {p["home_team"], p["away_team"]}
            assert not (same_matchup and g["date"] >= gd), "admitted the predicted game"
        checked += 1
    print(f"  OK: {checked} predictions checked; "
          f"every baseline input strictly precedes its game date.\n")


# ── Report ─────────────────────────────────────────────────────

def fmt_rate(label: str, k: int, n: int) -> str:
    p, lo, hi = wilson(k, n)
    return (f"  {label:<44} {k:>3}/{n:<3} = {p*100:5.1f}%   "
            f"95% Wilson [{lo*100:4.1f}%, {hi*100:4.1f}%]")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--season", type=int, default=2025,
                    help="BDL season id (2025 = the 2025-26 season)")
    ap.add_argument("--refresh", action="store_true", help="re-fetch BDL games")
    ap.add_argument("--verify-cutoff", action="store_true",
                    help="run the lookahead assertions and exit")
    args = ap.parse_args()

    print("=" * 78)
    print("ELO GAME PREDICTOR AUDIT")
    print("=" * 78)
    print()

    preds = load_predictions()
    print(f"game_predictions rows: {len(preds)}")
    if not preds:
        print("No rows. Nothing to audit.")
        return 0

    games = load_season_games(args.season, refresh=args.refresh)
    print(f"season {args.season} final games available: {len(games)}")

    if args.verify_cutoff:
        verify_cutoff(games, preds)
        return 0

    by_key = {(g["date"], g["home"], g["away"]): g for g in games}

    dates = sorted({str(p["game_date"])[:10] for p in preds})
    print(f"prediction date range: {dates[0]} .. {dates[-1]}")
    postseason_rows = sum(
        1 for p in preds
        if by_key.get((str(p["game_date"])[:10], p["home_team"], p["away_team"]),
                      {}).get("postseason")
    )
    print(f"rows that are postseason games: {postseason_rows}/{len(preds)}")
    print(f"model_version values in table: "
          f"{sorted({p['model_version'] for p in preds})}")
    print()

    # ── Coverage: scheduled games that never got a prediction ──
    print("-" * 78)
    print("COVERAGE")
    print("-" * 78)
    lo_d, hi_d = dates[0], dates[-1]
    in_window = [g for g in games if lo_d <= g["date"] <= hi_d]
    predicted_keys = {(str(p["game_date"])[:10], p["home_team"], p["away_team"])
                      for p in preds}
    missing = [g for g in in_window
               if (g["date"], g["home"], g["away"]) not in predicted_keys]
    print(f"  games played {lo_d}..{hi_d}: {len(in_window)}")
    print(f"  of those, predicted:        {len(in_window) - len(missing)}")
    print(f"  of those, NOT predicted:    {len(missing)}")
    for g in missing:
        print(f"    missing: {g['date']} {g['away']} @ {g['home']}")
    after = [g for g in games if g["date"] > hi_d]
    print(f"  games played AFTER the last prediction ({hi_d}): {len(after)}")
    if after:
        print(f"    spanning {after[0]['date']} .. {after[-1]['date']} "
              f"-- zero predictions were written for any of them")
    print()

    # ── Build the scored record ──
    rows = []
    unresolved = []
    for p in preds:
        gd = str(p["game_date"])[:10]
        home, away = p["home_team"], p["away_team"]
        g = by_key.get((gd, home, away))
        if g is None:
            unresolved.append(p)
            continue
        home_won = 1 if g["home_pts"] > g["away_pts"] else 0
        actual = home if home_won else away

        # Model
        hp = float(p["home_win_prob"]) / 100.0
        model_pick = p["predicted_winner"]

        # Baselines, each from games strictly before gd.
        rs = records_asof(games, gd, regular_only=True)
        asof = records_asof(games, gd, regular_only=False)
        el = elo_asof(games, gd)

        def pct(rec, t):
            w, l = rec.get(t, [0, 0])
            return w / (w + l) if (w + l) else 0.5

        rs_pick = home if pct(rs, home) >= pct(rs, away) else away
        asof_pick = home if pct(asof, home) >= pct(asof, away) else away
        elo_home_prob = 1.0 / (1.0 + 10 ** (
            (el.get(away, ELO_INITIAL) - (el.get(home, ELO_INITIAL) + ELO_HOME_ADVANTAGE)) / 400.0
        ))
        elo_pick = home if elo_home_prob >= 0.5 else away

        rows.append({
            "id": p["id"], "date": gd, "home": home, "away": away,
            "series": "-".join(sorted([home, away])),
            "home_won": home_won, "actual": actual,
            "home_prob": hp,
            "db_correct": p["correct"],
            "model": int(model_pick == actual),
            "home_bl": int(home == actual),
            "rs_bl": int(rs_pick == actual),
            "asof_bl": int(asof_pick == actual),
            "elo_bl": int(elo_pick == actual),
            "elo_home_prob": elo_home_prob,
            "model_picked_home": int(model_pick == home),
        })

    if unresolved:
        print(f"NOTE: {len(unresolved)} prediction rows had no matching final "
              f"game and are excluded.")
        for p in unresolved:
            print(f"    {str(p['game_date'])[:10]} {p['away_team']} @ {p['home_team']}")
        print()

    # Grading cross-check: does the DB's `correct` agree with the true result?
    print("-" * 78)
    print("GRADING INTEGRITY")
    print("-" * 78)
    graded = [r for r in rows if r["db_correct"] is not None]
    mismatches = [r for r in graded if r["db_correct"] != r["model"]]
    print(f"  rows with correct IS NOT NULL: {len(graded)}")
    print(f"  rows with correct IS NULL:     {len(rows) - len(graded)}")
    print(f"  DB `correct` vs independently recomputed result: "
          f"{len(mismatches)} mismatch(es) in {len(graded)}")
    for r in mismatches:
        print(f"    MISMATCH id={r['id']} {r['date']} {r['away']}@{r['home']} "
              f"db={r['db_correct']} recomputed={r['model']}")
    print(f"  `correct` column dtype convention: INTEGER 0/1 "
          f"(values seen: {sorted({r['db_correct'] for r in graded})})")
    print()

    ev = graded  # evaluate on graded rows only
    n = len(ev)
    if n == 0:
        print("No graded rows. Cannot score.")
        return 0

    # ── Accuracy vs baselines ──
    print("-" * 78)
    print(f"ACCURACY ON THE SAME {n} GRADED GAMES")
    print("-" * 78)
    keys = [
        ("model", "MODEL (71-feature stacking ensemble)"),
        ("home_bl", "BASELINE: always pick the home team"),
        ("rs_bl", "BASELINE: better regular-season win pct"),
        ("asof_bl", "BASELINE: better record as of game date"),
        ("elo_bl", "BASELINE: plain Elo rebuilt as-of (fast track)"),
    ]
    for k, label in keys:
        print(fmt_rate(label, sum(r[k] for r in ev), n))
    print(fmt_rate("BASELINE: coinflip (analytic)", n // 2, n)
          .replace(f"{n//2}/{n}", "  --   ")
          .replace(f"{(n//2)/n*100:5.1f}%", " 50.0%"))
    print()
    print(f"  home teams actually won: "
          f"{sum(r['home_won'] for r in ev)}/{n} = "
          f"{sum(r['home_won'] for r in ev)/n*100:.1f}%  "
          f"(the real home-win rate on THESE games, not an assumed 55-58%)")
    print(f"  model picked the home team: "
          f"{sum(r['model_picked_home'] for r in ev)}/{n} = "
          f"{sum(r['model_picked_home'] for r in ev)/n*100:.1f}%")
    print()

    # ── Paired comparisons ──
    print("-" * 78)
    print("PAIRED COMPARISONS (exact McNemar on discordant games)")
    print("-" * 78)
    for k, label in keys[1:]:
        b = sum(1 for r in ev if r["model"] == 1 and r[k] == 0)
        c = sum(1 for r in ev if r["model"] == 0 and r[k] == 1)
        p_val = binom_two_sided_p(b, c)
        pt, lo, hi = cluster_bootstrap_diff(ev, "model", k, "series")
        print(f"  model vs {label.split(': ')[-1]}")
        print(f"    model right/baseline wrong: {b}   "
              f"model wrong/baseline right: {c}   "
              f"(agree on {n - b - c} of {n})")
        print(f"    exact McNemar two-sided p = {p_val:.3f}")
        print(f"    accuracy difference {pt*100:+.1f} pts, "
              f"series-clustered 95% CI [{lo*100:+.1f}, {hi*100:+.1f}]")
        print()

    # ── Independence ──
    print("-" * 78)
    print("EFFECTIVE SAMPLE SIZE")
    print("-" * 78)
    series = defaultdict(list)
    for r in ev:
        series[r["series"]].append(r)
    print(f"  graded games: {n}")
    print(f"  distinct matchups (series): {len(series)}")
    for s, gs in sorted(series.items()):
        print(f"    {s:<9} {len(gs)} games, model {sum(x['model'] for x in gs)}/{len(gs)}")
    print()
    print("  Games within a playoff series share both rosters, both coaching")
    print("  staffs and one matchup dynamic. They are not independent trials,")
    print("  so the effective n is far closer to the number of series than to")
    print("  the number of games.")
    print()

    # ── Probability quality ──
    print("-" * 78)
    print("PROBABILITY QUALITY")
    print("-" * 78)
    probs = [r["home_prob"] for r in ev]
    outs = [r["home_won"] for r in ev]
    base = sum(outs) / len(outs)
    print(f"  Brier (model):                      {brier(probs, outs):.4f}")
    print(f"  Brier (always predict base rate {base:.3f}): "
          f"{brier([base]*len(outs), outs):.4f}")
    print(f"  Brier (always 0.500):               {brier([0.5]*len(outs), outs):.4f}")
    print(f"  Brier (plain as-of Elo):            "
          f"{brier([r['elo_home_prob'] for r in ev], outs):.4f}")
    print(f"  AUC  (model home_win_prob):         {auc(probs, outs):.4f}")
    print(f"  AUC  (plain as-of Elo):             "
          f"{auc([r['elo_home_prob'] for r in ev], outs):.4f}")
    print()
    distinct = sorted({round(p, 4) for p in probs})
    print(f"  distinct home_win_prob values emitted: {len(distinct)} across {n} games")
    print(f"    {[f'{d:.3f}' for d in distinct]}")
    print("    (the isotonic calibrator is a step function, so probabilities")
    print("     are quantised onto a small lattice and clipped to [0.15, 0.85])")
    print()

    print("  Reliability (predicted home win prob vs realised):")
    buckets = [(0.0, 0.35), (0.35, 0.45), (0.45, 0.55), (0.55, 0.65), (0.65, 1.01)]
    print(f"    {'bucket':<14}{'n':>4}{'mean pred':>11}{'realised':>10}{'gap':>9}   95% Wilson")
    for lo_b, hi_b in buckets:
        sel = [r for r in ev if lo_b <= r["home_prob"] < hi_b]
        if not sel:
            continue
        mp = sum(r["home_prob"] for r in sel) / len(sel)
        k = sum(r["home_won"] for r in sel)
        pr, wl, wh = wilson(k, len(sel))
        print(f"    [{lo_b:.2f},{hi_b:.2f}){len(sel):>4}{mp*100:>10.1f}%"
              f"{pr*100:>9.1f}%{(pr-mp)*100:>+8.1f}   [{wl*100:.1f}%, {wh*100:.1f}%]")
    print()

    # ── Does confidence sort outcomes? ──
    print("-" * 78)
    print("DOES THE MODEL'S OWN CONFIDENCE SORT OUTCOMES?")
    print("-" * 78)
    for r in ev:
        r["conf"] = max(r["home_prob"], 1 - r["home_prob"])
        r["edge"] = abs(r["home_prob"] - 0.5) * 2
    tiers = [
        ("NO_BET   (edge < 0.05)", lambda r: r["edge"] < 0.05),
        ("LEAN     (0.05-0.10)", lambda r: 0.05 <= r["edge"] < 0.10),
        ("BET      (0.10-0.20)", lambda r: 0.10 <= r["edge"] < 0.20),
        ("STRONG   (edge >= 0.20)", lambda r: r["edge"] >= 0.20),
    ]
    print("  by the model's own bet_quality tiers (recomputed from stored prob):")
    for label, pred_fn in tiers:
        sel = [r for r in ev if pred_fn(r)]
        if sel:
            print(fmt_rate("    " + label, sum(r["model"] for r in sel), len(sel)))
    print()
    lo_c = [r for r in ev if r["conf"] < 0.62]
    hi_c = [r for r in ev if r["conf"] >= 0.62]
    print("  split at 62% confidence:")
    if lo_c:
        print(fmt_rate("    lower-confidence half", sum(r["model"] for r in lo_c), len(lo_c)))
    if hi_c:
        print(fmt_rate("    higher-confidence half", sum(r["model"] for r in hi_c), len(hi_c)))
    print()
    print("  If confidence carried information, the higher-confidence tier would")
    print("  win at a higher rate than the lower one.")
    print()

    # ── Staleness of the Elo snapshot actually served ──
    print("-" * 78)
    print("STALENESS OF THE SERVED Elo SNAPSHOT")
    print("-" * 78)
    try:
        import joblib
        pkl = REPO_ROOT / "models" / "games" / "game_predictor.pkl"
        data = joblib.load(pkl)
        trained_at = str(data.get("trained_at", ""))[:10]
        fnames = list(data.get("feature_names") or [])
        print(f"  model pkl trained_at: {trained_at}")
        print(f"  selected features:    {len(fnames)}")
        print()
        print("  `self.elo_tracker` is restored from this pkl and is never updated")
        print("  between trainings (`compute_from_games` is called only inside")
        print("  `train_model`). So every Elo feature served is a snapshot from")
        print(f"  {trained_at}. Games each team played after that but before the")
        print("  prediction, which the served Elo cannot see:")
        for gd in [dates[0], dates[len(dates) // 2], dates[-1]]:
            gap = [g for g in games if trained_at <= g["date"] < gd]
            per_team: dict[str, int] = defaultdict(int)
            for g in gap:
                per_team[g["home"]] += 1
                per_team[g["away"]] += 1
            avg = sum(per_team.values()) / len(per_team) if per_team else 0
            days = (
                __import__("datetime").date.fromisoformat(gd)
                - __import__("datetime").date.fromisoformat(trained_at)
            ).days
            print(f"    prediction date {gd}: {days:>2} days stale, "
                  f"{len(gap):>3} league games unseen, "
                  f"~{avg:.1f} per team")
        print()

        # Features that are real in training but constant at serve time.
        # `build_game_features` calls `_build_historical_features` with
        # `all_games_df=None`, so `_compute_sos` returns its 0.5 default.
        print("  Features that vary in TRAINING but are CONSTANT at SERVE time")
        print("  (build_game_features passes all_games_df=None -> SOS defaults):")
        print("  feature_names is ordered by descending RF importance, so the")
        print("  index below is the feature's importance rank among the 71 kept.")
        for f, val in [("sos_diff", 0.0), ("elo_x_sos", 0.0),
                       ("home_sos", 0.5), ("away_sos", 0.5)]:
            if f in fnames:
                print(f"    rank {fnames.index(f)+1:>2}/71  {f:<12} "
                      f"-> hard-coded {val} on every served prediction")
        print()
        print("  Features whose TRAINING and SERVE definitions differ (training")
        print("  pools 3 seasons of prior games; serve reads current season only):")
        for f in ["win_pct_diff", "home_win_pct", "away_win_pct",
                  "h2h_avg_margin", "h2h_home_wins"]:
            if f in fnames:
                print(f"    rank {fnames.index(f)+1:>2}/71  {f}")
    except Exception as e:
        print(f"  (could not inspect pkl: {type(e).__name__}: {e})")
    print()

    print("=" * 78)
    print("Every rate above carries a Wilson interval. Where two intervals")
    print("overlap heavily, this sample does not distinguish the two methods.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
