# Runs Chronos-2 (zero-shot and LoRA fine-tuned) on the 3 pixels reused from
# the AELSTM project, forecasting the full 2022 test year in a single direct
# multi-step call, using historical climate as past_covariates and the
# actual observed 2022 climate as future_covariates. Saves predictions.csv,
# metrics.txt, and a predicted-vs-observed plot per (site, mode).
import argparse
import time

import numpy as np
import pandas as pd
import torch
from chronos import BaseChronosPipeline

import common_pipeline as cp
import plotting_utils as pu


def get_pipeline(device):
    print(f"Loading {cp.MODEL_ID} on device={device} ...")
    t0 = time.time()
    pipeline = BaseChronosPipeline.from_pretrained(cp.MODEL_ID, device_map=device)
    print(f"Loaded in {time.time() - t0:.1f}s")
    return pipeline


def predict_with_pipeline(pipeline, input_dict, prediction_length):
    _, mean = pipeline.predict_quantiles(
        [input_dict], prediction_length=prediction_length, quantile_levels=[0.1, 0.5, 0.9]
    )
    # mean[0] has shape (n_variates=1, prediction_length) for a univariate target
    return mean[0][0].float().cpu().numpy()


def finetune_pipeline(pipeline, input_dict, prediction_length, site):
    train_input = {
        "target": input_dict["target"],
        "past_covariates": input_dict["past_covariates"],
        # Values are unused during training; only the keys (which covariates
        # will be known in the future) matter.
        "future_covariates": {c: None for c in cp.FEATURE_COLS},
    }
    return pipeline.fit(
        inputs=[train_input],
        prediction_length=prediction_length,
        finetune_mode="lora",
        output_dir=cp.OUTPUTS_ROOT / "finetune_checkpoints" / site,
        learning_rate=cp.FINETUNE_LEARNING_RATE,
        num_steps=cp.FINETUNE_NUM_STEPS,
        batch_size=cp.FINETUNE_BATCH_SIZE,
        logging_steps=100,
    )


def save_run(mode, site, dates, true, pred, pred_color, pred_label):
    metrics = cp.compute_metrics(true, pred)
    output_dir = cp.OUTPUTS_ROOT / mode / site
    output_dir.mkdir(parents=True, exist_ok=True)

    pd.DataFrame({"date": dates, "ground_truth": true, "prediction": pred}).to_csv(
        output_dir / "predictions.csv", index=False
    )
    with open(output_dir / "metrics.txt", "w") as f:
        for name, value in metrics.items():
            f.write(f"{name}: {value:.6f}\n")

    title = f"{site} — Chronos-2 ({pred_label}) predicted vs. observed LAI, {cp.TEST_YEAR}"
    pu.plot_prediction(dates, true, pred, title, output_dir, "prediction_plot",
                        pred_color=pred_color, pred_label=pred_label)

    print(f"[{mode}/{site}] " + " ".join(f"{k}={v:.4f}" for k, v in metrics.items()))
    return metrics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sites", nargs="+", default=cp.SITES)
    parser.add_argument("--modes", nargs="+", default=["zero_shot", "finetuned_lora"],
                         choices=["zero_shot", "finetuned_lora"])
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    args = parser.parse_args()

    pipeline = get_pipeline(args.device)

    all_metrics = []
    for site in args.sites:
        df = cp.load_site_df(site)
        input_dict, prediction_length, future_dates, ground_truth = cp.build_chronos_inputs(df)
        print(f"\n=== {site}: context={len(input_dict['target'])} steps, "
              f"prediction_length={prediction_length} ===")

        if "zero_shot" in args.modes:
            pred = predict_with_pipeline(pipeline, input_dict, prediction_length)
            m = save_run("zero_shot", site, future_dates, ground_truth, pred,
                         pu.ZERO_SHOT_COLOR, "zero-shot")
            m.update(site=site, mode="zero_shot")
            all_metrics.append(m)

        if "finetuned_lora" in args.modes:
            t0 = time.time()
            finetuned = finetune_pipeline(pipeline, input_dict, prediction_length, site)
            print(f"LoRA fine-tuning took {time.time() - t0:.1f}s")
            pred = predict_with_pipeline(finetuned, input_dict, prediction_length)
            m = save_run("finetuned_lora", site, future_dates, ground_truth, pred,
                         pu.FINETUNED_COLOR, "LoRA fine-tuned")
            m.update(site=site, mode="finetuned_lora")
            all_metrics.append(m)

    summary = pd.DataFrame(all_metrics)
    summary_path = cp.OUTPUTS_ROOT / "chronos2_all_results.csv"
    summary.to_csv(summary_path, index=False)
    print(f"\nSaved summary to {summary_path}")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
