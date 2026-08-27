# example_config.py
#
# Demonstrates adapting chronos2_template.py to a COMPLETELY different
# domain - hourly electricity demand instead of 8-day vegetation LAI - by
# changing only the CONFIG block. Nothing else in the pipeline needs to
# change: Chronos-2 does not know or care whether the target is called
# "LAI" or "demand_mw".
#
# Usage:
#   import example_config as cfg   # instead of using chronos2_template's
#                                   # own module-level CONFIG constants
#   # then pass cfg.TARGET, cfg.PAST_COVARIATES, etc. explicitly to the
#   # chronos2_template functions, OR copy this block over the CONFIG
#   # section at the top of chronos2_template.py directly.

TIMESTAMP_COLUMN = "timestamp"
ID_COLUMN = "grid_zone"
TARGET = "demand_mw"

# Past-only covariate: actual historical temperature (no forecast used downstream).
# Known-future covariates: calendar features are known perfectly for any future
# timestamp, so they belong in both lists.
PAST_COVARIATES = ["temperature", "hour_of_day", "is_weekend"]
FUTURE_COVARIATES = ["hour_of_day", "is_weekend"]  # temperature forecast not assumed available here;
                                                     # add "temperature" to this list too if you have a
                                                     # weather forecast product for the future window

FREQ = "h"                 # hourly
PREDICTION_LENGTH = 168     # 168 hourly steps = 1 week ahead
CONTEXT_LENGTH = None        # use the model default

# Expected raw dataframe columns for this example:
#   timestamp, grid_zone, demand_mw, temperature, hour_of_day, is_weekend
#
# To use: copy these six settings over the CONFIG block in
# chronos2_template.py (or point a fresh copy of that file at this
# dataset), then run the same load_data -> validate_data -> align_frequency
# -> prepare_chronos_inputs -> run_forecast -> evaluate_forecast ->
# plot_forecast pipeline unchanged.
