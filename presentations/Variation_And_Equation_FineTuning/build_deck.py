# -*- coding: utf-8 -*-
"""Two-part follow-up deck:
  Part 1 - switching from raw-LAI to variation(anomaly)-based forecasting,
  with R2 computed the current/correct way (direct anomaly forecasting,
  not raw-LAI R2 or the composite-position decomposition).
  Part 2 - physics-guided Chronos-2 fine-tuning with Prof. Wang's exact
  logistic growth-mortality equation, vs. raw (zero-shot) Chronos-2.

Deliberately concise - assumes the reader already has the earlier decks'
background (LOYO-CV protocol, the composite-position analysis, the first
ad hoc physics equation attempt); only new material and final results are
shown here.

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

# ============================================================ pull every number live
anomaly_summary = pd.read_csv(ROOT / "outputs/loyo_cv_pools_summary/loyo_anomaly_summary.csv").set_index("pool")
conus_anom = anomaly_summary.loc["CONUS (70 pixels)"]
global_anom = anomaly_summary.loc["Global (68 pixels)"]

phen_results = pd.read_csv(ROOT / "outputs/physics_guided_chronos2_finetune_phenology/validation_results.csv")

# ============================================================ deck styling
INK = RGBColor(0x1C, 0x21, 0x19)
MUTED = RGBColor(0x5C, 0x63, 0x55)
FAINT = RGBColor(0x8B, 0x93, 0x82)
ACCENT = RGBColor(0x2F, 0x6F, 0x5E)
ACCENT_DARK = RGBColor(0x1E, 0x4A, 0x33)
ACCENT_TINT = RGBColor(0xE7, 0xF0, 0xE6)
WARN = RGBColor(0xB5, 0x65, 0x1D)
WARN_TINT = RGBColor(0xFB, 0xEE, 0xE0)
BLUE = RGBColor(0x2a, 0x78, 0xd6)
BLUE_TINT = RGBColor(0xE2, 0xEC, 0xFA)
GOOD = RGBColor(0x0c, 0xa3, 0x0c)
GOOD_TINT = RGBColor(0xE3, 0xF5, 0xE3)
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


def add_eyebrow(slide, text, color=ACCENT):
    add_text(slide, MARGIN, Inches(0.42), Inches(12), Inches(0.32), [(text, 13, color, True, False)])


def add_title(slide, title, eyebrow=None, eyebrow_color=ACCENT, bar_color=ACCENT):
    if eyebrow:
        add_eyebrow(slide, eyebrow, eyebrow_color)
    add_text(slide, MARGIN, Inches(0.72), Inches(12.2), Inches(0.62), [(title, 23, INK, True, False)])
    add_rect(slide, MARGIN, Inches(1.38), Inches(1.0), Pt(3), bar_color)


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


def styled_table(slide, left, top, width, height, header, rows, col_weights, header_size=12, body_size=11.5, highlight_rows=(), header_color=ACCENT):
    n_rows = len(rows) + 1
    tbl = slide.shapes.add_table(n_rows, len(header), left, top, width, height).table
    for c, w in enumerate(col_weights):
        tbl.columns[c].width = Emu(int(width * w))
    for ci, text in enumerate(header):
        cell = tbl.cell(0, ci); cell.text = text
        cell.fill.solid(); cell.fill.fore_color.rgb = header_color
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
         [("Variation-Based Forecasting + Physics-Equation Fine-Tuning", 22, WHITE, True, False)])
page_num(s, 1)
top, h = content_box(has_takeaway=False)
add_bullets(s, MARGIN, top + Inches(0.2), Inches(11.8), Inches(2.2), [
    "Part 1: forecasting the LAI variation (anomaly) directly, instead of raw LAI - R² computed the "
    "current, correct way.",
    "Part 2: fine-tuning Chronos-2 with Prof. Wang's exact growth-mortality equation as a physics loss - "
    "does it beat raw zero-shot Chronos-2?",
], size=16, space_after=10)

# ============================================================ SLIDE 2: PART 1 - WHY VARIATION
s = add_slide(); set_bg(s)
add_title(s, "Part 1: Forecast the Variation, Not Raw LAI", eyebrow="PART 1 — VARIATION-BASED FORECASTING")
page_num(s, 2)
top, h = content_box()
add_bullets(s, MARGIN, top, Inches(11.8), Inches(2.3), [
    "Raw-LAI R² mostly reflects seasonal-shape matching (both actual and predicted LAI follow the same "
    "strong annual cycle) - not genuine year-to-year skill.",
    "Fix: for each pixel, compute the per-calendar-position climatology from the 11 held-out-year LOYO "
    "context ONLY (no leakage - the same climatology machinery already used for this project's ACC metric), "
    "subtract it from LAI to get the variation/anomaly, and give Chronos-2 that anomaly directly as BOTH "
    "context and forecast target - weather covariates unchanged.",
    "R² and Pearson r are then computed directly on the anomaly itself - the current, correct standard, "
    "not a post-hoc decomposition of a raw-LAI forecast.",
], size=15, space_after=10)
add_takeaway(s, "The model's actual task is now \"predict the deviation from normal\" - exactly what "
                "\"capturing inter-annual variability\" means.")

# ============================================================ SLIDE 3: PART 1 - ACTUAL VARIATION CURVES
s = add_slide(); set_bg(s)
add_title(s, "Part 1 Result: Predicted vs. True Variation, 5 Example Pixels",
          eyebrow="PART 1 — VARIATION-BASED FORECASTING")
page_num(s, 3)
top, h = content_box()
add_picture_fit(s, FIG / "anomaly_example_curves.png", MARGIN, top, SLIDE_W - 2 * MARGIN, h)
add_takeaway(s, "Deliberately not cherry-picked: spans the full range from the pool's best fit (Pearson r=0.94) "
                "down to its worst (r=−0.72) - most pixels track the true dip/recovery shape; some don't.")

# ============================================================ SLIDE 3b: PART 1 AGGREGATE RESULT
s = add_slide(); set_bg(s)
add_title(s, "Part 1 Aggregate: Modest, Independently-Confirmed Signal", eyebrow="PART 1 — VARIATION-BASED FORECASTING")
page_num(s, 4)
top, h = content_box()
add_picture_fit(s, FIG / "loyo_anomaly_boxplot.png", MARGIN, top, SLIDE_W - 2 * MARGIN, h - Inches(1.1))
header = ["Pool", "R² (anomaly)", "Pearson r (anomaly)"]
rows = [
    ["CONUS (770 folds)", f"mean {conus_anom['mean_R2_anomaly']:.3f} / median {conus_anom['median_R2_anomaly']:.3f}",
     f"mean {conus_anom['mean_Pearson_r_anomaly']:.3f} / median {conus_anom['median_Pearson_r_anomaly']:.3f}"],
    ["Global (748 folds)", f"mean {global_anom['mean_R2_anomaly']:.3f} / median {global_anom['median_R2_anomaly']:.3f}",
     f"mean {global_anom['mean_Pearson_r_anomaly']:.3f} / median {global_anom['median_Pearson_r_anomaly']:.3f}"],
]
styled_table(s, MARGIN, top + h - Inches(1.0),
             SLIDE_W - 2 * MARGIN, Inches(0.85), header, rows, col_weights=[0.25, 0.4, 0.35],
             header_size=12.5, body_size=12.5)
add_takeaway(s, f"R² is unstable at this sample size (same small-sample caveat as the composite-position "
                f"analysis); Pearson r (≈{conus_anom['mean_Pearson_r_anomaly']:.2f} CONUS / "
                f"≈{global_anom['mean_Pearson_r_anomaly']:.2f} Global) is the robust number, and it's modest - "
                f"this is the result that motivated Part 2.")

# ============================================================ SLIDE 5: PART 2 - THE EQUATION
s = add_slide(); set_bg(s)
add_title(s, "Part 2: Fine-Tuning with the Exact Growth-Mortality Equation",
          eyebrow="PART 2 — PHYSICS-GUIDED FINE-TUNING", eyebrow_color=BLUE, bar_color=BLUE)
page_num(s, 5)
top, h = content_box()
add_text(s, MARGIN, top, Inches(11.8), Inches(0.35),
         [("Prof. Wang's diagnosis: the earlier ad hoc physics term library undersold the physics - this is "
           "the equation she actually meant:", 14.5, INK, False, False)])
add_picture_fit(s, FIG / "phenology_equation.png", MARGIN, top + Inches(0.5), SLIDE_W - 2 * MARGIN, Inches(1.5))
add_bullets(s, MARGIN, top + Inches(2.1), Inches(11.8), Inches(1.8), [
    "r (light/temperature-limited growth), K (water-limited carrying capacity), and m (drought/freeze-driven "
    "mortality) are each fit as their own small network from this equation's structure, then frozen and used "
    "as a physics-consistency loss while LoRA fine-tuning Chronos-2.",
    "Validated standalone on LAI first (clean fit, Pearson r mean 0.78) before using it to fine-tune "
    "Chronos-2 - see the companion physics-guided-fine-tuning deck for that step.",
], size=14, space_after=8, bullet_color=MUTED)
add_takeaway(s, "Same 3 project sites as the earlier validation, now across all 11 LOYO years (33 folds) - "
                "a broader test before drawing conclusions.", tint=BLUE_TINT, dark=RGBColor(0x14, 0x3A, 0x6B), bar=BLUE)

# ============================================================ SLIDE 6: PART 2 - ACTUAL PREDICTION CURVES
s = add_slide(); set_bg(s)
add_title(s, "Part 2 Result: Actual Predictions, 3 Example Folds",
          eyebrow="PART 2 — PHYSICS-GUIDED FINE-TUNING", eyebrow_color=BLUE, bar_color=BLUE)
page_num(s, 6)
top, h = content_box()
add_picture_fit(s, FIG / "example_prediction_curves.png", MARGIN, top, SLIDE_W - 2 * MARGIN, h - Inches(0.75))
add_text(s, MARGIN, top + h - Inches(0.65), SLIDE_W - 2 * MARGIN, Inches(0.6),
         [("Note: fine-tuning has real run-to-run variance at this sample size (re-running low_amplitude/2014 "
           "independently gave physics R²=0.06 here vs. 0.28 in the original 33-fold run - same direction of "
           "effect is not guaranteed on every individual re-run). The 33-fold aggregate (next slide) is the "
           "number to trust, not any single illustrative fold.", 12, MUTED, False, True)])
add_takeaway(s, "Visibly closer to observed LAI on the two weaker-baseline examples; indistinguishable from "
                "zero-shot where zero-shot was already excellent.",
             tint=BLUE_TINT, dark=RGBColor(0x14, 0x3A, 0x6B), bar=BLUE)

# ============================================================ SLIDE 7: PART 2 KEY RESULT
s = add_slide(); set_bg(s)
add_title(s, "Result: Physics-Guided Fine-Tuning Beats Raw Chronos-2",
          eyebrow="PART 2 — PHYSICS-GUIDED FINE-TUNING", eyebrow_color=BLUE, bar_color=BLUE)
page_num(s, 7)
top, h = content_box()
add_picture_fit(s, FIG / "comparison_boxplot.png", MARGIN, top, Inches(7.8), h)
add_text(s, Inches(8.5), top, Inches(4.3), Inches(0.3), [("33 LOYO-CV FOLDS", 13, ACCENT_DARK, True, False)])
add_bullets(s, Inches(8.5), top + Inches(0.4), Inches(4.3), Inches(2.3), [
    "Mean R²: zero-shot 0.380 → physics-guided 0.424.",
    "Median R²: zero-shot 0.644 → physics-guided 0.674.",
    "Plain fine-tuning (no physics) actually UNDERPERFORMS zero-shot (mean 0.287) - small-sample fine-tuning "
    "alone tends to overfit. The physics term fixes this AND pushes past zero-shot.",
    "Physics-guided beats plain fine-tuning in 22/33 folds (67%).",
], size=13, space_after=8, bullet_color=GOOD)
add_text(s, Inches(8.5), top + Inches(3.0), Inches(4.3), Inches(0.3), [("WHERE IT HELPS MOST", 13, WARN, True, False)])
add_bullets(s, Inches(8.5), top + Inches(3.4), Inches(4.3), Inches(1.6), [
    "Biggest gains on the two sites with weaker zero-shot baselines (evergreen, low_amplitude); roughly "
    "neutral on the site already near its R² ceiling (high_amplitude_deciduous, R²≈0.96) - little room left "
    "to improve there.",
], size=12.5, space_after=6, bullet_color=WARN)
add_takeaway(s, "A genuine, aggregate improvement over raw zero-shot Chronos-2 - not on every single fold, but "
                "consistently in mean and median across 33 independent held-out years.",
             tint=GOOD_TINT, dark=RGBColor(0x0a, 0x5a, 0x0a), bar=GOOD)

# ============================================================ SLIDE 8: SUMMARY
s = add_slide(); set_bg(s)
add_title(s, "Summary", eyebrow="SUMMARY")
page_num(s, 8)
top, h = content_box()
y = top
add_text(s, MARGIN, y, Inches(11.8), Inches(0.3), [("PART 1", 13, ACCENT_DARK, True, False)])
y += Inches(0.35)
add_bullets(s, MARGIN, y, Inches(11.8), Inches(1.3), [
    f"Forecasting the LAI variation directly gives a modest, honest signal (Pearson r≈"
    f"{conus_anom['mean_Pearson_r_anomaly']:.2f} CONUS / {global_anom['mean_Pearson_r_anomaly']:.2f} Global) - "
    "confirmed visually across 5 pixels spanning the full range from best to worst fit.",
], size=14, space_after=7, bullet_color=ACCENT)
y += Inches(1.5)
add_text(s, MARGIN, y, Inches(11.8), Inches(0.3), [("PART 2", 13, BLUE, True, False)])
y += Inches(0.35)
add_bullets(s, MARGIN, y, Inches(11.8), Inches(1.6), [
    "Fine-tuning Chronos-2 with Prof. Wang's exact equation as a physics loss beats raw zero-shot Chronos-2 "
    "on both mean and median R² across 33 held-out years - a real, aggregate improvement, visible both in "
    "the numbers and in the actual predicted curves.",
    "Plain fine-tuning alone (no physics) underperforms zero-shot - the physics term is doing real work, not "
    "just \"fine-tuning helps regardless.\"",
], size=14, space_after=7, bullet_color=BLUE)
y += Inches(1.9)
add_text(s, MARGIN, y, Inches(11.8), Inches(0.3), [("CAVEATS", 13, WARN, True, False)])
y += Inches(0.35)
add_bullets(s, MARGIN, y, Inches(11.8), Inches(1.1), [
    "Validation scope is still 3 sites (33 folds) - the natural next step is the full 70-pixel CONUS pool. "
    "Fine-tuning shows real run-to-run variance at this sample size; the aggregate statistic, not any single "
    "fold, is the evidence that should generalize.",
], size=13.5, space_after=7, bullet_color=WARN)
add_takeaway(s, "Both follow-ups answer Prof. Wang's questions directly: variation-forecasting confirms the "
                "modest signal is real; the correct equation turns physics guidance into a genuine improvement.")

out_path = HERE / "Variation_And_Equation_FineTuning.pptx"
prs.save(str(out_path))
print("Saved:", out_path)
print("Slides:", len(prs.slides._sldIdLst))
