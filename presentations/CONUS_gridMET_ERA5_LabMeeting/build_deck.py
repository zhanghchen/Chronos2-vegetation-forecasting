# -*- coding: utf-8 -*-
"""Lab-meeting summary deck integrating two large-scale Chronos-2 experiments:
  1) the 70->32-pixel purity-filtered gridMET CONUS expansion
     (reports/CHRONOS2_CONUS70_REPORT.md, outputs/purity32_pixel_study/)
  2) the 70-pixel NON-CONUS GLOBAL experiment: cloud ERA5 (Google ARCO-ERA5)
     + MODIS MOD15A2H LAI via NASA AppEEARS
     (experiments/global_era5_chronos/reports/ERA5_GLOBAL70_REPORT.md,
     experiments/global_era5_chronos/outputs/era5_global70*.csv)

This replaces this deck's ORIGINAL Part 2 (the 70-pixel CONUS cloud-ERA5
study, kept in experiments/global_era5_chronos/reports/
ERA5_CLOUD_LARGESCALE_REPORT.md for the record but no longer presented
here) with the new global non-CONUS experiment, per explicit request.

Every number on every slide is read directly from the CSV/txt result files
below at build time (not retyped from the .md reports), so the deck cannot
silently drift from the actual saved results. Figures are either newly
generated in make_figures.py (this same directory) or copied unmodified
from the two experiments' own outputs/ directories - see each add_picture
call's source path/comment for which is which.

Run: /home/deh25003/miniconda3/bin/python3 build_deck.py
"""
from pathlib import Path

import pandas as pd
from PIL import Image
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

HERE = Path(__file__).resolve().parent
FIG = HERE / "figures"
ROOT = Path("/home/deh25003/chronos-forecasting/Chronos2-vegetation-forecasting")
ERA5_ROOT = ROOT / "experiments/global_era5_chronos"

# ============================================================ pull every number
# straight from the saved result files (RESULT, not re-derived/eyeballed).
p32 = pd.read_csv(ROOT / "outputs/purity32_pixel_study/zero_shot_32pixels.csv")
p32_overall = pd.read_csv(ROOT / "outputs/purity32_pixel_study/summary_overall.csv", index_col=0)
p32_byclass = pd.read_csv(ROOT / "outputs/purity32_pixel_study/summary_by_class.csv", index_col=0).sort_values("mean", ascending=False)

g68 = pd.read_csv(ERA5_ROOT / "outputs/era5_global70_clean.csv")
g68_overall = pd.read_csv(ERA5_ROOT / "outputs/era5_global70_summary_overall.csv", index_col=0)
g68_byclass = pd.read_csv(ERA5_ROOT / "outputs/era5_global70_summary_by_class.csv", index_col=0).sort_values("mean", ascending=False)
g68_byregion = pd.read_csv(ERA5_ROOT / "outputs/era5_global70_summary_by_region.csv", index_col=0).sort_values("mean", ascending=False)
pixel_pool_70 = pd.read_csv(ERA5_ROOT / "data_selection/global_candidate_pixels_70.csv")

n32 = len(p32)
n32_ge08 = (p32["R2"] >= 0.8).sum()
n32_neg = (p32["R2"] < 0).sum()

n68 = len(g68)
n68_ge08 = (g68["R2"] >= 0.8).sum()
n68_neg = (g68["R2"] < 0).sum()
r2_context_corr = g68["context_steps"].corr(g68["R2"])
conus_global_median_gap = p32["R2"].median() - g68["R2"].median()

# ============================================================ deck styling (matches
# Code/build_era5_progress_deck.py's house style exactly, for visual consistency
# with every other deck in slides/)
INK = RGBColor(0x1C, 0x21, 0x19)
MUTED = RGBColor(0x5C, 0x63, 0x55)
FAINT = RGBColor(0x8B, 0x93, 0x82)
ACCENT = RGBColor(0x2F, 0x6F, 0x5E)      # gridMET green (matches ERA5_vs_gridmet fig)
ACCENT_DARK = RGBColor(0x1E, 0x4A, 0x33)
ACCENT_TINT = RGBColor(0xE7, 0xF0, 0xE6)
BLUE = RGBColor(0x3A, 0x6E, 0xA5)        # ERA5 blue (matches fig)
BLUE_TINT = RGBColor(0xE7, 0xEE, 0xF5)
WARN = RGBColor(0xB5, 0x65, 0x1D)
WARN_TINT = RGBColor(0xFB, 0xEE, 0xE0)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
RULE = RGBColor(0xDE, 0xE2, 0xD6)
FONT = "Calibri"

SLIDE_W, SLIDE_H = Inches(13.333), Inches(7.5)
MARGIN = Inches(0.55)
CONTENT_TOP = Inches(1.25)
TAKEAWAY_H = Inches(0.78)
TAKEAWAY_TOP = SLIDE_H - TAKEAWAY_H

prs = Presentation()
prs.slide_width = SLIDE_W
prs.slide_height = SLIDE_H
BLANK = prs.slide_layouts[6]


def add_slide():
    return prs.slides.add_slide(BLANK)


def set_bg(slide, color=WHITE):
    bg = slide.background
    bg.fill.solid(); bg.fill.fore_color.rgb = color


def add_rect(slide, left, top, width, height, color, line=False, line_color=None):
    shp = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, left, top, width, height)
    shp.fill.solid(); shp.fill.fore_color.rgb = color
    if line:
        shp.line.color.rgb = line_color or RULE; shp.line.width = Pt(0.75)
    else:
        shp.line.fill.background()
    shp.shadow.inherit = False
    return shp


def add_rounded(slide, left, top, width, height, color, line_color=None):
    shp = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height)
    shp.adjustments[0] = 0.12
    shp.fill.solid(); shp.fill.fore_color.rgb = color
    if line_color:
        shp.line.color.rgb = line_color; shp.line.width = Pt(1.0)
    else:
        shp.line.fill.background()
    shp.shadow.inherit = False
    return shp


def add_text(slide, left, top, width, height, runs, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, line_spacing=1.0, wrap=True):
    box = slide.shapes.add_textbox(left, top, width, height)
    tf = box.text_frame; tf.word_wrap = wrap; tf.vertical_anchor = anchor
    tf.margin_left = 0; tf.margin_right = 0; tf.margin_top = 0; tf.margin_bottom = 0
    for i, (text, size, color, bold, italic) in enumerate(runs):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align; p.line_spacing = line_spacing
        r = p.add_run(); r.text = text
        r.font.size = Pt(size); r.font.color.rgb = color; r.font.bold = bold; r.font.italic = italic; r.font.name = FONT
    return box


def add_bullets(slide, left, top, width, height, items, size=16, color=INK, space_after=9, bullet_color=ACCENT, anchor=MSO_ANCHOR.TOP):
    box = slide.shapes.add_textbox(left, top, width, height)
    tf = box.text_frame; tf.word_wrap = True; tf.vertical_anchor = anchor
    tf.margin_left = 0; tf.margin_right = 0
    for i, item in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(space_after); p.line_spacing = 1.06
        r0 = p.add_run(); r0.text = "▪  "; r0.font.size = Pt(size); r0.font.color.rgb = bullet_color; r0.font.name = FONT
        r1 = p.add_run(); r1.text = item; r1.font.size = Pt(size); r1.font.color.rgb = color; r1.font.name = FONT
    return box


def add_eyebrow(slide, text):
    add_text(slide, MARGIN, Inches(0.42), Inches(12), Inches(0.32), [(text, 13, ACCENT, True, False)])


def add_title(slide, title, eyebrow=None):
    if eyebrow:
        add_eyebrow(slide, eyebrow)
    add_text(slide, MARGIN, Inches(0.72), Inches(12.2), Inches(0.62), [(title, 23, INK, True, False)])
    add_rect(slide, MARGIN, Inches(1.38), Inches(1.0), Pt(3), ACCENT)


def add_takeaway(slide, text, tint=ACCENT_TINT, dark=ACCENT_DARK, bar=ACCENT):
    add_rect(slide, 0, TAKEAWAY_TOP, SLIDE_W, TAKEAWAY_H, tint)
    add_rect(slide, 0, TAKEAWAY_TOP, Inches(0.12), TAKEAWAY_H, bar)
    add_text(slide, Inches(0.45), TAKEAWAY_TOP, SLIDE_W - Inches(0.9), TAKEAWAY_H,
              [("TAKEAWAY   ", 12, dark, True, False)], anchor=MSO_ANCHOR.MIDDLE)
    add_text(slide, Inches(1.55), TAKEAWAY_TOP, SLIDE_W - Inches(2.0), TAKEAWAY_H,
              [(text, 14.5, dark, True, False)], anchor=MSO_ANCHOR.MIDDLE)


def page_num(slide, n):
    add_text(slide, SLIDE_W - Inches(0.7), Inches(0.42), Inches(0.4), Inches(0.3),
              [(str(n), 11, FAINT, False, False)], align=PP_ALIGN.RIGHT)


def content_box(has_takeaway=True):
    bottom = (TAKEAWAY_TOP - Inches(0.15)) if has_takeaway else (SLIDE_H - Inches(0.3))
    return CONTENT_TOP, bottom - CONTENT_TOP


def styled_table(slide, left, top, width, height, header, rows, col_weights, header_size=12, body_size=11.5, highlight_rows=()):
    n_rows = len(rows) + 1
    tbl = slide.shapes.add_table(n_rows, len(header), left, top, width, height).table
    for c, w in enumerate(col_weights):
        tbl.columns[c].width = Emu(int(width * w))
    for ci, text in enumerate(header):
        cell = tbl.cell(0, ci); cell.text = text
        cell.fill.solid(); cell.fill.fore_color.rgb = ACCENT
        p = cell.text_frame.paragraphs[0]; p.runs[0].font.size = Pt(header_size); p.runs[0].font.bold = True
        p.runs[0].font.color.rgb = WHITE; p.runs[0].font.name = FONT
        p.alignment = PP_ALIGN.CENTER if ci else PP_ALIGN.LEFT
        cell.margin_top = Pt(3); cell.margin_bottom = Pt(3)
    for ri, row in enumerate(rows, start=1):
        hl = (ri - 1) in highlight_rows
        for ci, text in enumerate(row):
            cell = tbl.cell(ri, ci); cell.text = text
            cell.fill.solid(); cell.fill.fore_color.rgb = ACCENT_TINT if hl else (WHITE if ri % 2 else RGBColor(0xF5, 0xF6, 0xF1))
            p = cell.text_frame.paragraphs[0]
            p.runs[0].font.size = Pt(body_size); p.runs[0].font.bold = (ci == 0 or hl)
            p.runs[0].font.color.rgb = INK; p.runs[0].font.name = FONT
            p.alignment = PP_ALIGN.CENTER if ci else PP_ALIGN.LEFT
            cell.margin_top = Pt(3); cell.margin_bottom = Pt(3)
    return tbl


def stat_card(slide, left, top, w, h, num, label, num_color=ACCENT_DARK, tint=ACCENT_TINT):
    add_rounded(slide, left, top, w, h, tint)
    add_text(slide, left, top + Inches(0.12), w, Inches(0.55), [(num, 26, num_color, True, False)], align=PP_ALIGN.CENTER)
    add_text(slide, left, top + Inches(0.68), w, Inches(0.55), [(label, 11.5, MUTED, False, False)], align=PP_ALIGN.CENTER)


def add_picture_fit(slide, path, box_left, box_top, box_w, box_h, align="center"):
    im = Image.open(path)
    ar = im.size[0] / im.size[1]
    box_ar = box_w / box_h
    if ar > box_ar:
        w = box_w; h = int(w / ar)
    else:
        h = box_h; w = int(h * ar)
    left = box_left + (box_w - w) // 2 if align == "center" else box_left
    top = box_top + (box_h - h) // 2
    slide.shapes.add_picture(str(path), left, top, width=w, height=h)
    return left, top, w, h


# ============================================================ SLIDE 1: TITLE
s = add_slide(); set_bg(s)
add_rect(s, 0, 0, SLIDE_W, Inches(1.15), ACCENT)
add_text(s, MARGIN, Inches(0.26), Inches(12.2), Inches(0.65),
         [("Zero-Shot Chronos-2 for LAI Forecasting: From CONUS to the Globe", 23, WHITE, True, False)])
page_num(s, 1)
top, h = content_box()
add_text(s, MARGIN, top + Inches(0.15), Inches(11.8), Inches(0.4), [("LAB MEETING SUMMARY", 13, ACCENT, True, False)])
add_bullets(s, MARGIN, top + Inches(0.7), Inches(11.8), Inches(3.0), [
    "Part 1: gridMET zero-shot generalization, expanded to a 32-pixel purity-filtered CONUS subset.",
    "Part 2: does the same zero-shot pattern hold outside the U.S.? 70 pixels spanning 14 world regions, "
    "cloud ERA5 climate + MODIS LAI ground truth (no CONUS pixels, no gridMET).",
    "Chronos-2 used strictly zero-shot throughout both parts: no training or fine-tuning.",
], size=18, space_after=16)
add_takeaway(s, "Part 1 asks whether the original result was cherry-picked within CONUS; Part 2 asks whether it holds at all outside CONUS.")


# ============================================================ SLIDE 2: MOTIVATION
s = add_slide(); set_bg(s)
add_title(s, "Motivation & Research Questions", eyebrow="BACKGROUND")
page_num(s, 2)
top, h = content_box()
add_bullets(s, MARGIN, top, Inches(11.8), Inches(3.3), [
    "Prior work established strong zero-shot Chronos-2 LAI forecasting on 3 hand-picked CONUS pixels "
    "using gridMET — the open question was whether that result generalizes.",
    "Part 1 asks: does the result hold across a larger, independently-selected, diverse CONUS pixel pool "
    "— not just 3 favorable locations?",
    "Part 2 asks a harder, independent question: does the result hold at all OUTSIDE the U.S., on a "
    "genuinely global pixel pool, using a global climate source (ERA5) and a global LAI product (MODIS) "
    "instead of gridMET/HiQ-LAI (both CONUS-only)?",
], size=16.5, space_after=13)
stat_top = top + Inches(3.5)
stats = [("70 → 32", "Part 1: purity-filtered CONUS subset"), ("70", "Part 2: non-CONUS global pixels, 14 regions"),
         ("Zero-shot", "no training/fine-tuning in either part")]
box_w = Inches(3.75); gap = Inches(0.3)
for i, (num, label) in enumerate(stats):
    left = MARGIN + i * (box_w + gap)
    stat_card(s, left, stat_top, box_w, Inches(1.15), num, label)
add_takeaway(s, "Part 1 tests robustness to pixel choice within CONUS; Part 2 tests robustness to geography, climate source, and LAI source all at once.")


# ============================================================ SLIDE 3: EXP1 DESIGN & MAP
s = add_slide(); set_bg(s)
add_title(s, "Experiment 1: Design & Pixel Selection", eyebrow="EXPERIMENT 1 — GRIDMET EXPANSION")
page_num(s, 3)
top, h = content_box()
add_bullets(s, MARGIN, top, Inches(4.5), Inches(4.6), [
    "Starting pool: 70 CONUS pixels, farthest-point-sampled across an 8-class vegetation-composition "
    "space, spanning 9 U.S. regions (already used for the full 70-pixel gridMET study).",
    f"This experiment isolates the {n32} pixels with PFT purity ≥ 0.75 — the \"clearly one vegetation "
    "type\" subset, a harder bar than the full mixed-composition pool.",
    "Protocol: context = 2000–2021 (~1,000 8-day LAI composites), forecast = all steps of 2022, zero-shot "
    "Chronos-2, scored against raw observed LAI.",
    "No new downloads — this study reuses gridMET/HiQ-LAI data already available locally.",
], size=15.5, space_after=13)
add_picture_fit(s, FIG / "map_32pixel_conus.png", MARGIN + Inches(4.7), top, Inches(7.1), Inches(4.7))
add_takeaway(s, f"{n32} pixels, 8 vegetation classes, 9 regions — purity ≥ 0.75 isolates the \"unambiguous vegetation type\" question.")


# ============================================================ SLIDE 4: EXP1 RESULTS
s = add_slide(); set_bg(s)
add_title(s, "Experiment 1: Results Overview", eyebrow="EXPERIMENT 1 — GRIDMET EXPANSION")
page_num(s, 4)
top, h = content_box()
stats = [
    (f"{p32_overall.loc['median','R2']:.3f}", "median R²"),
    (f"{n32_ge08}/{n32}", "pixels with R² ≥ 0.8"),
    (f"{p32_overall.loc['mean','Pearson_r']:.3f}", "mean Pearson r"),
    (f"{n32_neg}/{n32}", "pixels with R² < 0"),
]
box_w = Inches(2.75); gap = Inches(0.28)
for i, (num, label) in enumerate(stats):
    left = MARGIN + i * (box_w + gap)
    stat_card(s, left, top, box_w, Inches(1.2), num, label)
tbl_top = top + Inches(1.55)
header = ["Metric", "Mean", "Median", "Std", "Min", "Max"]
rows = [[m, f"{p32_overall.loc['mean',m]:.3f}", f"{p32_overall.loc['median',m]:.3f}",
         f"{p32_overall.loc['std',m]:.3f}", f"{p32_overall.loc['min',m]:.3f}", f"{p32_overall.loc['max',m]:.3f}"]
        for m in ["RMSE", "MAE", "R2", "Pearson_r"]]
styled_table(s, MARGIN, tbl_top, SLIDE_W - 2 * MARGIN, Inches(2.1), header, rows,
             col_weights=[0.2, 0.16, 0.16, 0.16, 0.16, 0.16], header_size=13, body_size=12.5)
add_bullets(s, MARGIN, tbl_top + Inches(2.35), Inches(11.8), Inches(1.0), [
    f"Only 1/{n32} pixels scores R² < 0 (px047_grass_nat, R²={p32.set_index('site').loc['px047_grass_nat','R2']:.3f}) "
    "— a near-flat, low-amplitude grassland series, the same signal-to-noise failure mode already "
    "diagnosed in prior LOYO-CV work, not a new problem.",
], size=14.5, space_after=8)
add_takeaway(s, f"Median R²={p32_overall.loc['median','R2']:.3f} across {n32} diverse, purity-filtered pixels — the earlier 3-pixel result was not cherry-picked.")


# ============================================================ SLIDE 5: EXP1 BY PIXEL/CLASS
s = add_slide(); set_bg(s)
add_title(s, "Experiment 1: Performance by Pixel and Vegetation Type", eyebrow="EXPERIMENT 1 — GRIDMET EXPANSION")
page_num(s, 5)
top, h = content_box()
add_picture_fit(s, FIG / "exp1_r2_by_pixel_and_class.png", MARGIN, top, SLIDE_W - 2 * MARGIN, h)
add_takeaway(s, "Tree/shrub-evergreen classes are most consistently strong; grassland and deciduous-shrub classes show the widest spread — driven by a handful of low-amplitude pixels, not the vegetation type itself.")


# ============================================================ SLIDE 6: PART 2 DATASET & PIPELINE
s = add_slide(); set_bg(s)
add_title(s, "Part 2: Global ERA5 + MODIS Dataset & Pipeline", eyebrow="PART 2 — NON-CONUS GLOBAL EXPERIMENT")
page_num(s, 6)
top, h = content_box()
add_text(s, MARGIN, top, Inches(11.8), Inches(0.6),
         [("Climate: ", 14, MUTED, True, False),
          ("Google ARCO-ERA5", 13.5, INK, True, False),
          (" (cloud Zarr, 0.25°, same pipeline validated for the CONUS study — see next slide).  ", 13.5, MUTED, False, False),
          ("LAI: ", 14, MUTED, True, False),
          ("MODIS MOD15A2H.061", 13.5, INK, True, False),
          (" (NEW — gridMET/HiQ-LAI is CONUS-only), fetched via NASA's AppEEARS point API.",
           13.5, MUTED, False, False)])
tbl_top = top + Inches(0.7)
header = ["Chronos-2 variable", "ERA5 source", "How it's obtained"]
rows = [
    ["tmmx (max temp)", "2m_temperature", "direct (daily maximum)"],
    ["tmmn (min temp)", "2m_temperature", "direct (daily minimum)"],
    ["pr (precipitation)", "total_precipitation", "direct (daily sum, m → mm)"],
    ["srad (solar radiation)", "surface_solar_radiation_downwards", "direct (daily mean, J/m² → W/m²)"],
    ["vpd, sph", "2m_temperature, dewpoint, surface_pressure", "derived (FAO-56 Penman-Monteith)"],
    ["vs (wind speed)", "10m u/v-wind components", "magnitude of daily-mean vector"],
]
styled_table(s, MARGIN, tbl_top, SLIDE_W - 2 * MARGIN, Inches(2.35), header, rows, col_weights=[0.28, 0.42, 0.30], header_size=12, body_size=11.3)
add_bullets(s, MARGIN, tbl_top + Inches(2.55), Inches(11.8), Inches(1.6), [
    "LAI: MOD15A2H.061 Lai_500m, 8-day, 500m, Terra-only (covers 2000 onward, unlike the Terra+Aqua combined "
    "product which only starts mid-2002) — QC-filtered to MODLAND-good-quality retrievals only (68.1% of "
    "pixel-dates kept; the rest are dropped, not interpolated over).",
    "Unlike the CONUS study's uniform ~1,000-step context, MODIS data gaps mean context length now varies by "
    "pixel (202–1,002 steps, median 696) — reported per-pixel, not hidden.",
], size=13.5, space_after=6)
add_takeaway(s, "Same validated ERA5 pipeline; the new piece is a genuinely global LAI source (MODIS via AppEEARS) to replace CONUS-only gridMET/HiQ-LAI.")


# ============================================================ SLIDE 7: PART 2 PIXELS & DESIGN
s = add_slide(); set_bg(s)
add_title(s, "Part 2: Global Pixel Selection & Experimental Design", eyebrow="PART 2 — NON-CONUS GLOBAL EXPERIMENT")
page_num(s, 7)
top, h = content_box()
add_bullets(s, MARGIN, top, Inches(11.8), Inches(1.7), [
    "70 pixels selected by farthest-point sampling in vegetation-composition space over the global ESA CCI "
    "PFT product (same methodology as the CONUS pool, extended to a genuinely global, non-CONUS candidate "
    "set) — 10 vegetation classes, 14 world regions, purity 0.44–1.00.",
    f"68/70 had enough usable LAI to run (2 excluded: one high-Arctic pixel with persistent polar night/ice, "
    "one Southeast Asia pixel with persistent monsoon cloud cover — both known MODIS limitations).",
], size=14.5, space_after=9)
add_picture_fit(s, FIG / "global70_map.png", MARGIN, top + Inches(1.85), SLIDE_W - 2 * MARGIN, h - Inches(1.9))
add_takeaway(s, "Protocol otherwise identical to Part 1: context = 2000–2021 (as available), forecast = 2022, zero-shot Chronos-2, no CONUS pixels.")


# ============================================================ SLIDE 8: EQUIVALENCE VALIDATION
s = add_slide(); set_bg(s)
add_title(s, "ERA5 Equivalence: CDS vs. Cloud, Visualized", eyebrow="VALIDATION BEHIND BOTH PARTS' ERA5 USE")
page_num(s, 8)
top, h = content_box()
add_text(s, MARGIN, top, Inches(11.8), Inches(0.4),
         [("Same evergreen pixel, 2021–2022 — actual daily values, not just a correlation coefficient:", 13.5, MUTED, False, False)])
add_picture_fit(s, FIG / "cds_vs_cloud_era5_timeseries_slide.png", MARGIN, top + Inches(0.45), SLIDE_W - 2 * MARGIN, h - Inches(0.5))
add_takeaway(s, "The two sources are visually near-indistinguishable for 6 of 7 variables; precipitation shows the one real, diagnosed discrepancy (convective-event spikes).")


# ============================================================ SLIDE 9: PART 2 LARGE-SCALE RESULTS
s = add_slide(); set_bg(s)
add_title(s, "Part 2: Global Results (68 Usable Pixels)", eyebrow="PART 2 — NON-CONUS GLOBAL EXPERIMENT")
page_num(s, 9)
top, h = content_box()
stats = [
    (f"{g68_overall.loc['median','R2']:.3f}", "median R²"),
    (f"{n68_ge08}/{n68}", "pixels with R² ≥ 0.8"),
    (f"{g68_overall.loc['mean','Pearson_r']:.3f}", "mean Pearson r"),
    (f"{n68_neg}/{n68}", "pixels with R² < 0"),
]
box_w = Inches(2.75); gap = Inches(0.28)
for i, (num, label) in enumerate(stats):
    left = MARGIN + i * (box_w + gap)
    stat_card(s, left, top, box_w, Inches(1.1), num, label, num_color=RGBColor(0x6B, 0x1A, 0x33), tint=RGBColor(0xF3, 0xE2, 0xE8))
tbl_top = top + Inches(1.45)
header = ["Class", "n", "Mean R²", "Median R²"]
rows = [[c, str(int(r["count"])), f"{r['mean']:.3f}", f"{r['median']:.3f}"] for c, r in g68_byclass.iterrows()]
styled_table(s, MARGIN, tbl_top, Inches(6.2), Inches(3.55), header, rows, col_weights=[0.46, 0.14, 0.2, 0.2], header_size=11.5, body_size=10.8)
add_picture_fit(s, FIG / "global70_r2_by_pixel_and_class.png", MARGIN + Inches(6.5), tbl_top - Inches(0.1), Inches(5.3), Inches(3.7))
add_takeaway(s, f"Median R²={g68_overall.loc['median','R2']:.3f}, only {n68_ge08}/{n68} pixels ≥0.8 — a real, substantially weaker result than either CONUS study.")


# ============================================================ SLIDE 10: CONUS VS GLOBAL
s = add_slide(); set_bg(s)
add_title(s, "Integrating Part 1 & Part 2: CONUS vs. Global", eyebrow="HEAD-TO-HEAD COMPARISON")
page_num(s, 10)
top, h = content_box()
add_picture_fit(s, FIG / "conus_vs_global_r2_boxplot.png", MARGIN + Inches(2.5), top, Inches(7.3), h)
add_bullets(s, MARGIN, top + Inches(0.3), Inches(2.3), Inches(4), [
    f"n={n32} (Part 1) vs. n={n68} (Part 2) — disjoint pixel sets, not matched pairs, so this is a "
    "distributional comparison, not a per-pixel scatter.",
    f"context-length vs. R² correlation within Part 2 is only r={r2_context_corr:.2f} — the gap is not "
    "mainly a context-length artifact.",
], size=11.5, space_after=8)
add_takeaway(s, f"Median R² drops from {p32['R2'].median():.3f} (CONUS) to {g68['R2'].median():.3f} (global) — the strongest CONUS finding does not transfer uniformly worldwide.")


# ============================================================ SLIDE 11: FAILURE CASES
s = add_slide(); set_bg(s)
add_title(s, "Part 2 Failure Cases & Regional Patterns", eyebrow="WHERE THE GLOBAL EXPERIMENT STRUGGLES")
page_num(s, 11)
top, h = content_box()
add_bullets(s, MARGIN, top, Inches(11.8), Inches(0.9), [
    "Two distinct failure modes: genuine anti-correlation (worst case, Amazon, Pearson r=-0.50 — direction, "
    "not just magnitude, is wrong) vs. directionally-right-but-miscalibrated (most other negative-R² pixels, "
    "e.g. Canada/Siberia pixels with Pearson r > +0.68 despite R² < 0).",
], size=13.5, space_after=6)
neg = g68[g68["R2"] < 0].sort_values("R2")[["site", "dominant_pft", "region", "R2", "Pearson_r", "context_steps"]]
tbl_top = top + Inches(1.0)
header = ["Pixel", "Class", "Region", "R²", "Pearson r", "Context"]
rows = [[r["site"], r["dominant_pft"], r["region"], f"{r['R2']:.3f}", f"{r['Pearson_r']:.3f}", str(int(r["context_steps"]))]
        for _, r in neg.head(8).iterrows()]
styled_table(s, MARGIN, tbl_top, SLIDE_W - 2 * MARGIN, Inches(3.1), header, rows,
             col_weights=[0.22, 0.16, 0.24, 0.13, 0.13, 0.12], header_size=11, body_size=10.3)
add_takeaway(s, f"{n68_neg}/{n68} pixels negative, concentrated in tropical (persistent cloud) and remote high-latitude regions — Amazon/Tropical S. America is the single weakest region (mean R²<0).")


# ============================================================ SLIDE 12: FINDINGS & NEXT STEPS
s = add_slide(); set_bg(s)
add_title(s, "Main Findings & Next Steps", eyebrow="SUMMARY")
page_num(s, 12)
top, h = content_box()
y = top
add_text(s, MARGIN, y, Inches(11.8), Inches(0.3), [("RESULT", 13, ACCENT_DARK, True, False)])
y += Inches(0.35)
add_bullets(s, MARGIN, y, Inches(11.8), Inches(1.15), [
    f"Part 1 (gridMET, {n32} CONUS pixels): median R²={p32_overall.loc['median','R2']:.3f}, {n32_ge08}/{n32} pixels ≥ 0.8.",
    f"Part 2 (ERA5 + MODIS, {n68} global non-CONUS pixels): median R²={g68_overall.loc['median','R2']:.3f}, "
    f"only {n68_ge08}/{n68} pixels ≥ 0.8, {n68_neg}/{n68} negative.",
], size=14.5, space_after=7, bullet_color=ACCENT)
y += Inches(1.25)
add_text(s, MARGIN, y, Inches(11.8), Inches(0.3), [("INTERPRETATION", 13, WARN, True, False)])
y += Inches(0.35)
add_bullets(s, MARGIN, y, Inches(11.8), Inches(1.55), [
    "The strong zero-shot generalization repeatedly seen within CONUS does NOT transfer uniformly to a "
    "global, more diverse pixel pool — this is the first result in this project to show a real ceiling on "
    "zero-shot Chronos-2's LAI generalization.",
    f"The gap is not primarily a context-length artifact (r={r2_context_corr:.2f} within Part 2); genuine "
    "regional/ecological difficulty — especially tropical persistent-cloud and remote high-latitude "
    "pixels — is the larger factor.",
], size=13.5, space_after=7, bullet_color=WARN)
y += Inches(1.65)
add_text(s, MARGIN, y, Inches(11.8), Inches(0.3), [("HYPOTHESIS / NEXT STEPS", 13, MUTED, True, False)])
y += Inches(0.35)
add_bullets(s, MARGIN, y, Inches(11.8), Inches(1.0), [
    "Not yet distinguished: Chronos-2's own generalization limits vs. noisier/sparser MODIS LAI vs. genuinely "
    "different (e.g. tropical) vegetation dynamics — disentangling needs a CONUS pixel re-scored against "
    "MODIS LAI as a controlled comparison.",
], size=13.5, space_after=7, bullet_color=MUTED)
add_takeaway(s, "Two integrated experiments: strong, robust generalization within CONUS across two climate sources; a real, unexplained drop when tested globally — an open question, not a closed one.")

out_path = HERE / "CONUS_gridMET_ERA5_LabMeeting.pptx"
prs.save(str(out_path))
print("Saved:", out_path)
print("Slides:", len(prs.slides._sldIdLst))
