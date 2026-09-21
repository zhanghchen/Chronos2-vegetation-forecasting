# Large-scale zero-shot Chronos-2 run across the 70 NEW non-CONUS global
# pixels, using cloud ERA5 (same source/pipeline as the CONUS 70-pixel
# study) and MODIS MOD15A2H LAI (via AppEEARS - see
# fetch_global_lai_appeears.py / load_global_lai.py) as ground truth.
# Same protocol as the CONUS study: context = 2000-2021, test year = 2022,
# zero-shot Chronos-2 (no training/fine-tuning).
#
# Requires (in order): select_global_pixels.py (pixel selection, already
# run), fetch_global_lai_appeears.py + poll_and_download_lai.py (LAI),
# load_global_lai.py (QC-filter + per-pixel CSVs), prefetch_arco_global70.py
# (climate cache). This script itself needs the chronos2 env (torch).
#
#   /home/deh25003/miniconda3/bin/python3 run_era5_chronos_batch_global.py  # WRONG env, will fail on torch
#   /home/deh25003/miniconda3/envs/chronos2/bin/python3 run_era5_chronos_batch_global.py
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_era5_chronos as rec  # noqa: E402 - triggers the required HDF5 warm-up import order

ROOT = Path(__file__).resolve().parents[1]
POOL_CSV = ROOT / "data_selection/global_candidate_pixels_70.csv"
LAI_DIR = ROOT / "data/global_lai/processed"
RESULTS_ROOT = ROOT / "results_global"
YEARS = list(range(2000, 2023))
TEST_YEAR = 2022
OUT_DIR = ROOT / "outputs"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def main():
    pool = pd.read_csv(POOL_CSV)
    have_lai = {p.stem for p in LAI_DIR.glob("*.csv")}
    pool = pool[pool["pixel_id"].isin(have_lai)].reset_index(drop=True)
    print(f"{len(pool)}/70 pixels have usable LAI data (see load_global_lai.py's coverage filter)")

    rows = []
    pipeline = None
    t_start = time.time()
    for i, prow in pool.iterrows():
        site, lat, lon = prow["pixel_id"], prow["lat"], prow["lon"]
        try:
            metrics, pipeline = rec.run_one_pixel(
                site, lat, lon, YEARS, test_year=TEST_YEAR, source="cloud", pipeline=pipeline, verbose=False,
                lai_dir=LAI_DIR, results_root=RESULTS_ROOT,
            )
            metrics.update(dominant_pft=prow["dominant_pft"], pft_purity=prow["pft_purity"],
                            region=prow["region"], n_pixels_done=i + 1)
            rows.append(metrics)
            print(f"[{i+1}/{len(pool)}] {site}: R2={metrics['R2']:.4f} RMSE={metrics['RMSE']:.4f} "
                  f"context={metrics['context_steps']} ({time.time()-t_start:.0f}s elapsed)")
        except Exception as e:  # noqa - log and continue; one bad pixel shouldn't abort the batch
            print(f"[{i+1}/{len(pool)}] {site}: FAILED - {e}")
            rows.append({"site": site, "error": str(e), "dominant_pft": prow["dominant_pft"],
                         "region": prow["region"], "pft_purity": prow["pft_purity"]})

        pd.DataFrame(rows).to_csv(OUT_DIR / "era5_global70.csv", index=False)  # checkpoint every pixel

    print(f"\nDone: {len(rows)} pixels in {time.time()-t_start:.0f}s -> {OUT_DIR / 'era5_global70.csv'}")


if __name__ == "__main__":
    main()
