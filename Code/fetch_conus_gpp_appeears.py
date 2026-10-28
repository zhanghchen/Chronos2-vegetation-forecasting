# CONUS GPP ground truth for Prof. Wang's suggestion that the physics-
# guided equation's effect may be more detectable on GPP than on LAI - via
# NASA's AppEEARS point-sample API, mirroring
# experiments/global_era5_chronos/scripts/fetch_global_lai_appeears.py
# exactly (same auth/task/poll/download pattern - see that file for the
# full API documentation in its comments), now pointed at MOD17A2HGF.061
# (MODIS GPP, gap-filled, 8-day composite, 500m) and the 70 existing CONUS
# LOYO-CV site coordinates instead of MOD15A2H.061 LAI and the 70 global
# pixels.
#
# v2 fix (2026-10-27): the first attempt (data/conus_gpp/, task v1) used
# MOD17A2H.061, which only returned 2021-2022 despite a correctly specified
# 2000-2022 request. Root cause, confirmed directly against AppEEARS'
# own product catalog (GET /api/product), not guessed: MOD17A2H.061's
# TemporalExtentStart is genuinely 2021-01-01 - it is NOT a full-record
# product, regardless of what the request date range says. The full-record
# equivalent (2000-01-01 - present, same Gpp_500m/Psn_QC_500m layers, same
# 0.0001 scale factor) is MOD17A2HGF.061 ("GF" = gap-filled), which is what
# this script now requests. Output goes to a new data/conus_gpp_gf/ dir -
# the old (2021-2022-only) data/conus_gpp/ download is left in place rather
# than overwritten, since it's still valid data for those two years.
import json
import netrc
import time
from pathlib import Path

import pandas as pd
import requests

API = "https://appeears.earthdatacloud.nasa.gov/api"
ROOT = Path(__file__).resolve().parent.parent
PIXELS_CSV = ROOT / "data/conus_gpp/conus70_coords.csv"
OUT_DIR = ROOT / "data/conus_gpp_gf"
OUT_DIR.mkdir(parents=True, exist_ok=True)
TASK_NAME = "chronos2_conus70_gppgf_v2"


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
                {"product": "MOD17A2HGF.061", "layer": "Gpp_500m"},
                {"product": "MOD17A2HGF.061", "layer": "Psn_QC_500m"},
            ],
            "coordinates": coords,
        },
    }
    r = requests.post(f"{API}/task", json=payload, headers={"Authorization": f"Bearer {token}"})
    if not r.ok:
        print("submit failed:", r.status_code, r.text)
        r.raise_for_status()
    task_id = r.json()["task_id"]
    print(f"Submitted task {task_id} ({len(coords)} points, 2000-01-01 to 2022-12-31, MOD17A2HGF.061)")
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
