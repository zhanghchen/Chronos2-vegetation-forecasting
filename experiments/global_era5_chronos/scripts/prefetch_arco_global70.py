# Same batched ARCO-ERA5 prefetch as prefetch_arco_pool.py, but for the 70
# NEW global (non-CONUS) pixels instead of the CONUS pool. Shares the same
# local cache directory (era5_source_arco.CACHE_DIR, keyed by grid point +
# year) - these are entirely new grid points, so nothing from the CONUS
# prefetch is reused or overwritten, it just adds alongside it.
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import era5_source_arco as esa

POOL_CSV = Path(__file__).resolve().parents[1] / "data_selection/global_candidate_pixels_70.csv"
YEARS = list(range(2000, 2023))


def main():
    pool = pd.read_csv(POOL_CSV)
    pixels = {row["pixel_id"]: (row["lat"], row["lon"]) for _, row in pool.iterrows()}
    print(f"Prefetching {len(pixels)} global pixels x {len(YEARS)} years ({YEARS[0]}-{YEARS[-1]}) from ARCO-ERA5...", flush=True)
    result = esa.fetch_many_pixels_arco_daily(pixels, YEARS)
    for name, df in list(result.items())[:3]:
        print(name, df.shape, df.index.min(), df.index.max())
    print(f"Done. {len(result)} pixels cached in {esa.CACHE_DIR}")


if __name__ == "__main__":
    main()
