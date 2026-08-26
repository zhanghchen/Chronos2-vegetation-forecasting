# Generalizes Chronos-2's public pipeline.fit(finetune_mode="lora") to
# arbitrary parameter-efficient adaptation methods. Chronos-2's public API
# only accepts finetune_mode in {"full","lora"} and hardcodes LoraConfig
# construction (confirmed by reading chronos/chronos2/pipeline.py:96-364
# directly before writing this) - but the underlying mechanism is just
# `peft.get_peft_model(model, <any peft.PeftConfig>)` followed by a
# completely generic `Chronos2Trainer` (a transformers.Trainer subclass
# whose only override is dataloader construction - confirmed by reading
# chronos/chronos2/trainer.py - no LoRA-specific logic anywhere). This
# module replicates fit()'s internals exactly (dataset construction,
# TrainingArguments, validation wiring, the final-step-eval callback, tf32
# save/restore, returning a new Chronos2Pipeline) but substitutes the
# hardcoded LoRA-application step with a pluggable dispatcher, so results
# stay directly comparable to the existing zero-shot/LoRA/improved-LoRA runs
# built on the public API.
#
# Architecture facts used below, confirmed by direct inspection of the
# loaded amazon/chronos-2 model (not assumed):
#   - T5-style encoder: 12 blocks (encoder.block.0..11), each with
#     self_attention.{q,k,v,o} and mlp.{wi,wo}, plus a per-sublayer
#     layer_norm and a final encoder.final_layer_norm. d_model=768.
#   - self_attention and mlp Linear layers have NO bias (bias=False) -
#     confirmed by enumerating named_parameters(): only the
#     input_patch_embedding/output_patch_embedding MLPs have bias terms
#     (6 tensors, 8,352 params total = 0.007% of the model). This is why
#     BitFit (classic "unfreeze all bias terms") only touches the patch
#     embedding, never the transformer body - see BITFIT_UNFREEZE_SUBSTR.
#   - Normalization params total 28,416 = 37 norm modules x 768 (12
#     blocks x 3 sub-layer norms + 1 final norm) - all learnable scale
#     vectors (RMSNorm-style, no bias), confirming LN-Tuning has
#     meaningfully more capacity than BitFit despite still being tiny.
import math
import time
import warnings
from copy import deepcopy
from pathlib import Path

import torch
from transformers.trainer_callback import TrainerCallback
from transformers.training_args import TrainingArguments

from chronos.chronos2 import Chronos2Model, Chronos2Pipeline
from chronos.chronos2.dataset import Chronos2Dataset, DatasetMode
from chronos.chronos2.trainer import Chronos2Trainer, EvaluateAndSaveFinalStepCallback

# Same attention + output-embedding targets already validated for LoRA in
# finetune_lora_improved.py - reused unchanged for DoRA and VeRA, since both
# are low-rank-update methods with the same natural target set.
LOW_RANK_TARGET_MODULES = [
    "self_attention.q", "self_attention.v", "self_attention.k", "self_attention.o",
    "output_patch_embedding.output_layer",
]
# IA3's original design targets K/V projections (attention) and the FFN's
# *down*-projection (T5 naming: mlp.wo is the second/output linear of the
# 2-layer FFN) - feedforward_modules must be a subset of target_modules.
IA3_TARGET_MODULES = ["self_attention.k", "self_attention.v", "mlp.wo"]
IA3_FEEDFORWARD_MODULES = ["mlp.wo"]
# All per-sublayer RMSNorm-style scale vectors, every block + the final norm.
LN_TUNING_TARGET_MODULES = ["layer_norm", "final_layer_norm"]
# Classic BitFit target: every bias term. On this architecture that's only
# the patch-embedding MLPs (see module docstring) - reported honestly as a
# near-zero-capacity control, not hidden.
BITFIT_UNFREEZE_SUBSTR = ".bias"
# Optional 6th (partial/selective layer fine-tuning): full-weight unfreeze of
# only the LAST encoder block + final norm + output embedding, mirroring
# which modules the low-rank methods already target, but with full capacity
# there instead of a low-rank update.
PARTIAL_LAST_BLOCK_PREFIXES = ("encoder.block.11.", "encoder.final_layer_norm", "output_patch_embedding.")

METHODS = ["dora", "vera", "ia3", "ln_tuning", "bitfit", "partial_last_block"]


def build_fresh_model(pipeline):
    """Deep-copies the pretrained model exactly as pipeline.fit() does,
    before any adaptation is applied - every method starts from the exact
    same pretrained weights."""
    config = deepcopy(pipeline.model.config)
    model = Chronos2Model(config).to(pipeline.model.device)
    model.load_state_dict(pipeline.model.state_dict())
    return model


def apply_adaptation(model, method, rank=None, dropout=0.0):
    """Wraps/modifies `model` in place (or returns a peft-wrapped copy) for
    the given method. Returns (model, n_trainable, n_total)."""
    if method == "dora":
        from peft import LoraConfig, get_peft_model
        cfg = LoraConfig(r=rank, lora_alpha=rank * 2, lora_dropout=dropout,
                          target_modules=LOW_RANK_TARGET_MODULES, use_dora=True)
        model = get_peft_model(model, cfg)
    elif method == "vera":
        from peft import VeraConfig, get_peft_model
        cfg = VeraConfig(r=rank, vera_dropout=dropout, target_modules=LOW_RANK_TARGET_MODULES)
        model = get_peft_model(model, cfg)
    elif method == "ia3":
        from peft import IA3Config, get_peft_model
        cfg = IA3Config(target_modules=IA3_TARGET_MODULES, feedforward_modules=IA3_FEEDFORWARD_MODULES)
        model = get_peft_model(model, cfg)
    elif method == "ln_tuning":
        from peft import LNTuningConfig, get_peft_model
        cfg = LNTuningConfig(target_modules=LN_TUNING_TARGET_MODULES)
        model = get_peft_model(model, cfg)
    elif method == "bitfit":
        for n, p in model.named_parameters():
            p.requires_grad_(n.endswith(BITFIT_UNFREEZE_SUBSTR))
    elif method == "partial_last_block":
        for n, p in model.named_parameters():
            p.requires_grad_(any(n.startswith(pre) for pre in PARTIAL_LAST_BLOCK_PREFIXES))
    else:
        raise ValueError(f"Unknown method: {method}")

    if hasattr(model, "get_nb_trainable_parameters"):
        n_trainable, n_total = model.get_nb_trainable_parameters()
    else:
        n_trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
        n_total = sum(p.numel() for p in model.parameters())
    return model, n_trainable, n_total


def fit_with_adaptation(
    pipeline, inputs, prediction_length, method, *,
    rank=None, dropout=0.0, validation_inputs=None, context_length=None,
    learning_rate=1e-4, num_steps=1000, batch_size=32, output_dir=None,
    min_past=None, callbacks=None, logging_steps=100, disable_data_parallel=True,
):
    """Faithful generalization of Chronos2Pipeline.fit() (see module
    docstring) to any method in METHODS. Returns
    (finetuned_pipeline, n_trainable, n_total, elapsed_sec, peak_memory_bytes)."""
    model = build_fresh_model(pipeline)
    model, n_trainable, n_total = apply_adaptation(model, method, rank=rank, dropout=dropout)

    if context_length is None:
        context_length = pipeline.model_context_length
    if min_past is None:
        min_past = prediction_length

    train_dataset = Chronos2Dataset.convert_inputs(
        inputs=inputs, context_length=context_length, prediction_length=prediction_length,
        batch_size=batch_size, output_patch_size=pipeline.model_output_patch_size,
        min_past=min_past, mode=DatasetMode.TRAIN,
    )

    if output_dir is None:
        output_dir = Path("chronos-2-finetuned") / time.strftime("%Y-%m-%d_%H-%M-%S")
    elif isinstance(output_dir, str):
        output_dir = Path(output_dir)

    use_cpu = str(pipeline.model.device) == "cpu"
    has_sm80 = torch.cuda.is_available() and torch.cuda.get_device_capability()[0] >= 8

    training_kwargs = dict(
        output_dir=str(output_dir), per_device_train_batch_size=batch_size,
        per_device_eval_batch_size=batch_size, learning_rate=learning_rate,
        lr_scheduler_type="linear", warmup_ratio=0.0, optim="adamw_torch_fused",
        logging_strategy="steps", logging_steps=logging_steps, disable_tqdm=False,
        report_to="none", max_steps=num_steps, gradient_accumulation_steps=1,
        dataloader_num_workers=0, tf32=has_sm80 and not use_cpu, bf16=has_sm80 and not use_cpu,
        save_only_model=True, prediction_loss_only=True, save_total_limit=1,
        save_strategy="no", save_steps=None, eval_strategy="no", eval_steps=None,
        load_best_model_at_end=False, metric_for_best_model=None, use_cpu=use_cpu,
    )

    eval_dataset = None
    callbacks = list(callbacks) if callbacks else []
    if validation_inputs is not None:
        eval_dataset = Chronos2Dataset.convert_inputs(
            inputs=validation_inputs, context_length=context_length, prediction_length=prediction_length,
            batch_size=batch_size, output_patch_size=pipeline.model_output_patch_size, mode=DatasetMode.VALIDATION,
        )
        training_kwargs.update(
            save_strategy="steps", save_steps=100, eval_strategy="steps", eval_steps=100,
            load_best_model_at_end=True, metric_for_best_model="eval_loss", label_names=["future_target"],
        )
        callbacks.append(EvaluateAndSaveFinalStepCallback())

    if training_kwargs["tf32"]:
        matmul_tf32 = torch.backends.cuda.matmul.allow_tf32
        cudnn_tf32 = torch.backends.cudnn.allow_tf32

    training_args = TrainingArguments(**training_kwargs)
    if disable_data_parallel and not use_cpu:
        training_args._n_gpu = 1
        assert training_args.n_gpu == 1

    trainer = Chronos2Trainer(model=model, args=training_args, train_dataset=train_dataset,
                               eval_dataset=eval_dataset, callbacks=callbacks)

    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()
    t0 = time.time()
    trainer.train()
    elapsed = time.time() - t0
    peak_memory = torch.cuda.max_memory_allocated() if torch.cuda.is_available() else 0

    model.chronos_config.context_length = max(model.chronos_config.context_length, context_length)
    model.chronos_config.max_output_patches = max(
        model.chronos_config.max_output_patches, math.ceil(prediction_length / pipeline.model_output_patch_size)
    )
    model.config.chronos_config = model.chronos_config.__dict__

    finetuned_pipeline = Chronos2Pipeline(model=model)

    if training_kwargs["tf32"]:
        torch.backends.cuda.matmul.allow_tf32 = matmul_tf32
        torch.backends.cudnn.allow_tf32 = cudnn_tf32

    return finetuned_pipeline, n_trainable, n_total, elapsed, peak_memory


class HistoryCallback(TrainerCallback):
    """Captures every logged training-loss/eval-loss point (same convention
    as finetune_lora_improved.py's HistoryCallback)."""

    def __init__(self):
        self.records = []

    def on_log(self, args, state, control, logs=None, **kwargs):
        if logs is None:
            return
        record = dict(logs)
        record["step"] = state.global_step
        self.records.append(record)
