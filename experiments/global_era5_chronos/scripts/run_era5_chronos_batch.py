# Large-scale zero-shot Chronos-2 run across the full 70-pixel CONUS pool,
# using cloud ERA5 (Google ARCO-ERA5) as the climate covariate source, with
# a FULL 2000-2021 context (matching the existing 22-year-context gridMET
# CONUS-70 study's protocol exactly - fixing the earlier ERA5 experiment's
# short 2-year-context mismatch). Pixel set and LAI data are reused
# unchanged from the existing pool (AELSTM/outputs/pft_multipixel_selection/
# pft_diverse_pixels.csv); no new pixel sampling was invented.
#
# Requires prefetch_arco_pool.py to have already populated
# data/era5_arco/cache/ for all 70 pixels (run in the era5cloud env). This
# script itself must run in the chronos2 env (needs torch/transformers) -
# it never touches the cloud/zarr/gcsfs path directly, only the small local
# CSV cache era5_source_arco.py already wrote.
#
#   /home/deh25003/miniconda3/envs/chronos2/bin/python3 run_era5_chronos_batch.py
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_era5_chronos as rec  # noqa: E402 - triggers the required HDF5 warm-up import order

POOL_CSV = Path("/home/deh25003/chronos-forecasting/AELSTM/outputs/pft_multipixel_selection/pft_diverse_pixels.csv")
YEARS = list(range(2000, 2023))
TEST_YEAR = 2022
OUT_DIR = Path(__file__).resolve().parents[1] / "outputs"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def main():
    pool = pd.read_csv(POOL_CSV)
    rows = []
    pipeline = None
    t_start = time.time()
    for i, prow in pool.iterrows():
        site, lat, lon = prow["pixel_id"], prow["lat"], prow["lon"]
        try:
            metrics, pipeline = rec.run_one_pixel(
                site, lat, lon, YEARS, test_year=TEST_YEAR, source="cloud", pipeline=pipeline, verbose=False
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

        pd.DataFrame(rows).to_csv(OUT_DIR / "era5_cloud_70pixels.csv", index=False)  # checkpoint every pixel

    print(f"\nDone: {len(rows)} pixels in {time.time()-t_start:.0f}s -> {OUT_DIR / 'era5_cloud_70pixels.csv'}")


if __name__ == "__main__":
    main()
