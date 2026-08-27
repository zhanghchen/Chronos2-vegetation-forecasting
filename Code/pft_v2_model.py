# Candidate PFT-conditioning architectures for Chronos-2, screened against
# each other on pre-2022 validation data (see pft_v2_train.py). All share
# the same safe injection point established in pft_multipixel_model.py
# (FiLM on hidden states immediately before output_patch_embedding, base
# model frozen, zero-initialized conditioner => identity at init) - what
# varies is the CONDITIONER module and WHICH rows get conditioned.
import torch
import torch.nn as nn

from chronos.chronos2.model import Chronos2Model


class DeepMLPConditioner(nn.Module):
    """Original design: PFT vector -> MLP -> (gamma, beta). Expressive,
    many parameters relative to the amount of real training signal - the
    leading suspect for the original overfitting."""

    def __init__(self, pft_dim, d_model, hidden_dim=64, dropout=0.0):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(pft_dim, hidden_dim),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, 2 * d_model),
        )
        nn.init.zeros_(self.net[-1].weight)
        nn.init.zeros_(self.net[-1].bias)

    def forward(self, pft_features):
        out = self.net(pft_features)
        gamma, beta = out.chunk(2, dim=-1)
        return gamma, beta

    def n_params(self):
        return sum(p.numel() for p in self.parameters())


class LinearMixtureConditioner(nn.Module):
    """Biologically-structured alternative (section 5 of the redesign
    request): one learned (gamma_c, beta_c) modulation vector PER PFT
    CLASS, linearly combined by the pixel's own fractional weights:
        gamma = sum_c p_c * gamma_c,  beta = sum_c p_c * beta_c
    This is exactly a soft per-class response decomposition
    (Response = sum_c p_c * response_c(...)) implemented as a linear layer
    with no bias and no hidden nonlinearity - trainable parameters =
    2 * d_model * K (e.g. 2*768*10 = 15,360, ~6.5x smaller than the deep
    MLP), and each class's own modulation vector is directly inspectable.
    Zero-initialized => identity at init, same as the MLP conditioner."""

    def __init__(self, pft_dim, d_model):
        super().__init__()
        self.class_film = nn.Linear(pft_dim, 2 * d_model, bias=False)
        nn.init.zeros_(self.class_film.weight)

    def forward(self, pft_features):
        out = self.class_film(pft_features)
        gamma, beta = out.chunk(2, dim=-1)
        return gamma, beta

    def n_params(self):
        return sum(p.numel() for p in self.parameters())


class LowRankMLPConditioner(nn.Module):
    """A middle ground between DeepMLPConditioner and LinearMixtureConditioner:
    a small nonlinear encoder into a LOW-RANK bottleneck (rank << d_model),
    then a fixed linear expansion to (gamma, beta). Regularizes by
    construction (the FiLM vectors are confined to an r-dimensional
    subspace of R^d_model instead of the full space)."""

    def __init__(self, pft_dim, d_model, rank=8, hidden_dim=16, dropout=0.0):
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Linear(pft_dim, hidden_dim), nn.GELU(), nn.Dropout(dropout), nn.Linear(hidden_dim, rank),
        )
        self.expand_gamma = nn.Linear(rank, d_model, bias=False)
        self.expand_beta = nn.Linear(rank, d_model, bias=False)
        nn.init.zeros_(self.expand_gamma.weight)
        nn.init.zeros_(self.expand_beta.weight)

    def forward(self, pft_features):
        z = self.encoder(pft_features)
        return self.expand_gamma(z), self.expand_beta(z)

    def n_params(self):
        return sum(p.numel() for p in self.parameters())


class Chronos2PFTModelV2(Chronos2Model):
    """Generalized version of pft_multipixel_model.Chronos2PFTModel:
    accepts any conditioner module and a `condition_rows` mask decoupled
    from `is_target_row` (so a future variant could condition covariate
    rows too - "PFT-conditioned climate representation" - without any
    other code change)."""

    def __init__(self, config, conditioner):
        super().__init__(config)
        self.pft_conditioner = conditioner

    @classmethod
    def from_pretrained_base(cls, base_model, conditioner):
        model = cls(base_model.config, conditioner)
        missing, unexpected = model.load_state_dict(base_model.state_dict(), strict=False)
        assert unexpected == [], f"unexpected keys: {unexpected}"
        assert all(k.startswith("pft_conditioner.") for k in missing), f"unexpected missing keys: {missing}"
        return model

    def freeze_base(self):
        for name, p in self.named_parameters():
            p.requires_grad = name.startswith("pft_conditioner.")

    def forward(
        self, context, context_mask=None, group_ids=None, future_covariates=None,
        future_covariates_mask=None, num_output_patches=1, future_target=None,
        future_target_mask=None, output_attentions=False, pft_features=None, condition_rows=None,
    ):
        batch_size = context.shape[0]
        encoder_outputs, loc_scale, patched_future_covariates_mask, num_context_patches = self.encode(
            context=context, context_mask=context_mask, group_ids=group_ids,
            future_covariates=future_covariates, future_covariates_mask=future_covariates_mask,
            num_output_patches=num_output_patches, future_target=future_target,
            future_target_mask=future_target_mask, output_attentions=output_attentions,
        )
        hidden_states = encoder_outputs[0]
        assert hidden_states.shape == (batch_size, num_context_patches + 1 + num_output_patches, self.model_dim)

        if pft_features is not None and condition_rows is not None and condition_rows.any():
            gamma, beta = self.pft_conditioner(pft_features[condition_rows])
            gamma = gamma.unsqueeze(1)
            beta = beta.unsqueeze(1)
            forecast_slice = hidden_states[condition_rows, -num_output_patches:, :]
            modulated = forecast_slice * (1 + gamma) + beta
            hidden_states = hidden_states.clone()
            hidden_states[condition_rows, -num_output_patches:, :] = modulated

        forecast_embeds = hidden_states[:, -num_output_patches:]
        quantile_preds = self.output_patch_embedding(forecast_embeds)
        from einops import rearrange
        quantile_preds = rearrange(
            quantile_preds, "b n (q p) -> b q (n p)", n=num_output_patches,
            q=self.num_quantiles, p=self.chronos_config.output_patch_size,
        )
        loss = (
            self._compute_loss(
                quantile_preds=quantile_preds, future_target=future_target,
                future_target_mask=future_target_mask,
                patched_future_covariates_mask=patched_future_covariates_mask,
                loc_scale=loc_scale, num_output_patches=num_output_patches,
            ) if future_target is not None else None
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
