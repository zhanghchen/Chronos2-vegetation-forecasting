# Minimal, fast fallback: 1 maximally-pure (pft_purity=1.0) representative
# site per PFT class (8 classes -> px004..px011, chosen directly from
# data/processed/pft_diverse_pixels.csv), submitted alongside the stuck
# 70-site and slow-starting 20-site requests, as a bet this size (~8
# points x 23 years, close to the ~12,740-unit request that finished in
# 17s before) clears AppEEARS' queue fast enough to get SOME real GPP
# data - across every vegetation class - running today. Same
# MOD17A2HGF.061 fix as the other two (see fetch_conus_gpp_appeears.py's
# header for why).
import netrc
import time
from pathlib import Path

import pandas as pd
import requests

API = "https://appeears.earthdatacloud.nasa.gov/api"
ROOT = Path(__file__).resolve().parent.parent
PIXELS_CSV = ROOT / "data/conus_gpp/conus70_coords.csv"
OUT_DIR = ROOT / "data/conus_gpp8_gf"
OUT_DIR.mkdir(parents=True, exist_ok=True)
TASK_NAME = "chronos2_conus8_gppgf_v1"

SELECTED_SITES = [
    "px004_trees_ne", "px005_trees_bd", "px006_trees_nd",
    "px007_shrubs_ne", "px008_shrubs_bd", "px009_shrubs_nd",
    "px010_grass_nat", "px011_grass_man",
]


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
    pixels = pd.read_csv(PIXELS_CSV).set_index("pixel_id")
    coords = [{"id": sid, "latitude": pixels.loc[sid, "lat"], "longitude": pixels.loc[sid, "lon"]}
              for sid in SELECTED_SITES]
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
