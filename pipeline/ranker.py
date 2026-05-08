"""
Ranker — Computes composite ranking scores for private life insurers.

Ranking weights (configurable):
  - New Business Premium (NBP):        40%  — market size / reach
  - Claim Settlement Ratio (CSR):      35%  — customer trust & reliability
  - Solvency Ratio:                    25%  — financial stability

Individual metric rankings and composite score are all output.
"""

import logging
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Default weights (must sum to 1.0)
DEFAULT_WEIGHTS = {
    "new_business_premium_cr":    0.40,
    "claim_settlement_ratio_pct": 0.35,
    "solvency_ratio":             0.25,
}


def _min_max_normalize(series: pd.Series) -> pd.Series:
    """Min-max scale a series to [0, 1]. Returns 0.5 for constant series."""
    mn, mx = series.min(), series.max()
    if mx == mn:
        return pd.Series([0.5] * len(series), index=series.index)
    return (series - mn) / (mx - mn)


def compute_rankings(master_df: pd.DataFrame, weights: dict = None) -> pd.DataFrame:
    """
    Compute per-metric ranks and a weighted composite score.

    Returns a ranking DataFrame with columns:
        company_name, rank_by_nbp, rank_by_csr, rank_by_solvency,
        composite_score, rank_overall
    """
    if weights is None:
        weights = DEFAULT_WEIGHTS

    df = master_df.copy()
    ranking_records = []

    metric_cols = list(weights.keys())

    # Drop rows with all ranking metrics missing
    df_rank = df.dropna(subset=metric_cols, how="all").copy()

    if df_rank.empty:
        logger.warning("No data available to rank.")
        return pd.DataFrame()

    # Fill remaining NaNs with column median so ranking still works
    for col in metric_cols:
        if col in df_rank.columns:
            df_rank[col] = pd.to_numeric(df_rank[col], errors="coerce")
            df_rank[col] = df_rank[col].fillna(df_rank[col].median())

    # Per-metric ranks (1 = best)
    rank_map = {
        "new_business_premium_cr":    "rank_by_nbp",
        "claim_settlement_ratio_pct": "rank_by_csr",
        "solvency_ratio":             "rank_by_solvency",
    }
    for metric, rank_col in rank_map.items():
        if metric in df_rank.columns:
            df_rank[rank_col] = df_rank[metric].rank(ascending=False, method="min").astype(int)

    # Normalized scores for composite
    normed = {}
    for metric in metric_cols:
        if metric in df_rank.columns:
            normed[metric] = _min_max_normalize(df_rank[metric])
        else:
            normed[metric] = pd.Series([0.0] * len(df_rank), index=df_rank.index)

    # Weighted composite score
    df_rank["composite_score"] = sum(
        normed[metric] * weight for metric, weight in weights.items()
    ).round(4)

    # Overall rank (1 = best composite score)
    df_rank["rank_overall"] = df_rank["composite_score"].rank(ascending=False, method="min").astype(int)

    # Build ranking output
    output_cols = ["company_name", "company_type"]
    for col in metric_cols:
        if col in df_rank.columns:
            output_cols.append(col)
    for rank_col in ["rank_by_nbp", "rank_by_csr", "rank_by_solvency", "composite_score", "rank_overall"]:
        if rank_col in df_rank.columns:
            output_cols.append(rank_col)

    ranking_df = df_rank[[c for c in output_cols if c in df_rank.columns]].sort_values("rank_overall")
    ranking_df = ranking_df.reset_index(drop=True)

    logger.info(f"Ranking complete: {len(ranking_df)} companies ranked.")
    return ranking_df
