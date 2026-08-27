# Builds chronos2_tutorial.ipynb programmatically (via nbformat) so the
# cell content is guaranteed valid, and so it can be regenerated
# deterministically if TUTORIAL.md changes. Run once: python build_notebook.py
import nbformat as nbf

nb = nbf.v4.new_notebook()
cells = []


def md(text):
    cells.append(nbf.v4.new_markdown_cell(text))


def code(text):
    cells.append(nbf.v4.new_code_cell(text))


md("""\
# Chronos-2 Tutorial: Scientific Time-Series Forecasting

This notebook is the runnable companion to `TUTORIAL.md` in this folder. It uses a small
**synthetic** dataset (generated below, no private or external data required) shaped like a
seasonal target with a few climate-style covariates, observed on an 8-day step — but the same code
works for hourly, daily, or monthly data by editing the CONFIG block in `chronos2_template.py`.

Run the cells top to bottom. Requires: `chronos-forecasting`, `torch`, `pandas`, `numpy`,
`matplotlib`, `scikit-learn` (see `README.md` for the install command)."""
)

code("""\
import sys
sys.path.insert(0, ".")

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

import chronos2_template as ct
""")

md("## 1. Generate the example dataset\n\nRun once; produces `data/example_timeseries.csv`.")
code("""\
import make_synthetic_data
make_synthetic_data.main()
""")

md("## 2. Load and inspect")
code("""\
df = ct.load_data("data/example_timeseries.csv")
df.head()
""")

code("""\
report = ct.validate_data(df)
""")

md("## 3. Configure (edit these 6 lines for a new dataset)")
code("""\
ct.TARGET = "target"
ct.PAST_COVARIATES = ["temperature", "precipitation", "vpd", "radiation"]
ct.FUTURE_COVARIATES = ["temperature", "precipitation", "vpd", "radiation"]
ct.ID_COLUMN = "series_id"
ct.TIMESTAMP_COLUMN = "date"
ct.FREQ = "8D"
ct.PREDICTION_LENGTH = 46
""")

md("## 4. Chronological train/test split, and Chronos-2 input construction\n\n"
   "We hold out the last `PREDICTION_LENGTH` steps of each series as the test window - see "
   "TUTORIAL.md Part 11 for why this must be a chronological split, not a random one.")
code("""\
one_series = df[df[ct.ID_COLUMN] == df[ct.ID_COLUMN].iloc[0]].sort_values(ct.TIMESTAMP_COLUMN)
split_date = one_series[ct.TIMESTAMP_COLUMN].iloc[-ct.PREDICTION_LENGTH]
print("Split date:", split_date)

inputs, ground_truth, future_dates = ct.prepare_chronos_inputs(df, split_date)
print(f"{len(inputs)} series prepared. Context length: {len(inputs[0]['target'])}, "
      f"forecast horizon: {len(ground_truth[sorted(ground_truth)[0]])}")
""")

md("## 5. Load Chronos-2 and generate a zero-shot forecast\n\n"
   "Always start with zero-shot (no training) - see TUTORIAL.md Part 9.")
code("""\
pipeline = ct.load_pipeline()  # auto-selects GPU if available, else CPU
quantiles, median = ct.run_forecast(pipeline, inputs, prediction_length=ct.PREDICTION_LENGTH)
""")

md("## 6. Evaluate and plot, per series")
code("""\
series_ids = sorted(df[ct.ID_COLUMN].unique())
all_metrics = {}
for i, sid in enumerate(series_ids):
    pred = median[i][0].numpy()
    lower = quantiles[i][0, :, 0].numpy()
    upper = quantiles[i][0, :, -1].numpy()
    metrics = ct.evaluate_forecast(ground_truth[sid], pred)
    all_metrics[sid] = metrics
    print(sid, metrics)

    fig, axes = plt.subplots(1, 3, figsize=(15, 4))
    ct.plot_forecast(future_dates[sid], ground_truth[sid], pred, lower, upper,
                      title=f"{sid}: forecast vs. observed", ax=axes[0])
    ct.plot_scatter(ground_truth[sid], pred, title=f"{sid}: observed vs. predicted", ax=axes[1])
    ct.plot_residuals(future_dates[sid], ground_truth[sid], pred, title=f"{sid}: residuals", ax=axes[2])
    plt.tight_layout()
    plt.show()
""")

md("""\
## 7. Next steps

- **Add or remove covariates** by editing `PAST_COVARIATES`/`FUTURE_COVARIATES` above and re-running
  from cell 4 - always compare against this zero-shot baseline (TUTORIAL.md Part 9, Part 17 step 9).
- **Fine-tune** with `pipeline.fit(...)` - see TUTORIAL.md Part 10, and Part 11 for the validation
  protocol to use before trusting any fine-tuned result.
- **Switch to your own dataset** by pointing `ct.load_data(...)` at a CSV with the same long-format
  shape (`date`, series id, target, covariate columns) - see TUTORIAL.md Part 4 and
  `example_config.py` for a worked second-domain example.
"""
)

nb["cells"] = cells
nb["metadata"] = {
    "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
    "language_info": {"name": "python", "version": "3.11"},
}

with open("chronos2_tutorial.ipynb", "w") as f:
    nbf.write(nb, f)
print("Wrote chronos2_tutorial.ipynb")
