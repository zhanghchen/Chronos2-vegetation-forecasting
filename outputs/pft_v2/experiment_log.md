# PFT-v2 Experiment Log

Train windows: [(2010, 2011), (2011, 2012), (2012, 2013), (2013, 2014), (2014, 2015), (2015, 2016), (2016, 2017), (2017, 2018)]
Val windows: [(2018, 2019), (2019, 2020), (2020, 2021)]
Test window (touched once, at the end): (2021, 2022)

## Stage 1: architecture screening (fractional PFT, pre-2022 validation only)

- **deep_mlp**: n_params=100544, best val_loss=0.34664, val_r2=0.8323, lr=0.001, step=0 (579s)
- **deep_mlp_reg**: n_params=51040, best val_loss=0.34667, val_r2=0.8325, lr=0.003, step=0 (580s)

--- resume/run at 2026-08-27 01:15:00.209889 ---
Train windows: [(2010, 2011), (2011, 2012), (2012, 2013), (2013, 2014), (2014, 2015), (2015, 2016), (2016, 2017), (2017, 2018)]
Val windows: [(2018, 2019), (2019, 2020), (2020, 2021)]
Test window (touched once, at the end): (2021, 2022)

## Stage 1: architecture screening (fractional PFT, pre-2022 validation only)

- **deep_mlp**: n_params=100544, best val_loss=0.34664, val_r2=0.8323, lr=0.001, step=0 (0s)
- **deep_mlp_reg**: n_params=51040, best val_loss=0.34667, val_r2=0.8325, lr=0.003, step=0 (0s)
- **linear_mixture**: n_params=15360, best val_loss=0.34695, val_r2=0.8317, lr=0.001, step=0 (578s)
- **low_rank**: n_params=12600, best val_loss=0.34653, val_r2=0.8321, lr=0.001, step=20 (580s)

**Winning architecture (by pre-2022 validation loss): low_rank** (val_loss=0.34653, val_r2=0.8321)

## Stage 2: winning architecture, dominant PFT (pre-2022 validation only)

- dominant: val_loss=0.34655, val_r2=0.8321, lr=0.001, step=20

## Stage 3: shuffled-PFT control, winning architecture (pre-2022 validation only)

- shuffled: val_loss=0.34647, val_r2=0.8321, lr=0.001, step=20

## Stage 4: final refits on all pre-2022 windows

## Stage 5: final, single 2022 evaluation

- **baseline (zero-shot)**: mean R2=0.7655, mean RMSE=0.2050
- **low_rank + fractional PFT**: mean R2=0.7677, mean RMSE=0.2046
- **low_rank + dominant PFT**: mean R2=0.7678, mean RMSE=0.2045
- **low_rank + SHUFFLED PFT (control)**: mean R2=0.7679, mean RMSE=0.2047

## Final 2022 summary

                   method  mean_R2  mean_RMSE
       baseline_zero_shot 0.765487   0.204997
      low_rank_fractional 0.767712   0.204560
        low_rank_dominant 0.767767   0.204549
low_rank_shuffled_control 0.767877   0.204653

Done.
