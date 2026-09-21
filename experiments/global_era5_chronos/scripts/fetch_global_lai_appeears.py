# Global LAI ground truth for the 70 non-CONUS pixels, via NASA's AppEEARS
# point-sample API (https://appeears.earthdatacloud.nasa.gov/api/) -
# requests a time series at specific lat/lon points directly, so we never
# download/mosaic full MODIS granules (the same "don't download unnecessary
# global data" principle already applied to the ERA5 cloud source).
#
# Product: MOD15A2H.061 (Terra-only, 8-day, 500m Leaf Area Index) - NOT the
# combined MCD15A2H.061 (Terra+Aqua), because MCD15A2H only starts mid-2002
# while MOD15A2H covers 2000-02-18 onward, matching HiQ-LAI's own start
# date/cadence exactly (HiQ-LAI is itself MODIS-derived).
# Layers: Lai_500m (the value, scale factor 0.1 -> m^2/m^2) and
# FparLai_QC (quality flags, used to drop poor retrievals - see
# load_and_filter_lai.py for the exact QC bit convention).
#
# Auth: reuses the existing ~/.netrc `urs.earthdata.nasa.gov` credentials
# (confirmed working - see this session's login test) via AppEEARS'
# username/password login endpoint.
import json
import netrc
import time
from pathlib import Path

import pandas as pd
import requests

API = "https://appeears.earthdatacloud.nasa.gov/api"
ROOT = Path(__file__).resolve().parents[1]
PIXELS_CSV = ROOT / "data_selection/global_candidate_pixels_70.csv"
OUT_DIR = ROOT / "data/global_lai"
OUT_DIR.mkdir(parents=True, exist_ok=True)
TASK_NAME = "chronos2_global70_lai_v1"


def login(max_retries=8):
    n = netrc.netrc()
    user, _, password = n.authenticators("urs.earthdata.nasa.gov")
    last_err = None
    for attempt in range(max_retries):
        try:
            r = requests.post(f"{API}/login", auth=(user, password), timeout=30)
            r.raise_for_status()
            return r.json()["token"]
        except requests.exceptions.RequestException as e:
            last_err = e
            wait = 15 * (attempt + 1)
            print(f"  [retry {attempt+1}/{max_retries}] login failed: {e} - waiting {wait}s")
            time.sleep(wait)
    raise RuntimeError(f"AppEEARS login failed after {max_retries} attempts: {last_err}")


def submit_task(token):
    pixels = pd.read_csv(PIXELS_CSV)
    coords = [{"id": row["pixel_id"], "latitude": row["lat"], "longitude": row["lon"]}
              for _, row in pixels.iterrows()]
    payload = {
        "task_type": "point",
        "task_name": TASK_NAME,
        "params": {
            "dates": [{"startDate": "01-01-2000", "endDate": "12-31-2022"}],
            "layers": [
                {"product": "MOD15A2H.061", "layer": "Lai_500m"},
                {"product": "MOD15A2H.061", "layer": "FparLai_QC"},
            ],
            "coordinates": coords,
        },
    }
    r = requests.post(f"{API}/task", json=payload, headers={"Authorization": f"Bearer {token}"})
    if not r.ok:
        print("submit failed:", r.status_code, r.text)
        r.raise_for_status()
    task_id = r.json()["task_id"]
    print(f"Submitted task {task_id} ({len(coords)} points, 2000-01-01 to 2022-12-31)")
    (OUT_DIR / "task_id.txt").write_text(task_id)
    return task_id


def find_existing_task(token):
    r = requests.get(f"{API}/task", headers={"Authorization": f"Bearer {token}"})
    r.raise_for_status()
    for t in r.json():
        if t.get("task_name") == TASK_NAME:
            return t["task_id"], t.get("status")
    return None, None


def main():
    token = login()
    existing_id, existing_status = find_existing_task(token)
    if existing_id:
        print(f"Found existing task {existing_id} (status={existing_status}) - not resubmitting.")
        (OUT_DIR / "task_id.txt").write_text(existing_id)
        return existing_id
    return submit_task(token)


if __name__ == "__main__":
    main()
