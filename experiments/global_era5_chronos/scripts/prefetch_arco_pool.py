# One-time batched prefetch of the full 2000-2022 ARCO-ERA5 history for the
# entire 70-pixel pool (AELSTM/outputs/pft_multipixel_selection/
# pft_diverse_pixels.csv - the same pixel set already used for the CONUS-70
# gridMET zero-shot study, reused here per the project's explicit
# instruction to reuse existing pixel definitions rather than inventing a
# new sampling scheme).
#
# Uses era5_source_arco.fetch_many_pixels_arco_daily(), which reads each
# unique (year) worth of global hourly chunks ONCE and extracts all 70
# pixels from it (verified empirically: 5-pixel batch costs the same as a
# 1-pixel request - see reports/ERA5_CLOUD_EQUIVALENCE_REPORT.md) - so this
# is a single ~100-minute fetch for the WHOLE pool, not 70 separate fetches.
# Run with the era5cloud conda env (has gcsfs/zarr/dask):
#   /home/deh25003/miniconda3/envs/era5cloud/bin/python3 prefetch_arco_pool.py
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import era5_source_arco as esa

POOL_CSV = Path("/home/deh25003/chronos-forecasting/AELSTM/outputs/pft_multipixel_selection/pft_diverse_pixels.csv")
YEARS = list(range(2000, 2023))  # matches the 22-year-context gridMET protocol (context 2000-2021, test 2022)


def main():
    pool = pd.read_csv(POOL_CSV)
    pixels = {row["pixel_id"]: (row["lat"], row["lon"]) for _, row in pool.iterrows()}
    print(f"Prefetching {len(pixels)} pixels x {len(YEARS)} years ({YEARS[0]}-{YEARS[-1]}) from ARCO-ERA5...")
    result = esa.fetch_many_pixels_arco_daily(pixels, YEARS)
    for name, df in list(result.items())[:3]:
        print(name, df.shape, df.index.min(), df.index.max())
    print(f"Done. {len(result)} pixels cached in {esa.CACHE_DIR}")


if __name__ == "__main__":
    main()
