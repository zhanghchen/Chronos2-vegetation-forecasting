# QC-filters the AppEEARS MOD17A2HGF.061 point-sample results (raw combined
# CSV, one row per pixel-date) and writes one data/processed/sites_gpp/{site}.csv
# per CONUS site, matching the exact column contract of
# data/processed/sites/{site}.csv (date, <target>, tmmx, tmmn, pr, srad,
# vpd, sph, vs) so loyo_cv_gpp_anomaly_chronos2.py can reuse
# common_pipeline/loyo_cv_chronos2/loyo_cv_anomaly_chronos2 unmodified, just
# pointed at this directory with target_col="GPP" instead of "LAI".
#
# QC rule mirrors experiments/global_era5_chronos/scripts/load_global_lai.py
# exactly (see that file's header for the fuller rationale): keep only
# MODLAND QC bit == "0b0" ("Good quality") AND Gpp_500m within its documented
# valid physical range (0.0-3.0 kg C/m^2/8-day, per AppEEARS'
# GET /api/product/MOD17A2HGF.061 metadata).
#
# SCALE-FACTOR CAUTION (same lesson as the LAI bug, 2026-09-25): AppEEARS'
# point-sample API already returns SCALED physical values - do NOT
# re-apply the 0.0001 scale factor documented in the product metadata.
# This script verifies the raw range empirically before trusting it (see
# the printed sanity-check line) rather than assuming either way.
import argparse
import glob
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
WEATHER_DIR = ROOT / "data/processed/sites"
OUT_DIR = ROOT / "data/processed/sites_gpp"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# --raw-dir picks which AppEEARS download to use - whichever of the
# parallel 8/20/70-site requests finished first (2026-10-28: all three
# submitted at once since the 70-site request sat in AppEEARS' queue for
# hours with no ETA; this script works unmodified against any of them,
# it just writes fewer data/processed/sites_gpp/*.csv for a smaller pool).
RAW_DIR_CHOICES = {
    "8": ROOT / "data/conus_gpp8_gf/raw",
    "20": ROOT / "data/conus_gpp20_gf/raw",
    "70": ROOT / "data/conus_gpp_gf/raw",
}

GPP_VALID_MAX = 3.0  # kg C/m^2/8-day, per AppEEARS product metadata (ValidMax)


def find_results_csv(raw_dir):
    matches = glob.glob(str(raw_dir / "*results.csv"))
    if not matches:
        raise FileNotFoundError(f"No *results.csv found in {raw_dir} - has the AppEEARS download finished?")
    if len(matches) > 1:
        raise RuntimeError(f"Multiple *results.csv found in {raw_dir}, expected one: {matches}")
    return Path(matches[0])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pool", choices=sorted(RAW_DIR_CHOICES), default="70",
                         help="which AppEEARS download to use (8/20/70 points)")
    args = parser.parse_args()
    raw_dir = RAW_DIR_CHOICES[args.pool]
    raw_csv = find_results_csv(raw_dir)
    print(f"Using pool={args.pool} -> {raw_csv}")
    df = pd.read_csv(raw_csv)
    gpp_col = [c for c in df.columns if c.endswith("_Gpp_500m") and not c.endswith("_bitmask")]
    qc_col = [c for c in df.columns if c.endswith("_Psn_QC_500m_MODLAND") and not c.endswith("Description")]
    if len(gpp_col) != 1 or len(qc_col) != 1:
        raise RuntimeError(f"Expected exactly one GPP column and one QC-MODLAND column, got {gpp_col} / {qc_col}")
    gpp_col, qc_col = gpp_col[0], qc_col[0]

    df = df[["ID", "Date", gpp_col, qc_col]].copy()
    df.columns = ["pixel_id", "date", "gpp_raw", "modland_qc"]
    df["date"] = pd.to_datetime(df["date"])

    # Sanity-check the scale factor empirically before trusting it, per the
    # LAI lesson - good-QC values should sit well inside [0, 3.0], not look
    # like raw int16 DNs (0-30000) or be suspiciously capped under ~0.3.
    good_qc = df[df["modland_qc"].astype(str) == "0b0"]
    print(f"Good-QC Gpp_500m range: [{good_qc['gpp_raw'].min():.4f}, {good_qc['gpp_raw'].max():.4f}] "
          f"(expect within [0, {GPP_VALID_MAX}] if AppEEARS already scaled it, as it did for LAI)")

    good = df[(df["modland_qc"].astype(str) == "0b0") & (df["gpp_raw"] >= 0) & (df["gpp_raw"] <= GPP_VALID_MAX)].copy()
    good["GPP"] = good["gpp_raw"]
    print(f"{len(good)}/{len(df)} pixel-dates pass QC ({len(good)/len(df):.1%})")

    coverage_rows = []
    n_written = 0
    for pixel_id, g in good.groupby("pixel_id"):
        weather_path = WEATHER_DIR / f"{pixel_id}.csv"
        if not weather_path.exists():
            coverage_rows.append({"pixel_id": pixel_id, "n_good_gpp_obs": len(g), "merged_rows": 0,
                                   "note": "no matching weather CSV in data/processed/sites/"})
            continue
        weather = pd.read_csv(weather_path, parse_dates=["date"])
        gpp_series = g.sort_values("date")[["date", "GPP"]]
        merged = weather.merge(gpp_series, on="date", how="inner")
        feature_cols = ["tmmx", "tmmn", "pr", "srad", "vpd", "sph", "vs"]
        merged = merged[["date", "GPP"] + feature_cols].dropna().reset_index(drop=True)
        coverage_rows.append({"pixel_id": pixel_id, "n_good_gpp_obs": len(g), "merged_rows": len(merged),
                               "date_min": merged["date"].min() if len(merged) else None,
                               "date_max": merged["date"].max() if len(merged) else None, "note": ""})
        if len(merged) >= 100:
            merged.to_csv(OUT_DIR / f"{pixel_id}.csv", index=False)
            n_written += 1

    cov = pd.DataFrame(coverage_rows).sort_values("merged_rows")
    cov.to_csv(raw_dir.parent / "coverage_report.csv", index=False)
    print(f"\n{n_written}/{len(cov)} sites have >=100 merged GPP+weather rows -> written to {OUT_DIR}")
    print(cov[cov["merged_rows"] < 100].to_string(index=False))


if __name__ == "__main__":
    main()
