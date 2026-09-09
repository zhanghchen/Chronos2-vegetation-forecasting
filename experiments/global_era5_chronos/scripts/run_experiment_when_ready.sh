#!/bin/bash
# Waits for the ERA5 fetch supervisor's DONE_MARKER to appear (i.e. for
# fetch_era5_point_daily to have every needed variable/year cached for the
# evergreen validation pixel), then automatically runs the actual Chronos-2
# zero-shot experiment on that data (Part 7 validation) - no need for a
# human to be watching at the exact moment the download finishes. Resilient
# to environment teardowns the same way run_era5_fetch_supervised.sh is
# (poll-and-retry loop, not a single long sleep), and idempotent: skips
# straight to printing the existing result if it's already been run.
cd "$(dirname "$0")"
# NOTE: this must be the chronos2 conda env, not base python3 -- base's
# `chronos` package is a different, incompatible package lacking
# BaseChronosPipeline (confirmed by direct import test), even though base
# also happens to have torch and an unrelated `chronos` installed.
PYTHON=/home/deh25003/miniconda3/envs/chronos2/bin/python3
LOGDIR=/gpfs/sharedfs1/vscode_temp/claude-1024136/-home-deh25003-chronos-forecasting/7e05eaf0-dc4c-49b9-9938-e50cb41eb412/scratchpad
DONE_MARKER=/home/deh25003/chronos-forecasting/Chronos2-vegetation-forecasting/experiments/global_era5_chronos/data/era5/processed/evergreen_era5_daily.csv
RESULT_MARKER=/home/deh25003/chronos-forecasting/Chronos2-vegetation-forecasting/experiments/global_era5_chronos/results/evergreen/metrics_era5.txt
LOG=$LOGDIR/era5_experiment_autorun.log

echo "=== autorun: waiting for ERA5 fetch to complete, started at $(date) ===" >> "$LOG"

while [ ! -f "$DONE_MARKER" ]; do
  sleep 60
done

echo "=== autorun: DONE_MARKER found at $(date), running Chronos-2 zero-shot experiment ===" >> "$LOG"

if [ -f "$RESULT_MARKER" ]; then
  echo "=== autorun: result already exists at $RESULT_MARKER, not re-running ===" >> "$LOG"
else
  $PYTHON run_era5_chronos.py --lat 30.525 --lon -82.4333 --site evergreen \
      --era5-years 2021 2022 --test-year 2022 >> "$LOG" 2>&1
  echo "=== autorun: experiment finished at $(date), exit code $? ===" >> "$LOG"
fi
