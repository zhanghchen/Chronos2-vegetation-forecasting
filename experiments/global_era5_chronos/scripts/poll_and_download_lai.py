# Polls the AppEEARS point task submitted by fetch_global_lai_appeears.py
# until it completes, then downloads the result bundle (per-point CSVs) into
# data/global_lai/raw/.
import netrc
import sys
import time
from pathlib import Path

import requests

API = "https://appeears.earthdatacloud.nasa.gov/api"
ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data/global_lai"
RAW_DIR = OUT_DIR / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)


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
            print(f"  [retry {attempt+1}/{max_retries}] login failed: {e} - waiting {wait}s", flush=True)
            time.sleep(wait)
    raise RuntimeError(f"login failed: {last_err}")


def wait_for_task(token, task_id, poll_s=60, max_wait_s=21600):
    headers = {"Authorization": f"Bearer {token}"}
    t0 = time.time()
    while time.time() - t0 < max_wait_s:
        try:
            r = requests.get(f"{API}/task/{task_id}", headers=headers, timeout=30)
            r.raise_for_status()
            status = r.json().get("status")
        except requests.exceptions.RequestException as e:
            print(f"  status check failed: {e} - retrying", flush=True)
            time.sleep(poll_s)
            continue
        print(f"  [{time.time()-t0:.0f}s] status={status}", flush=True)
        if status == "done":
            return True
        if status in ("error", "expired", "deleted"):
            raise RuntimeError(f"Task ended with status={status}")
        time.sleep(poll_s)
    raise TimeoutError(f"Task not done after {max_wait_s}s")


def download_bundle(token, task_id):
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(f"{API}/bundle/{task_id}", headers=headers, timeout=30)
    r.raise_for_status()
    files = r.json()["files"]
    print(f"Bundle has {len(files)} files")
    for f in files:
        file_id, name = f["file_id"], f["file_name"]
        dst = RAW_DIR / name
        if dst.exists():
            continue
        resp = requests.get(f"{API}/bundle/{task_id}/{file_id}", headers=headers, stream=True, timeout=60)
        resp.raise_for_status()
        with open(dst, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=8192):
                fh.write(chunk)
    print(f"Downloaded {len(files)} files to {RAW_DIR}")


def main():
    task_id = (OUT_DIR / "task_id.txt").read_text().strip()
    print(f"Polling task {task_id}...", flush=True)
    token = login()
    wait_for_task(token, task_id)
    token = login()  # refresh in case the wait took a while
    download_bundle(token, task_id)


if __name__ == "__main__":
    main()
