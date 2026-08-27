# A Practical Tutorial: Using Chronos-2 for Scientific Time-Series Forecasting

This tutorial answers one practical question: **given a new time-series dataset, how do I correctly
prepare the data, feed it into Chronos-2, generate forecasts, add covariates, fine-tune the model,
and evaluate the results?**

Everything here has been verified against the current `chronos-forecasting` source code
(`src/chronos/chronos2/{pipeline,dataset,model}.py`) and tested end-to-end on a small synthetic
dataset (`make_synthetic_data.py`). It draws on implementation patterns and debugging lessons from a
real vegetation-forecasting project, generalized so they apply to any domain. Every code path shown
is a real, currently-supported API call — nothing is invented.

**Companion files in this folder**: `chronos2_template.py` (reusable pipeline), `example_config.py`
(a second-domain example), `chronos2_tutorial.ipynb` (runnable notebook), `make_synthetic_data.py`
(generates the example dataset used throughout).

---

## Part 1 — What Chronos-2 Is

Chronos-2 is a pretrained time-series *foundation model*: a single set of weights, trained once on a
large, diverse corpus, that can forecast a new time series it has never seen — **zero-shot**, with no
retraining — by treating forecasting as a sequence-continuation problem, the same way a language
model continues text.

What it supports, concretely:

- **Univariate forecasting** — one target series in, one forecast out.
- **Multivariate forecasting** — several related target series forecast jointly, sharing information
  between them.
- **Past covariates** — auxiliary series observed only up to "now" (e.g. a sensor reading with no
  forecast product).
- **Known future covariates** — auxiliary series whose *future* values are already known when you
  forecast (e.g. a weather forecast, a calendar feature, a planned event schedule).
- **Zero-shot inference** — the default mode: load the pretrained weights, forecast, done.
- **Fine-tuning** — optionally adapt the weights to your dataset with a small amount of gradient
  training (`pipeline.fit(...)`), either updating all weights ("full") or a small LoRA adapter.
- **Cross-learning** — optionally let multiple series in a batch share information with each other at
  inference or fine-tuning time, instead of forecasting each one in isolation.

That's the full theoretical background this tutorial needs. Everything else is shown by example.

---

## Part 2 — Installation and Environment

```bash
# Create a clean environment
conda create -n chronos2-tutorial python=3.11 -y
conda activate chronos2-tutorial

# Core dependencies
pip install chronos-forecasting torch pandas numpy matplotlib scikit-learn

# Optional, only needed if you plan to fine-tune with LoRA (Part 10)
pip install peft
```

`chronos-forecasting` pulls in `transformers` and `huggingface_hub` automatically; the first
`from_pretrained(...)` call downloads the model weights from the Hugging Face Hub and caches them
locally (subsequent loads are instant and offline).

**Loading the pipeline** (works identically on GPU or CPU — just change `device`):

```python
import torch
from chronos import BaseChronosPipeline

device = "cuda" if torch.cuda.is_available() else "cpu"
pipeline = BaseChronosPipeline.from_pretrained("amazon/chronos-2", device_map=device)
```

`BaseChronosPipeline.from_pretrained` reads the model's config and automatically dispatches to the
correct concrete pipeline class (`Chronos2Pipeline` for `amazon/chronos-2`) — this is the same entry
point used in Amazon's own quickstart notebook.

**Verifying the load succeeded:**

```python
assert hasattr(pipeline, "predict_quantiles")
print(f"Default context length: {pipeline.model_context_length}")     # 8192
print(f"Default prediction length: {pipeline.model_prediction_length}") # 1024
print(f"Output patch size: {pipeline.model_output_patch_size}")         # 16
```

If these print without error, the model loaded correctly. `model_context_length` /
`model_prediction_length` are the model's *default* history/horizon lengths — you can request a
shorter or longer horizon per call (Part 3), up to model-specific limits.

---

## Part 3 — The Simplest Possible Example

Start with one univariate series, no covariates:

```python
import numpy as np
import torch
from chronos import BaseChronosPipeline

pipeline = BaseChronosPipeline.from_pretrained("amazon/chronos-2", device_map="cpu")

# historical observations: e.g. 100 time steps of a target variable
history = np.sin(np.linspace(0, 20, 100)) + np.random.normal(0, 0.05, 100)

prediction_length = 12

# Chronos-2's low-level API accepts a plain array/tensor directly for the
# simplest case (no covariates): a list of 1-d series.
quantiles, median = pipeline.predict_quantiles(
    inputs=[history],
    prediction_length=prediction_length,
    quantile_levels=[0.1, 0.5, 0.9],
)

# median[0] has shape (n_variates=1, prediction_length)
point_forecast = median[0][0].numpy()
lower = quantiles[0][0, :, 0].numpy()   # 0.1 quantile
upper = quantiles[0][0, :, 2].numpy()   # 0.9 quantile

print("Point forecast:", point_forecast)
```

```
historical observations
        ↓
   Chronos-2 (zero-shot, no training)
        ↓
   future forecast (median + quantiles)
```

Plotting:

```python
import matplotlib.pyplot as plt

fig, ax = plt.subplots(figsize=(9, 4))
ax.plot(range(len(history)), history, label="History", color="black")
future_x = range(len(history), len(history) + prediction_length)
ax.plot(future_x, point_forecast, label="Forecast (median)", color="#2F6F5E")
ax.fill_between(future_x, lower, upper, color="#2F6F5E", alpha=0.2, label="10-90% interval")
ax.legend(); ax.set_title("Chronos-2 zero-shot forecast")
plt.show()
```

That's the entire minimal workflow. Everything from here on is about correctly *preparing your own
data* to fit this same call.

---

## Part 4 — Adapting Your Own Dataset

This is the section most researchers actually need. The transformation is always the same:

```
Raw dataset
      ↓
Data cleaning        (parse timestamps, sort, drop/flag bad rows)
      ↓
Temporal alignment    (regular time step, no gaps — or gaps explicitly handled)
      ↓
Chronos-2 input format (target / past_covariates / future_covariates dict)
      ↓
Prediction
```

Suppose your raw data looks like either of these (both are common):

```
date, target
2000-01-01, 2.31
2000-01-09, 2.44
...
```

or, with covariates already merged in:

```
date, target, temperature, precipitation, VPD
2000-01-01, 2.31, 14.2, 1.1, 0.62
...
```

**Four roles every column must be sorted into:**

| Role | Meaning | Required? |
|---|---|---|
| **timestamp** | when each row occurred | always |
| **series ID** | which independent series a row belongs to | only if you have more than one series |
| **target** | the variable you want to forecast | always |
| **past covariates** | auxiliary variables observed historically | optional |
| **future covariates** | auxiliary variables whose future values are *already known* | optional, must be a subset of past covariates |

**Expected dataframe shape** (long format — one row per series per timestamp):

```
date         series_id   target   temperature   precipitation   vpd
2000-01-01   site_A      2.31     14.2          1.1             0.62
2000-01-09   site_A      2.44     15.0          0.0             0.71
...
```

Chronos-2's low-level API (`predict`, `predict_quantiles`, `fit`) does **not** consume this dataframe
directly — you convert it into a list of dictionaries, one per series:

```python
item = {
    "target": np.asarray(context_target, dtype="float32"),           # shape (history_length,)
    "past_covariates": {                                             # each value: shape (history_length,)
        "temperature": np.asarray(context_temp, dtype="float32"),
        "precipitation": np.asarray(context_precip, dtype="float32"),
    },
    "future_covariates": {                                           # each value: shape (prediction_length,)
        "temperature": np.asarray(future_temp, dtype="float32"),
        "precipitation": np.asarray(future_precip, dtype="float32"),
    },
}
```

This is exactly what `chronos2_template.prepare_chronos_inputs()` builds for you from a long-format
dataframe — see Part 7.

**Alternative: the dataframe-native API.** Chronos-2 also ships a higher-level, long-format dataframe
API, `pipeline.predict_df(df, future_df=..., id_column=..., timestamp_column=..., target=...)`, which
handles the dict conversion internally: any column in `df` besides the ID/timestamp/target becomes a
past covariate automatically, and any column that *also* appears in `future_df` becomes a known future
covariate. This is the fastest way to get started **if your timestamps are perfectly regular** —
`predict_df` requires strictly regular timestamps and will raise otherwise (see Part 8 and Part 15).
For irregular real-world data (common with satellite composites, clinical visit logs, etc.), use the
lower-level dict API shown above, which tolerates irregular spacing (though see the caveat in Part 8
about what "irregular" means for context length).

---

## Part 5 — Climate / Exogenous Covariates

A concrete, scientifically intuitive example: forecasting a vegetation index (target) from its own
history plus climate drivers.

```
Target:                    Leaf Area Index (LAI)
Historical covariates:     temperature, precipitation, VPD, solar radiation
Known future covariates:   forecast/future temperature, precipitation, VPD, radiation
```

```
Historical LAI ───────────────┐
Historical Climate ───────────┤
                               ├──→  Chronos-2  ──→  Future LAI
Future Climate ────────────────┘
```

**The critical distinction:**

- **`past_covariates`**: values observed up through the end of the historical context. Required for
  *every* covariate the model uses, whether or not it's also known in the future — Chronos-2 needs
  historical covariate values to learn the historical target-covariate relationship, exactly as it
  needs historical target values.
- **`future_covariates`**: values already known for the *forecast horizon itself*. Use this only for
  variables that are genuinely known ahead of time (a numerical weather forecast, a calendar feature,
  a scheduled event) — never for the thing you're trying to predict, and never for a covariate you
  don't actually have real future values for. If you omit a covariate from `future_covariates`
  entirely, Chronos-2 treats it as past-only and does not expect (or use) future values for it.

Complete runnable example:

```python
import numpy as np
from chronos import BaseChronosPipeline

pipeline = BaseChronosPipeline.from_pretrained("amazon/chronos-2", device_map="cpu")

n_hist, horizon = 200, 20
history_lai = np.random.rand(n_hist).astype("float32")
history_temp = np.random.rand(n_hist).astype("float32")
history_precip = np.random.rand(n_hist).astype("float32")
future_temp = np.random.rand(horizon).astype("float32")     # e.g. from a weather forecast
future_precip = np.random.rand(horizon).astype("float32")

inputs = [{
    "target": history_lai,
    "past_covariates": {"temperature": history_temp, "precipitation": history_precip},
    "future_covariates": {"temperature": future_temp, "precipitation": future_precip},
}]

quantiles, median = pipeline.predict_quantiles(inputs=inputs, prediction_length=horizon)
forecast = median[0][0].numpy()
```

**A covariate observed but not known in the future** (e.g. a lab measurement with no forecast
product) simply gets left out of `future_covariates`:

```python
inputs = [{
    "target": history_lai,
    "past_covariates": {"temperature": history_temp, "soil_moisture_sensor": history_soil},
    "future_covariates": {"temperature": future_temp},   # soil_moisture_sensor omitted — past-only
}]
```

---

## Part 6 — Multiple Series, Multiple Variables, and Cross-Learning

Chronos-2 distinguishes several related but different concepts — conflating them is a common source
of confusion:

1. **One target series** — the basic case above.
2. **Multiple covariates on one target** — shown in Part 5; each covariate is one more entry in
   `past_covariates`/`future_covariates`, all attached to the same target.
3. **Multiple target series forecast jointly (multivariate)** — pass `target` as a 2-D array
   `(n_variates, history_length)`; the model shares information *within* that one task while
   forecasting all variates together. Use this when the variates are genuinely part of the same
   system (e.g. multiple correlated sensor channels on one machine).
4. **Multiple independent series** (e.g. many locations, patients, or sensors, each with their own
   target + covariates) — pass a **list** with one dict per series. By default each is forecast
   **independently** — nothing is shared between them.

For case 4 (the common "many pixels / many patients / many stores" scenario), two different
mechanisms control what's shared:

- **`id_column` / `timestamp_column` / `target`** (used with the dataframe API, `predict_df`) simply
  tell Chronos-2 how to *parse* your long-format dataframe into separate series — they do not, by
  themselves, cause any information sharing between series.
- **`cross_learning=True`** (a real parameter of `predict`, `predict_quantiles`, and `predict_df`) is
  what actually enables sharing: when set, all series in the same batch are forecast *jointly*, and
  the model can use patterns from one series to help forecast another. Per the official docstring:
  cross-learning does not always improve accuracy and should be validated per use case; results become
  batch-size-dependent (Amazon's own technical report used ~100 series per batch); it helps most when
  individual series have limited historical context.

```python
# 3 independent locations, each with its own target + climate history —
# by default forecast independently (cross_learning=False, the default)
inputs = [
    {"target": lai_site_a, "past_covariates": {"temperature": temp_a}, "future_covariates": {"temperature": future_temp_a}},
    {"target": lai_site_b, "past_covariates": {"temperature": temp_b}, "future_covariates": {"temperature": future_temp_b}},
    {"target": lai_site_c, "past_covariates": {"temperature": temp_c}, "future_covariates": {"temperature": future_temp_c}},
]
quantiles, median = pipeline.predict_quantiles(inputs=inputs, prediction_length=20)
# median[i] corresponds to inputs[i], in order

# Same call, but let the 3 series share information at inference time:
quantiles, median = pipeline.predict_quantiles(inputs=inputs, prediction_length=20, cross_learning=True)
```

`group_ids` is a related, lower-level concept used internally by the `Chronos2Dataset`/model machinery
to control which rows attend to each other (it is how a series' own covariates get associated with its
own target). If you're using the list-of-dicts input format shown throughout this tutorial, you do not
need to set `group_ids` yourself — it's handled for you.

---

## Part 7 — A General, Reusable Data Adapter

`chronos2_template.py` in this folder is a ready-to-copy template. Edit only the CONFIG block:

```python
TARGET = "LAI"
PAST_COVARIATES = ["temperature", "precipitation", "vpd"]
FUTURE_COVARIATES = ["temperature", "precipitation", "vpd"]
ID_COLUMN = "pixel_id"
TIMESTAMP_COLUMN = "date"
FREQ = "8D"
PREDICTION_LENGTH = 46
```

...and reuse the rest of the pipeline unchanged:

```python
import chronos2_template as ct

df = ct.load_data("data/my_dataset.csv")
report = ct.validate_data(df)                 # checks columns, NaNs, timestamp regularity
df = ct.align_frequency(df)                   # only if validate_data() flagged irregular timestamps

split_date = df[df[ct.ID_COLUMN] == df[ct.ID_COLUMN].iloc[0]][ct.TIMESTAMP_COLUMN].iloc[-ct.PREDICTION_LENGTH]
inputs, ground_truth, future_dates = ct.prepare_chronos_inputs(df, split_date)

pipeline = ct.load_pipeline()                 # auto-selects GPU if available
quantiles, median = ct.run_forecast(pipeline, inputs)

for i, series_id in enumerate(sorted(df[ct.ID_COLUMN].unique())):
    pred = median[i][0].numpy()
    metrics = ct.evaluate_forecast(ground_truth[series_id], pred)
    ct.plot_forecast(future_dates[series_id], ground_truth[series_id], pred, title=series_id)
    print(series_id, metrics)
```

The seven functions provided (`load_data`, `validate_data`, `align_frequency`,
`prepare_chronos_inputs`, `run_forecast`, `evaluate_forecast`, `plot_forecast` +
`plot_scatter`/`plot_residuals`) are written generically against the CONFIG constants — adapting to a
new dataset should require editing only the CONFIG block. See `example_config.py` for a worked example
adapting the same template to hourly electricity demand.

---

## Part 8 — Different Temporal Resolutions

Chronos-2 has no built-in notion of calendar time — `context_length` and `prediction_length` are
**counts of time steps**, not days or months. The model does not know or care whether one step means
one hour, one day, or one 8-day composite; that meaning is entirely up to how you built the series.

| Resolution | Example `FREQ` | Notes |
|---|---|---|
| Hourly | `"h"` | Watch for daylight-saving jumps if using naive timestamps |
| Daily | `"D"` | Simplest case, usually already regular |
| 8-day (satellite composites) | `"8D"` | The last composite of a calendar year is often shorter — see below |
| Weekly | `"W"` | |
| Monthly | `"MS"` | Irregular *day counts* per step, but a regular *step count* — usually fine |

**Regular vs. missing timestamps.** A "regular" series means every step is the same duration apart.
Real-world data frequently isn't: sensors drop out, satellite composites' last period of the year is
short, clinical visits are irregular. `validate_data()` in the template flags this; `align_frequency()`
reindexes onto a strict grid and interpolates small gaps. **Do not skip this step** if you plan to use
`predict_df`, which requires regular timestamps outright and will raise an error otherwise. The
lower-level dict API is more forgiving — it treats whatever sequence you give it as consecutive steps,
regardless of the real elapsed time between them — but that forgiveness is also a trap: if you feed it
an irregularly-spaced series without realizing it, the model will silently treat unequal time gaps as
equal, which can distort both the learned seasonal pattern and the effective horizon of "hlength
`prediction_length` steps ahead."

**Context length and prediction length, worked example.** For 8-day LAI composites:

```
15 historical observations  ≈  15 × 8  = 120 days of history
prediction_length = 15      ≈  15 × 8  = 120 days forecast horizon
```

If you want roughly a "1-year-ahead" forecast at this resolution, that's about `365 / 8 ≈ 46` steps —
**not** `prediction_length=365`. Getting this conversion wrong (passing a day-count where a step-count
is expected) is one of the most common mistakes when moving between datasets of different resolution;
see Part 15.

---

## Part 9 — Zero-Shot Forecasting

Zero-shot means: load the pretrained weights, forecast immediately, **no parameter updates at all**.

```
Pretrained Chronos-2  +  new dataset  →  prediction
                    (no training)
```

```python
pipeline = BaseChronosPipeline.from_pretrained("amazon/chronos-2", device_map="cpu")
quantiles, median = pipeline.predict_quantiles(inputs=inputs, prediction_length=prediction_length)
```

**Always run zero-shot first, before considering fine-tuning.** This is a general methodological
recommendation, not specific to any one dataset: zero-shot costs nothing to try (no training time, no
hyperparameter search, no risk of overfitting a small dataset), gives you an immediate, honest baseline
number to compare anything else against, and — in practice, across a range of forecasting tasks with
limited fine-tuning data — often turns out to be very hard to beat. Skipping straight to fine-tuning
means you have no way of knowing whether any complexity you add afterward is actually earning its
keep.

---

## Part 10 — Fine-Tuning Chronos-2

If zero-shot isn't sufficient, Chronos-2 exposes fine-tuning through `pipeline.fit(...)`. Verified
directly from the current source (`src/chronos/chronos2/pipeline.py`):

```python
finetuned_pipeline = pipeline.fit(
    inputs=[train_item],              # same format as predict()'s inputs
    prediction_length=prediction_length,
    validation_inputs=[val_item],     # optional but strongly recommended — see Part 11
    finetune_mode="lora",             # "full" (default) or "lora" — both officially supported
    learning_rate=1e-5,               # library recommends ~1e-5 for LoRA, notes full fine-tuning
                                       # typically needs a much smaller value (default 1e-6)
    num_steps=1000,
    batch_size=32,
    context_length=None,              # defaults to the model's own context length
    output_dir="./chronos2-finetuned",
)
```

Key parameters, verified against the current signature:

| Parameter | Meaning |
|---|---|
| `inputs` | Training series, same list-of-dicts format as `predict()`. Note: `future_covariates`' *values* aren't used for training, but the *keys present* tell Chronos-2 which covariates are known-future — include the key (values can be `None`/empty) if that's true of your task. |
| `prediction_length` | The horizon the model is fine-tuned to forecast. |
| `validation_inputs` | Same format as `inputs`. When provided, automatically enables step-based evaluation, checkpointing, and `load_best_model_at_end=True` (best validation loss, not the final step) — see Part 11. |
| `finetune_mode` | `"full"` (updates all weights, the default) or `"lora"` (trains a small low-rank adapter, requires `peft`). |
| `lora_config` | Optional `peft.LoraConfig` (or dict) when `finetune_mode="lora"`; a sensible default (`r=8, lora_alpha=16`, targeting attention + output projections) is used if omitted. |
| `learning_rate` | Default `1e-6` for full fine-tuning; the library's own docstring recommends a higher value (e.g. `1e-5`) for LoRA specifically. |
| `num_steps` | Total training steps (default 1000). |
| `batch_size` | Number of *time series* (targets + covariates combined) per batch, default 256 — with several covariates per target, the effective number of independent forecasting tasks per batch is lower than this number. |
| `context_length` | Max context length used during fine-tuning; defaults to the model's own. |

**Officially supported modes**: the signature is `finetune_mode: Literal["full", "lora"] = "full"` —
both are real, current options. LoRA fine-tunes far fewer parameters (a small adapter) and is
generally cheaper and less prone to overfitting on small datasets; full fine-tuning updates every
weight and needs a correspondingly smaller learning rate and more data to avoid destroying the
pretrained representation.

**Practical lesson**: across a range of parameter-efficient fine-tuning strategies tested in the
vegetation-forecasting project this tutorial draws on, **trainable parameter count alone did not
predict which method performed best** — a smaller-capacity adapter sometimes outperformed a
much-larger-capacity one, and vice versa. Don't assume "more trainable parameters = better fine-tune";
treat capacity as one more hyperparameter to validate, not a lever to maximize.

---

## Part 11 — Train / Validation / Test Splits (Read This Before Fine-Tuning)

This is the section most likely to silently invalidate a result if skipped.

**Never randomly split individual timestamps** for a forecasting task. A forecaster's job is to
predict the future from the past; a random split lets the model "train" on timestamps that occur
*after* some of its "test" timestamps, which is temporal leakage — the model can implicitly learn
information that would never be available at real forecast time, making validation/test metrics
overoptimistic in a way that won't reproduce in real use.

**Correct approach: chronological splits.**

```
2000–2019   →   Training
2020–2021   →   Validation   (used to pick hyperparameters / checkpoints)
2022        →   Test         (touched exactly once, at the very end)
```

**Rolling validation windows** give a more robust hyperparameter/checkpoint choice than a single
validation year, at some extra compute cost:

```
Train              →  Validate
2000–2017          →  2018
2000–2018          →  2019
2000–2019          →  2020
2000–2020          →  2021
```

then, only after every modeling decision is locked in:

```
Final refit on 2000–2021  →  evaluate once on 2022
```

```python
# Chronos-2's own validation mechanism, wired through fit():
finetuned = pipeline.fit(
    inputs=[build_input(df, end_year=2019)],
    validation_inputs=[build_input(df, end_year=2020)],  # a genuinely later, held-out window
    prediction_length=prediction_length,
    finetune_mode="lora",
    num_steps=1000,
)
# fit() with validation_inputs set automatically enables load_best_model_at_end=True,
# selecting by minimum validation loss - not just whatever weights exist after num_steps.
```

**The single most important rule**: once you've picked your final method, architecture, and
hyperparameters using only pre-test data, evaluate on the true test year **exactly once**. Going back
to re-check the test year and adjusting your approach based on what you see there quietly turns the
"test" set into another validation set — and defeats the purpose of holding it out at all.

---

## Part 12 — Evaluation

```python
from math import sqrt
import numpy as np
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score

def evaluate_forecast(y_true, y_pred):
    y_true, y_pred = np.asarray(y_true, dtype=float), np.asarray(y_pred, dtype=float)
    return {
        "RMSE": sqrt(mean_squared_error(y_true, y_pred)),   # error magnitude, same units as target, penalizes large errors
        "MAE": mean_absolute_error(y_true, y_pred),         # average absolute error, robust to outliers
        "R2": r2_score(y_true, y_pred),                     # variance explained (1=perfect, 0=no better than the mean, <0=worse)
        "Pearson_r": float(np.corrcoef(y_true, y_pred)[0, 1]),  # linear correlation, scale/bias-independent
    }
```

(`chronos2_template.evaluate_forecast` is this same function, with NaN-masking added.)

**Recommended plots** (all provided in `chronos2_template.py`):

- **Observed vs. predicted time series** (`plot_forecast`) — the primary sanity check; look for
  systematic timing offsets (peaks predicted too early/late) as well as magnitude errors.
- **Scatter: observed vs. predicted** (`plot_scatter`) — points should cluster around the 1:1 line;
  systematic curvature suggests a bias the aggregate metrics might hide.
- **Residual plot** (`plot_residuals`) — predicted minus observed over time; a residual pattern that
  tracks the seasonal cycle (rather than looking like noise) usually means the model is systematically
  mis-timing or mis-scaling the seasonal signal, not just adding random error.
- **Optional: seasonal/phase-binned error** — group residuals by month or phenological phase
  (e.g. green-up / peak / senescence for a vegetation index) to check whether error is concentrated in
  a specific part of the cycle rather than spread evenly.

---

## Part 13 — Complete Example: Vegetation Index (LAI) Forecasting

A full, runnable, end-to-end example using generic paths (`data/lai.csv`, `data/climate.csv`) —
substitute your own files with the same column structure.

```python
import pandas as pd
import numpy as np
import chronos2_template as ct

# --- 1. Raw data ---
lai = pd.read_csv("data/lai.csv", parse_dates=["date"])          # columns: date, pixel_id, LAI
climate = pd.read_csv("data/climate.csv", parse_dates=["date"])  # columns: date, pixel_id, temperature, precipitation, vpd, radiation

# --- 2. Merge + configure ---
df = lai.merge(climate, on=["date", "pixel_id"], how="inner")

ct.TARGET = "LAI"
ct.PAST_COVARIATES = ["temperature", "precipitation", "vpd", "radiation"]
ct.FUTURE_COVARIATES = ["temperature", "precipitation", "vpd", "radiation"]
ct.ID_COLUMN = "pixel_id"
ct.TIMESTAMP_COLUMN = "date"
ct.FREQ = "8D"
ct.PREDICTION_LENGTH = 46   # roughly one year at an 8-day step, see Part 8

# --- 3. Preprocessing + temporal alignment ---
report = ct.validate_data(df)
if not report.ok:
    df = ct.align_frequency(df)

# --- 4. Chronos-2 input construction (chronological split, see Part 11) ---
test_year = 2022
split_date = pd.Timestamp(f"{test_year}-01-01")
inputs, ground_truth, future_dates = ct.prepare_chronos_inputs(df, split_date)

# --- 5. Zero-shot prediction (always run this first, Part 9) ---
pipeline = ct.load_pipeline()
quantiles, median = ct.run_forecast(pipeline, inputs, prediction_length=ct.PREDICTION_LENGTH)

# --- 6. Evaluation + visualization ---
pixel_ids = sorted(df[ct.ID_COLUMN].unique())
for i, pid in enumerate(pixel_ids):
    pred = median[i][0].numpy()
    metrics = ct.evaluate_forecast(ground_truth[pid], pred)
    print(pid, metrics)
    ct.plot_forecast(future_dates[pid], ground_truth[pid], pred, title=f"{pid}: {test_year} forecast")
```

This mirrors, in generalized form, the structure that a real LAI-from-climate forecasting pipeline
uses in practice: merge target and covariates, validate temporal structure, split chronologically,
forecast zero-shot first, then evaluate before considering anything more complex.

---

## Part 14 — Switching to a Completely Different Dataset

Chronos-2 has no notion of what your target variable *means*. The same pipeline applies whether the
series is called `LAI`, `demand_mw`, or `heart_rate` — only the CONFIG block changes:

| Domain | `TARGET` | Covariates |
|---|---|---|
| Electricity | `demand_mw` | temperature, hour-of-day, weekday flag |
| Healthcare | a physiological measurement | other clinical variables, medication timing |
| Weather | `temperature` | humidity, pressure, wind speed |
| Vegetation | `LAI` | temperature, precipitation, VPD, radiation |

See `example_config.py` for the electricity example worked out in full. In every case, the researcher's
job is the same six-item checklist:

```
TARGET            — what to forecast
COVARIATES        — what auxiliary information is available, and whether it's known in the future
TIMESTAMP         — how time is represented, and at what resolution
SERIES ID         — whether there's one series or many
CONTEXT LENGTH     — how much history to condition on (Part 8)
FORECAST HORIZON   — how many steps ahead, and over what real-world time span (Part 8)
```

Get these six things right and the rest of the pipeline (Parts 3–13) is domain-agnostic.

---

## Part 15 — Common Pitfalls

| Symptom | Possible cause | How to check | How to fix |
|---|---|---|---|
| Forecast looks shifted in time | Temporal resolution mismatch (e.g. treating daily data as if it were 8-day) | Print `len(context)` vs. real elapsed days; compare `FREQ` to actual timestamp deltas | Recompute `PREDICTION_LENGTH`/`context_length` in *steps*, not days (Part 8) |
| `ValueError: ... must be 1-d with length equal to prediction_length` | Off-by-one in a date-based train/test split | Print `len(future_covariates[...])` vs. `prediction_length` before calling `predict` | Split by exact row count (`.iloc[-N:]`), not by a calendar date, when step-count precision matters |
| Model raises on NaN in `future_covariates` | A genuinely-future-unknown variable was mistakenly included as a known future covariate | Check whether the variable really has real values available at real forecast time | Move it to past-only (omit from `future_covariates`), or provide a `future_covariates_mask` |
| `predict_df` raises about irregular timestamps | Real gaps or inconsistent step sizes in the source data | `validate_data()`'s irregularity check (Part 15 companion, or manually diff timestamps per series) | `align_frequency()` first, or switch to the lower-level dict API which tolerates irregular spacing (with the caveat in Part 8) |
| Zero-shot and fine-tuned results look identical/near-identical for a static-like covariate | The covariate is (near-)constant over time within a series | Check `covariate.std()` within a single series' context window | See Part 16 — static covariates need different handling entirely |
| Future-data leakage (suspiciously good validation results) | Validation window overlaps or follows training data incorrectly, or the test year was used to pick a checkpoint/hyperparameter | Re-derive the exact date ranges used for train/val/test; confirm test year is never referenced before the single final evaluation | Rebuild the split from Part 11's pattern; never use test-year metrics to make any decision |
| Fine-tuning doesn't beat zero-shot | Too little fine-tuning data relative to model/adapter capacity; near-optimal pretrained baseline for this task | Compare zero-shot vs. fine-tuned on a *validation* window before ever touching the test year; check validation loss curve shape | Always keep the zero-shot baseline as the comparison point (Part 9); consider a smaller-capacity adapter or more data before concluding fine-tuning helps |
| Validation loss rises immediately during fine-tuning | Overfitting — too few independent training examples for the amount of trainable capacity | Plot train vs. validation loss per step; check if validation is lowest at step 0 | Use `validation_inputs` + early stopping (Part 11); reduce capacity/LR; get more independent training windows |
| GPU out-of-memory during fine-tuning/inference | `batch_size` or `context_length` too large for available GPU memory, or another process is using the GPU | `nvidia-smi`; try a smaller `batch_size` | Reduce `batch_size`; explicitly pin `CUDA_VISIBLE_DEVICES` to a free GPU; use `device_map="cpu"` for small jobs |
| Model ignores a covariate you added | See Part 16 — this is very often a static-feature/normalization issue, not a "the model can't learn it" issue | Perturb the covariate while holding everything else fixed and check if the forecast changes at all | See Part 16 |
| "Adding more covariates should help" but it doesn't | Not every covariate carries independent, learnable signal; more covariates can also dilute or add noise | Compare a with/without-covariate ablation on a validation window, not just eyeballing the change | Treat covariate selection as an empirical question, not an assumption — validate additions the same way you'd validate a hyperparameter |

---

## Part 16 — Static Features Require Special Attention

A **static feature** — vegetation type, soil type, a location category, a patient demographic group, a
sensor model — describes a whole series rather than varying over time within it. This deserves a
dedicated warning because it interacts poorly with a mechanism most users won't think to check:
**per-series normalization.**

Chronos-2 normalizes each input series (target *and* each covariate) using statistics computed from
*that series' own values*. If a "covariate" is constant across the entire context window —

```
[0.65, 0.65, 0.65, 0.65, ...]   ← broadcasting a static value across every timestep
```

— its own variance is exactly zero. A per-series normalization step computing `(x - mean) / std`
cannot meaningfully divide by a zero standard deviation; whatever fallback the implementation uses to
avoid a divide-by-zero (commonly substituting a tiny fixed constant for the denominator) effectively
maps every value of that constant covariate to the same normalized output — so the model receives
essentially the same input regardless of what the actual static value was. In other words: **naively
broadcasting a static feature across time and feeding it in as an ordinary covariate does not
reliably work**, and a normalization step is very often the reason, whether or not it's the specific
mechanism your model of choice uses.

**Check this before assuming a model can use a static feature**: does the modeling framework's own
normalization/preprocessing operate per-series? If so, verify directly (e.g. perturb the static value
while holding everything else fixed, and check whether the output changes at all) rather than assuming
it will "just work" because the covariate has the right shape.

**Chronos-2 specifically**: the current public API supports categorical covariates that *change value
over time* (e.g. day-of-week, a shifting weather regime) — these are encoded numerically (target
encoding for a single continuous target, ordinal encoding otherwise) and passed through the normal
covariate channel, which is genuinely useful. This is a **different** feature from static-per-series
information, and does not solve the static-feature problem above: a categorical value that happens to
be constant for the entire series is still constant after encoding, and is still subject to the same
per-series normalization. As of the current API, Chronos-2 does not expose a dedicated static-feature
input that bypasses per-series normalization; a workaround requires either genuine temporal variation
in the covariate (constant-only-within-a-series but varying *across* many pooled series does not, by
itself, help an individual series' own normalization) or a custom architecture-level modification that
injects the static information downstream of normalization — a nontrivial undertaking, and worth
confirming is actually necessary (via the perturbation check above) before investing in it.

---

## Part 17 — Recommended Workflow

```
Step 1   Inspect the dataset (columns, dtypes, date range, missingness)
Step 2   Identify target and covariates; classify each covariate as past-only or known-future
Step 3   Align temporal resolution (regular timestamps; resample/interpolate if needed)
Step 4   Check missing values (target and covariates, per series)
Step 5   Create a chronological train / validation / test split (never random-by-timestamp)
Step 6   Run zero-shot Chronos-2 as the first baseline
Step 7   Evaluate (RMSE / MAE / R² / Pearson r + plots)
Step 8   Add covariates one group at a time, if useful
Step 9   Compare each addition against the zero-shot baseline on the VALIDATION set
Step 10  Only then consider fine-tuning (full or LoRA)
Step 11  Validate fine-tuning carefully (rolling windows, early stopping, no test-year peeking)
Step 12  Evaluate the finalized method ONCE on the held-out test set
```

```
 ┌──────────┐   ┌───────────┐   ┌──────────┐   ┌─────────┐   ┌───────────┐
 │ Inspect  │→ │ Identify  │→ │  Align   │→ │  Check  │→ │  Train /  │
 │ dataset  │  │ target &  │  │ temporal │  │ missing │  │ val / test │
 │          │  │covariates │  │resolution│  │ values  │  │   split   │
 └──────────┘   └───────────┘   └──────────┘   └─────────┘   └─────┬─────┘
                                                                     ↓
 ┌───────────┐   ┌──────────┐   ┌───────────┐   ┌─────────┐   ┌───────────┐
 │ Evaluate  │← │ Compare  │← │Add useful │← │Evaluate │← │ Zero-shot │
 │   once,   │  │ vs. zero │  │covariates │  │         │  │ Chronos-2 │
 │   final   │  │  -shot   │  │           │  │         │  │           │
 │ test set  │  └──────────┘   └───────────┘   └─────────┘   └───────────┘
      ↑
 ┌────┴─────┐   ┌───────────┐
 │ Validate │← │  Consider │
 │carefully │  │fine-tuning│
 └──────────┘   └───────────┘
```

---

## Reference: API surface used in this tutorial

All verified against `src/chronos/chronos2/{pipeline,dataset}.py` in the currently installed
`chronos-forecasting` package.

- `BaseChronosPipeline.from_pretrained(model_id, device_map=...)`
- `pipeline.predict(inputs, prediction_length=None, batch_size=256, context_length=None, cross_learning=False, ...)`
- `pipeline.predict_quantiles(inputs, prediction_length=None, quantile_levels=[...], ...)` → `(quantiles, median)`
- `pipeline.predict_df(df, future_df=None, id_column="item_id", timestamp_column="timestamp", target="target", prediction_length=None, cross_learning=False, ...)` → long-format forecast dataframe
- `pipeline.fit(inputs, prediction_length, validation_inputs=None, finetune_mode="full"|"lora", lora_config=None, learning_rate=1e-6, num_steps=1000, batch_size=256, context_length=None, output_dir=None, ...)` → a new, fine-tuned pipeline
- `pipeline.model_context_length`, `pipeline.model_prediction_length`, `pipeline.model_output_patch_size`
