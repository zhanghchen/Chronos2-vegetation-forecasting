# Chronos-2 with PFT conditioning via FiLM, for the multi-pixel experiment.
#
# WHY NOT JUST POOL PIXELS: verified directly from source
# (src/chronos/chronos2/model.py, chronos_bolt.py InstanceNorm) that every
# covariate row is normalized using ITS OWN per-row loc/scale
# (dim=-1 reduction over the time axis only), independent of what else is
# in the batch. A per-pixel-constant PFT covariate therefore has std=0 and
# gets erased to exactly 0 (scale substituted with eps) REGARDLESS of
# pooling - confirmed again here, not assumed. Pooling many pixels into one
# batch does not change this: each row's normalization is still computed
# from only that row's own values. Feeding PFT as just another covariate
# row, even in a pooled multi-pixel setting, would fail identically to the
# single-pixel case (CHRONOS2_PFT_ABLATION_REPORT.md).
#
# Also verified: GroupSelfAttention (layers.py) explicitly has "no natural
# ordering along the batch axis" - no RoPE, no learned per-row type
# embedding. Once a covariate row's *content* is erased by InstanceNorm,
# there is no other channel (position, embedding, or otherwise) through
# which the model could recover which covariate it originally was. PFT
# cannot reach the model through the existing covariate mechanism at all,
# pooled or not.
#
# ARCHITECTURE-LEVEL FIX: a small PFT encoder (frozen base model + a new,
# separately-trained FiLM head) conditions the model's own per-item
# representation directly, bypassing InstanceNorm entirely (PFT is a
# per-item property, not a covariate value that needs a comparable time
# axis to be instance-normalized against). Injection point: the encoder's
# *output* hidden states for the target row's forecast-patch positions
# (`hidden_states[:, -num_output_patches:]`), immediately before
# `output_patch_embedding` - the smallest possible point that still lets
# PFT influence the final LAI read-out. `encode()` itself (all attention,
# instance-norm, patch embedding) is reused from Chronos2Model completely
# unmodified. The FiLM head's final layer is zero-initialized, so at
# initialization gamma=0, beta=0 and this model is BYTE-IDENTICAL to the
# unmodified pretrained model - only training moves it away from that.
import torch
import torch.nn as nn

from chronos.chronos2.model import Chronos2Model


class PFTEncoder(nn.Module):
    """Fractional PFT vector (K dims) -> (gamma, beta), each d_model-wide.
    Zero-initialized output layer => identity FiLM at init."""

    def __init__(self, pft_dim, d_model, hidden_dim=64):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(pft_dim, hidden_dim),
            nn.GELU(),
            nn.Linear(hidden_dim, 2 * d_model),
        )
        nn.init.zeros_(self.net[-1].weight)
        nn.init.zeros_(self.net[-1].bias)

    def forward(self, pft_features):
        out = self.net(pft_features)
        gamma, beta = out.chunk(2, dim=-1)
        return gamma, beta


class Chronos2PFTModel(Chronos2Model):
    """Subclasses Chronos2Model purely to add a FiLM conditioning head.
    No method of the base class is modified - encode() is called exactly
    as the base forward() would call it; only the post-encode, pre-readout
    step is new."""

    def __init__(self, config, pft_dim=10, pft_hidden=64):
        super().__init__(config)
        self.pft_dim = pft_dim
        self.pft_encoder = PFTEncoder(pft_dim, config.d_model, pft_hidden)

    @classmethod
    def from_pretrained_base(cls, base_model, pft_dim=10, pft_hidden=64):
        """Builds a Chronos2PFTModel with the same weights as an already-
        loaded, pretrained Chronos2Model - the new pft_encoder is the only
        thing not present in the source state_dict (loaded with
        strict=False for exactly that reason)."""
        model = cls(base_model.config, pft_dim=pft_dim, pft_hidden=pft_hidden)
        missing, unexpected = model.load_state_dict(base_model.state_dict(), strict=False)
        assert unexpected == [], f"unexpected keys: {unexpected}"
        assert all(k.startswith("pft_encoder.") for k in missing), f"unexpected missing keys: {missing}"
        return model

    def freeze_base(self):
        """Freezes every parameter except pft_encoder - the only thing
        this experiment trains, by design (see module docstring)."""
        for name, p in self.named_parameters():
            p.requires_grad = name.startswith("pft_encoder.")

    def forward(
        self,
        context,
        context_mask=None,
        group_ids=None,
        future_covariates=None,
        future_covariates_mask=None,
        num_output_patches=1,
        future_target=None,
        future_target_mask=None,
        output_attentions=False,
        pft_features=None,
        is_target_row=None,
    ):
        """Identical to Chronos2Model.forward() except for the FiLM
        conditioning block, which is the only new code below `encode()`.
        `pft_features`: (batch_size, pft_dim) - only rows where
        `is_target_row` is True are actually read; other rows may be zeros.
        `is_target_row`: (batch_size,) bool - which rows are the LAI
        target (vs. a climate covariate) row for their item.
        """
        batch_size = context.shape[0]
        encoder_outputs, loc_scale, patched_future_covariates_mask, num_context_patches = self.encode(
            context=context,
            context_mask=context_mask,
            group_ids=group_ids,
            future_covariates=future_covariates,
            future_covariates_mask=future_covariates_mask,
            num_output_patches=num_output_patches,
            future_target=future_target,
            future_target_mask=future_target_mask,
            output_attentions=output_attentions,
        )
        hidden_states = encoder_outputs[0]
        assert hidden_states.shape == (batch_size, num_context_patches + 1 + num_output_patches, self.model_dim)

        if pft_features is not None and is_target_row is not None and is_target_row.any():
            gamma, beta = self.pft_encoder(pft_features[is_target_row])  # (n_target, d_model) each
            gamma = gamma.unsqueeze(1)  # (n_target, 1, d_model) - broadcasts over forecast patches
            beta = beta.unsqueeze(1)
            forecast_slice = hidden_states[is_target_row, -num_output_patches:, :]
            modulated = forecast_slice * (1 + gamma) + beta
            hidden_states = hidden_states.clone()
            hidden_states[is_target_row, -num_output_patches:, :] = modulated

        forecast_embeds = hidden_states[:, -num_output_patches:]
        quantile_preds = self.output_patch_embedding(forecast_embeds)
        from einops import rearrange

        quantile_preds = rearrange(
            quantile_preds, "b n (q p) -> b q (n p)",
            n=num_output_patches, q=self.num_quantiles, p=self.chronos_config.output_patch_size,
        )

        loss = (
            self._compute_loss(
                quantile_preds=quantile_preds, future_target=future_target,
                future_target_mask=future_target_mask,
                patched_future_covariates_mask=patched_future_covariates_mask,
                loc_scale=loc_scale, num_output_patches=num_output_patches,
            )
            if future_target is not None else None
        )

        quantile_preds = rearrange(
            quantile_preds, "b q h -> b (q h)", b=batch_size, q=self.num_quantiles,
            h=num_output_patches * self.chronos_config.output_patch_size,
        )
        quantile_preds = self.instance_norm.inverse(quantile_preds, loc_scale)
        quantile_preds = rearrange(
            quantile_preds, "b (q h) -> b q h", q=self.num_quantiles,
            h=num_output_patches * self.chronos_config.output_patch_size,
        )

        return quantile_preds, loss
