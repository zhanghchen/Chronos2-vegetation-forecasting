# Fallback 20-site GPP fetch (same MOD17A2HGF.061 fix as
# fetch_conus_gpp_appeears.py v2 - see that file's header for the root
# cause), submitted IN PARALLEL with the full 70-site request as a hedge:
# the 70-site/23-year task has been stuck in AppEEARS' "processing" queue
# for 2.5+ hours with no ETA signal, so this smaller request (~3.5x fewer
# estimated units) is a bet that AppEEARS' queue handles it faster, giving
# at least SOME real GPP data to start the zero-shot comparison with while
# the full request keeps running independently.
#
# Site selection (20 of the 70 CONUS sites): the 4 named project-anchor
# sites (evergreen, high_amplitude_deciduous, low_amplitude,
# mixed_forest_grass - already used for physics-guided validation) + the 2
# highest pft_purity sites from each of the 8 PFT classes in
# data/processed/pft_diverse_pixels.csv, so this subset still has full
# vegetation-class coverage for the by-PFT comparison, just thinner than
# the full 70.
import netrc
import time
from pathlib import Path

import pandas as pd
import requests

API = "https://appeears.earthdatacloud.nasa.gov/api"
ROOT = Path(__file__).resolve().parent.parent
PIXELS_CSV = ROOT / "data/conus_gpp/conus70_coords.csv"
OUT_DIR = ROOT / "data/conus_gpp20_gf"
OUT_DIR.mkdir(parents=True, exist_ok=True)
TASK_NAME = "chronos2_conus20_gppgf_v1"

SELECTED_SITES = [
    "evergreen", "high_amplitude_deciduous", "low_amplitude", "mixed_forest_grass",
    "px011_grass_man", "px067_grass_man",
    "px010_grass_nat", "px046_grass_nat",
    "px008_shrubs_bd", "px064_shrubs_bd",
    "px009_shrubs_nd", "px057_shrubs_nd",
    "px007_shrubs_ne", "px053_shrubs_ne",
    "px005_trees_bd", "px063_trees_bd",
    "px006_trees_nd", "px068_trees_nd",
    "px004_trees_ne", "px065_trees_ne",
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
