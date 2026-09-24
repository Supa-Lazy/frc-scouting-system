"""
Monte Carlo match simulation engine for FRC scouting.

Provides recency-weighted team performance stats and probabilistic
win/score predictions via simulation.
"""

import numpy as np

from teams.models import Team_Match_Data


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_metric_value(match, key, legacy_keys):
    """Return float value for a metric from a Team_Match_Data record, or None."""
    value = match.data.get(key)
    if value is None:
        for lk in legacy_keys:
            value = match.data.get(lk)
            if value is not None:
                break
    if value is not None:
        return float(value)
    return None


def _is_all_zero(match):
    """Return True when every numeric field in match.data is zero (incomplete scan)."""
    if not match.data:
        return True
    numeric_vals = [float(v) for v in match.data.values() if isinstance(v, (int, float))]
    return not numeric_vals or all(v == 0 for v in numeric_vals)


def _linear_slope(values):
    """Return the linear regression slope of a 1-D sequence, or 0 if not enough data."""
    n = len(values)
    if n < 2:
        return 0.0
    x = np.arange(n, dtype=float)
    y = np.array(values, dtype=float)
    # slope = (n*sum(xy) - sum(x)*sum(y)) / (n*sum(x^2) - sum(x)^2)
    sx = x.sum()
    sy = y.sum()
    sxy = (x * y).sum()
    sxx = (x * x).sum()
    denom = n * sxx - sx * sx
    if denom == 0:
        return 0.0
    return (n * sxy - sx * sy) / denom


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_team_recent_data(team_number, comp_code, quantifier, config, n_recent=None):
    """
    Fetch non-excluded, non-all-zero match records for a team, ordered oldest→newest.

    Parameters
    ----------
    team_number : int
    comp_code   : str
    quantifier  : str  ("Quals" / "Playoff" / "Prac")
    config      : dict  from config_loader.get_config()
    n_recent    : int | None  — if set, return only the last n_recent matches

    Returns
    -------
    list[Team_Match_Data]  — may be empty
    """
    qs = Team_Match_Data.objects.filter(
        team_number=team_number,
        event=comp_code,
        quantifier=quantifier,
        is_excluded=False,
    ).order_by('match_number')

    records = [m for m in qs if not _is_all_zero(m)]

    if n_recent is not None and n_recent > 0:
        records = records[-n_recent:]

    return records


def compute_weighted_stats(match_records, config, decay=0.25):
    """
    Compute exponentially recency-weighted mean and std dev for every config metric
    plus the anchor fields driverRanking, defenseRanking, autoLeave.

    Weights: weight_i = exp(decay * (i - (n-1)))
    so the most-recent match (i = n-1) has weight = 1.0 and older matches decay
    exponentially toward zero.

    Parameters
    ----------
    match_records : list[Team_Match_Data]  ordered oldest → newest
    config        : dict
    decay         : float  (default 0.25)

    Returns
    -------
    dict  { metric_key: {"mean": float, "std": float, "n": int} }
          returns {} when match_records is empty.
    """
    n = len(match_records)
    if n == 0:
        return {}

    # Build weight vector
    indices = np.arange(n, dtype=float)
    weights = np.exp(decay * (indices - (n - 1)))   # last element = exp(0) = 1.0

    result = {}

    # --- anchor fields ---
    for field in ('driverRanking', 'defenseRanking', 'autoLeave'):
        vals = np.array([float(getattr(m, field, 0)) for m in match_records], dtype=float)
        w = weights.copy()
        # Only weight non-zero entries (mirrors _compute_team_averages behaviour)
        mask = vals > 0
        if mask.sum() == 0:
            result[field] = {"mean": 0.0, "std": 0.0, "n": n}
            continue
        w_masked = w[mask]
        v_masked = vals[mask]
        w_sum = w_masked.sum()
        mean = float((w_masked * v_masked).sum() / w_sum)
        if mask.sum() == 1:
            std = 0.0
        else:
            variance = float((w_masked * (v_masked - mean) ** 2).sum() / w_sum)
            std = float(np.sqrt(max(variance, 0.0)))
        result[field] = {"mean": mean, "std": std, "n": int(mask.sum())}

    # --- config metrics ---
    for metric in config.get('metrics', []):
        key = metric['key']
        legacy_keys = metric.get('legacy_keys', [])
        vals_list = []
        w_list = []
        for i, m in enumerate(match_records):
            v = _extract_metric_value(m, key, legacy_keys)
            if v is not None:
                vals_list.append(v)
                w_list.append(float(weights[i]))

        if not vals_list:
            result[key] = {"mean": 0.0, "std": 0.0, "n": 0}
            continue

        v_arr = np.array(vals_list, dtype=float)
        w_arr = np.array(w_list, dtype=float)
        w_sum = w_arr.sum()
        mean = float((w_arr * v_arr).sum() / w_sum)
        if len(vals_list) == 1:
            std = 0.0
        else:
            variance = float((w_arr * (v_arr - mean) ** 2).sum() / w_sum)
            std = float(np.sqrt(max(variance, 0.0)))

        result[key] = {"mean": mean, "std": std, "n": len(vals_list)}

    return result


def simulate_alliance_score(team_stats_list, config, n_iterations=10000):
    """
    Vectorised Monte Carlo simulation for a 3-robot alliance.

    For every iteration each robot's metric is sampled from
    Normal(mean, std) clamped to [0, metric_max * 1.5].
    The alliance score for an iteration is the sum over all robots and all metrics.

    Parameters
    ----------
    team_stats_list : list[dict]  — 3 stat dicts from compute_weighted_stats()
    config          : dict
    n_iterations    : int

    Returns
    -------
    dict with keys: mean, std, p10, p50, p90, samples (1000 values for histogram)
    """
    metrics = config.get('metrics', [])

    # Build per-metric, per-robot mean/std/max tensors  shape (n_metrics, 3)
    means = np.zeros((len(metrics), 3), dtype=float)
    stds  = np.zeros((len(metrics), 3), dtype=float)
    maxes = np.zeros((len(metrics), 3), dtype=float)

    for mi, metric in enumerate(metrics):
        key = metric['key']
        metric_max = float(metric.get('max', 999))
        for ri, stats in enumerate(team_stats_list):
            if key in stats:
                means[mi, ri] = stats[key]['mean']
                stds[mi, ri]  = stats[key]['std']
            maxes[mi, ri] = metric_max

    # shape (n_iterations, n_metrics, 3)
    raw_samples = np.random.normal(
        loc=means[np.newaxis, :, :],          # broadcast over iterations
        scale=stds[np.newaxis, :, :] + 1e-6,
        size=(n_iterations, len(metrics), 3)
    )

    # Clamp to [0, max * 1.5]
    upper = maxes[np.newaxis, :, :] * 1.5
    raw_samples = np.clip(raw_samples, 0.0, upper)

    # Alliance score per iteration: sum over metrics and robots  → shape (n_iterations,)
    alliance_scores = raw_samples.sum(axis=(1, 2))

    # Subsample 1000 for the histogram
    idx = np.random.choice(n_iterations, size=min(1000, n_iterations), replace=False)
    samples = alliance_scores[idx].tolist()

    return {
        "mean":    float(alliance_scores.mean()),
        "std":     float(alliance_scores.std()),
        "p10":     float(np.percentile(alliance_scores, 10)),
        "p50":     float(np.percentile(alliance_scores, 50)),
        "p90":     float(np.percentile(alliance_scores, 90)),
        "samples": samples,
    }


def simulate_match(red_team_numbers, blue_team_numbers, comp_code, quantifier,
                   config, n_iterations=10000):
    """
    Main entry point: run a full Monte Carlo match simulation.

    Parameters
    ----------
    red_team_numbers  : list[int]  — 3 team numbers
    blue_team_numbers : list[int]  — 3 team numbers
    comp_code         : str
    quantifier        : str
    config            : dict  from config_loader.get_config()
    n_iterations      : int

    Returns
    -------
    dict  — full simulation result (see module docstring / task spec)
    """
    metrics = config.get('metrics', [])

    warnings = []

    # --- helper: build per-team data ---
    def _team_result(team_number):
        records = get_team_recent_data(team_number, comp_code, quantifier, config)
        n_matches = len(records)

        if n_matches < 3:
            warnings.append(
                f"Team {team_number} has only {n_matches} match{'es' if n_matches != 1 else ''}"
            )

        if n_matches == 0:
            return {
                "stats": {},
                "n_matches": 0,
                "trend": "stable",
                "strengths": [],
                "weaknesses": [],
                "per_match_scores": [],
            }

        stats = compute_weighted_stats(records, config)

        # --- trend: linear regression of per-match total score (last 5) ---
        tail = records[-5:] if len(records) >= 5 else records
        per_match_scores = []
        for m in tail:
            total = 0.0
            for metric in metrics:
                key = metric['key']
                v = _extract_metric_value(m, key, metric.get('legacy_keys', []))
                if v is not None:
                    total += v
            per_match_scores.append(total)

        slope = _linear_slope(per_match_scores)
        if slope > 0.5:
            trend = "improving"
        elif slope < -0.5:
            trend = "declining"
        else:
            trend = "stable"

        # --- strengths / weaknesses: metric mean as fraction of metric max ---
        fractions = []
        for metric in metrics:
            key = metric['key']
            metric_max = float(metric.get('max', 999))
            mean_val = stats.get(key, {}).get('mean', 0.0)
            if metric_max > 0:
                frac = mean_val / metric_max
            else:
                frac = 0.0
            fractions.append((frac, mean_val, key, metric.get('display_name', key)))

        # Sort descending by fraction
        fractions_sorted = sorted(fractions, key=lambda x: x[0], reverse=True)

        strengths = [display for _, _, _, display in fractions_sorted[:2]]
        # weaknesses: bottom 2 with non-zero mean
        non_zero = [(frac, mean, key, display) for frac, mean, key, display in fractions_sorted
                    if mean > 0]
        weaknesses = [display for _, _, _, display in reversed(non_zero[-2:])] if non_zero else []

        return {
            "stats": stats,
            "n_matches": n_matches,
            "trend": trend,
            "strengths": strengths,
            "weaknesses": weaknesses,
            "per_match_scores": per_match_scores,
        }

    # --- collect team data for all 6 robots ---
    red_data  = [_team_result(t) for t in red_team_numbers]
    blue_data = [_team_result(t) for t in blue_team_numbers]

    # --- alliance-level simulation (vectorised over n_iterations) ---
    def _build_stats_list(team_data_list):
        return [td["stats"] for td in team_data_list]

    red_stats_list  = _build_stats_list(red_data)
    blue_stats_list = _build_stats_list(blue_data)

    # --- per-iteration scores for win probability ---
    # We need iteration-level scores for both alliances simultaneously.
    def _sample_alliance_scores(team_stats_list, n_iter):
        """Return 1-D array of length n_iter with alliance total scores."""
        if not metrics:
            return np.zeros(n_iter)

        means = np.zeros((len(metrics), 3), dtype=float)
        stds  = np.zeros((len(metrics), 3), dtype=float)
        maxes = np.zeros((len(metrics), 3), dtype=float)

        for mi, metric in enumerate(metrics):
            key = metric['key']
            metric_max = float(metric.get('max', 999))
            for ri, stats in enumerate(team_stats_list):
                if key in stats:
                    means[mi, ri] = stats[key]['mean']
                    stds[mi, ri]  = stats[key]['std']
                maxes[mi, ri] = metric_max

        raw = np.random.normal(
            loc=means[np.newaxis, :, :],
            scale=stds[np.newaxis, :, :] + 1e-6,
            size=(n_iter, len(metrics), 3)
        )
        upper = maxes[np.newaxis, :, :] * 1.5
        raw = np.clip(raw, 0.0, upper)
        return raw.sum(axis=(1, 2))

    red_iter_scores  = _sample_alliance_scores(red_stats_list,  n_iterations)
    blue_iter_scores = _sample_alliance_scores(blue_stats_list, n_iterations)

    red_wins  = int((red_iter_scores  > blue_iter_scores).sum())
    blue_wins = int((blue_iter_scores > red_iter_scores).sum())
    ties      = n_iterations - red_wins - blue_wins

    red_win_pct  = round(red_wins  / n_iterations * 100, 1)
    blue_win_pct = round(blue_wins / n_iterations * 100, 1)
    tie_pct      = round(ties      / n_iterations * 100, 1)

    # --- full alliance stat dicts (with histogram samples) ---
    red_alliance  = simulate_alliance_score(red_stats_list,  config, n_iterations)
    blue_alliance = simulate_alliance_score(blue_stats_list, config, n_iterations)

    def _fmt_team(team_number, team_data):
        stats = team_data["stats"]
        # Weighted mean across all metric means (rough single-number summary)
        mean_total = sum(
            stats.get(m['key'], {}).get('mean', 0.0)
            for m in metrics
        )
        std_total = float(np.sqrt(sum(
            stats.get(m['key'], {}).get('std', 0.0) ** 2
            for m in metrics
        )))
        return {
            "mean": round(mean_total, 2),
            "std": round(std_total, 2),
            "n_matches": team_data["n_matches"],
            "trend": team_data["trend"],
            "strengths": team_data["strengths"],
            "weaknesses": team_data["weaknesses"],
        }

    red_teams_out  = {t: _fmt_team(t, d) for t, d in zip(red_team_numbers,  red_data)}
    blue_teams_out = {t: _fmt_team(t, d) for t, d in zip(blue_team_numbers, blue_data)}

    data_warning = "; ".join(warnings) if warnings else None

    return {
        "red_win_pct":  red_win_pct,
        "blue_win_pct": blue_win_pct,
        "tie_pct":      tie_pct,
        "red": {
            "mean_score": round(red_alliance["mean"], 2),
            "p10":        round(red_alliance["p10"],  2),
            "p90":        round(red_alliance["p90"],  2),
            "samples":    red_alliance["samples"],
            "teams":      red_teams_out,
        },
        "blue": {
            "mean_score": round(blue_alliance["mean"], 2),
            "p10":        round(blue_alliance["p10"],  2),
            "p90":        round(blue_alliance["p90"],  2),
            "samples":    blue_alliance["samples"],
            "teams":      blue_teams_out,
        },
        "n_iterations": n_iterations,
        "data_warning": data_warning,
    }
