# Chronos-2 Tutorial

A practical, verified tutorial for applying Chronos-2 (Amazon's time-series foundation model) to a
new scientific time-series dataset: data preparation, zero-shot forecasting, covariates, multi-series
setups, fine-tuning, evaluation, and common pitfalls.

This folder is self-contained and uses only a small synthetic example dataset generated locally — no
external data, credentials, or private paths are required to run it.

## Contents

| File | What it is |
|---|---|
| `TUTORIAL.md` | The full 17-part written tutorial. Start here. |
| `chronos2_tutorial.ipynb` | Runnable notebook version of the core workflow. |
| `chronos2_template.py` | Reusable pipeline: edit the CONFIG block, reuse the 7 helper functions on any dataset. |
| `example_config.py` | Worked example adapting the template to a different domain (electricity demand). |
| `make_synthetic_data.py` | Generates the example dataset used by the notebook and tutorial (`data/example_timeseries.csv`). |
| `build_notebook.py` | Regenerates `chronos2_tutorial.ipynb` from source (only needed if you edit the notebook's content programmatically). |

## Quickstart

```bash
# 1. Create and activate a clean environment
conda create -n chronos2-tutorial python=3.11 -y
conda activate chronos2-tutorial

# 2. Install dependencies
pip install chronos-forecasting torch pandas numpy matplotlib scikit-learn jupyter

# 3. (Optional) LoRA fine-tuning support
pip install peft

# 4. Generate the example dataset
cd tutorial
python make_synthetic_data.py

# 5a. Run the notebook
jupyter notebook chronos2_tutorial.ipynb

# 5b. — or run the equivalent as a plain script
python -c "
import chronos2_template as ct
df = ct.load_data('data/example_timeseries.csv')
ct.validate_data(df)
split = df[df[ct.ID_COLUMN]==df[ct.ID_COLUMN].iloc[0]][ct.TIMESTAMP_COLUMN].iloc[-ct.PREDICTION_LENGTH]
inputs, gt, dates = ct.prepare_chronos_inputs(df, split)
pipeline = ct.load_pipeline()
q, m = ct.run_forecast(pipeline, inputs)
print(ct.evaluate_forecast(gt[sorted(gt)[0]], m[0][0].numpy()))
"
```

The first `load_pipeline()` call downloads and caches the `amazon/chronos-2` weights from the Hugging
Face Hub (a few GB); subsequent runs are instant and work offline.

## Adapting to your own dataset

1. Put your data in long format: one row per `(series, timestamp)`, with a target column and any
   covariate columns (see `TUTORIAL.md` Part 4 for the exact required shape).
2. Copy `chronos2_template.py` into your own project (or edit this copy in place).
3. Edit the six-line CONFIG block at the top: `TARGET`, `PAST_COVARIATES`, `FUTURE_COVARIATES`,
   `ID_COLUMN`, `TIMESTAMP_COLUMN`, `FREQ`, `PREDICTION_LENGTH`. See `example_config.py` for a worked
   second example.
4. Run the same `load_data → validate_data → align_frequency → prepare_chronos_inputs →
   load_pipeline → run_forecast → evaluate_forecast → plot_forecast` sequence — nothing else needs to
   change.

Read `TUTORIAL.md` Part 17 for the recommended end-to-end workflow (inspect → split → zero-shot →
evaluate → add covariates → only then fine-tune → validate → test once), and Part 15 for a
troubleshooting table if something doesn't work as expected.

## Requirements

- Python ≥ 3.9
- `chronos-forecasting` (installs `torch`, `transformers`, `huggingface_hub` as dependencies)
- `pandas`, `numpy`, `scikit-learn`, `matplotlib`
- `peft` (only if using `finetune_mode="lora"` in Part 10)
- `jupyter` (only to run the notebook interactively)

A GPU is not required — everything in this tutorial runs on CPU, just slower. Set
`device_map="cuda"` (or leave `device=None` in `chronos2_template.load_pipeline` for
auto-detection) to use a GPU if one is available.
