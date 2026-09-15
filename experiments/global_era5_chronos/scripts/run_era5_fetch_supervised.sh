#!/bin/bash
# Supervisor loop for the ERA5 fetch: this environment has repeatedly
# killed background python processes via full teardowns (not just SIGHUP -
# nohup/setsid alone don't protect against it). Since era5_source.py's
# download is fully resumable (cached per variable/statistic/location/
# year), the safe fix is to keep relaunching the fetch until it actually
# finishes, rather than relying on any single long-lived process to
# survive uninterrupted for the hours this can take.
#
# Generalized (was hardcoded to the evergreen pixel) so it can be reused
# for the remaining Part 7 validation pixels without copy-pasting a new
# script per site. Usage:
#   run_era5_fetch_supervised.sh <site> <lat> <lon> <year> [<year> ...]
# IMPORTANT: never run two instances of this script (for the same or
# different sites) concurrently -- the CDS account allows exactly one
# request in flight at a time; a second instance will just collide with
# the first and both will fail with 403 Forbidden.
set -e
SITE="$1"; LAT="$2"; LON="$3"; shift 3
if [ -z "$SITE" ] || [ -z "$LAT" ] || [ -z "$LON" ] || [ -z "$1" ]; then
  echo "Usage: $0 <site> <lat> <lon> <year> [<year> ...]" >&2
  exit 1
fi
YEARS_CSV=$(IFS=,; echo "$*")

cd "$(dirname "$0")"
PYTHON=/home/deh25003/miniconda3/bin/python3
LOGDIR=/gpfs/sharedfs1/vscode_temp/claude-1024136/-home-deh25003-chronos-forecasting/7e05eaf0-dc4c-49b9-9938-e50cb41eb412/scratchpad
LOG="$LOGDIR/era5_supervisor_${SITE}.log"
DONE_MARKER=/home/deh25003/chronos-forecasting/Chronos2-vegetation-forecasting/experiments/global_era5_chronos/data/era5/processed/${SITE}_era5_daily.csv

attempt=0
while [ ! -f "$DONE_MARKER" ]; do
  attempt=$((attempt+1))
  echo "=== supervisor[$SITE]: attempt $attempt at $(date) ===" >> "$LOG"
  $PYTHON -u -c "
import time
import era5_source as es
t0 = time.time()
df = es.build_gridmet_equivalent($LAT, $LON, [$YEARS_CSV])
df.to_csv('$DONE_MARKER')
print(f'DONE in {time.time()-t0:.0f}s, shape={df.shape}', flush=True)
print(df.describe(), flush=True)
" >> "$LOG" 2>&1
  sleep 5
done
echo "=== supervisor[$SITE]: DONE_MARKER found, exiting at $(date) ===" >> "$LOG"
