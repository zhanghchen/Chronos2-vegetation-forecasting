# -*- coding: utf-8 -*-
"""Progress-update deck for Prof. Wang, English, three parts:
  Part 1 - last week's pooled LAI-anomaly boxplot redone, broken down by
           dominant vegetation class.
  Part 2 - why the GPP download previously only returned 2021-2022 (wrong
           MODIS product, not a request error), and the fix.
  Part 3 - first zero-shot GPP vs. LAI comparison on real GPP data
           (20-site sample; full 70-site run still in progress).

Same visual identity as presentations/Variation_And_Equation_FineTuning/
(this project's established deck style for Prof. Wang updates).

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
SITES_20 = ["evergreen", "high_amplitude_deciduous", "low_amplitude", "mixed_forest_grass",
            "px011_grass_man", "px067_grass_man", "px010_grass_nat", "px046_grass_nat",
            "px008_shrubs_bd", "px064_shrubs_bd", "px009_shrubs_nd", "px057_shrubs_nd",
            "px007_shrubs_ne", "px053_shrubs_ne", "px005_trees_bd", "px063_trees_bd",
            "px006_trees_nd", "px068_trees_nd", "px004_trees_ne", "px065_trees_ne"]

lai_all = pd.read_csv(ROOT / "outputs/loyo_cv_anomaly/all_folds_anomaly.csv")
lai20 = lai_all[lai_all["site"].isin(SITES_20)]
gpp20 = pd.read_csv(ROOT / "outputs/loyo_cv_gpp_anomaly/all_folds_gpp_anomaly.csv")

pft = pd.read_csv(ROOT / "data/processed/pft_diverse_pixels.csv")[["pixel_id", "dominant_pft"]]
lai20_pft = lai20.merge(pft, left_on="site", right_on="pixel_id")
gpp20_pft = gpp20.merge(pft, left_on="site", right_on="pixel_id")

conus_pft_r = pd.read_csv(ROOT / "outputs/loyo_cv_anomaly_by_pft/conus_by_pft_pearson_r.csv").set_index("dominant_pft")
global_pft_r = pd.read_csv(ROOT / "outputs/loyo_cv_anomaly_by_pft/global_by_pft_pearson_r.csv").set_index("dominant_pft")

# ============================================================ deck styling (matches Variation_And_Equation_FineTuning)
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
         [("GPP vs. LAI: Vegetation-Class Breakdown, Data Fix, and First Zero-Shot Comparison", 21, WHITE, True, False)])
page_num(s, 1)
top, h = content_box(has_takeaway=False)
add_bullets(s, MARGIN, top + Inches(0.2), Inches(11.8), Inches(2.6), [
    "Part 1: last week's pooled LAI-anomaly boxplot, redone broken down by dominant vegetation class.",
    "Part 2: why the GPP download previously only returned 2021-2022 - wrong MODIS product, not a request "
    "error - and the fix.",
    "Part 3: first zero-shot GPP vs. LAI comparison on real GPP data (same sites, same LOYO-CV protocol).",
], size=16, space_after=10)

# ============================================================ SLIDE 2: PART 1 - WHY BREAK DOWN BY CLASS
s = add_slide(); set_bg(s)
add_title(s, "Part 1: LAI Anomaly, Broken Down by Vegetation Class", eyebrow="PART 1 — VEGETATION-CLASS BREAKDOWN")
page_num(s, 2)
top, h = content_box()
add_bullets(s, MARGIN, top, Inches(11.8), Inches(2.9), [
    "Last week's result pooled every vegetation type into one CONUS boxplot (770 folds) and one Global "
    "boxplot (748 folds) - this hides which vegetation types Chronos-2 is actually good at.",
    "Reran the same already-computed fold-level results (no new model calls), grouped by each site's "
    "dominant vegetation class instead - using the project's existing ESA-CCI-derived PFT classification, "
    "not the informal site-name suffix.",
    "Pseudo-replication fix: grouping at the fold level pools 11 years per site into each class's "
    "distribution, which overstates independence (11 years at one site aren't 11 independent draws). "
    "The honest sample size per class is its site count, not its fold count.",
], size=15, space_after=9)
add_takeaway(s, "Fixed two ways, both shown next: collapse each site to its 11-year mean first (one point "
                "per site), and check the ranking separately for each of the 11 years.")

# ============================================================ SLIDE 3: PART 1 - PER-SITE BOXPLOTS
s = add_slide(); set_bg(s)
add_title(s, "Shrubs and Grasses Forecast Better Than Trees, in Both Pools", eyebrow="PART 1 — VEGETATION-CLASS BREAKDOWN")
page_num(s, 3)
top, h = content_box()
add_picture_fit(s, FIG / "loyo_anomaly_by_pft_persite_boxplots.png", MARGIN, top, SLIDE_W - 2 * MARGIN, h)
add_takeaway(s, "Each site collapsed to its 11-year mean first, then boxplotted (dots = individual sites) - "
                "a class with 6 sites shows 6 points here, not 66 pooled folds.")

# ============================================================ SLIDE 4: PART 1 - BY-YEAR ROBUSTNESS CHECK
s = add_slide(); set_bg(s)
add_title(s, "Robustness Check: Is the Ranking Stable Year by Year?", eyebrow="PART 1 — VEGETATION-CLASS BREAKDOWN")
page_num(s, 4)
top, h = content_box()
add_picture_fit(s, FIG / "loyo_anomaly_by_pft_byyear.png", MARGIN, top, SLIDE_W - 2 * MARGIN, h)
add_takeaway(s, "Shrub-family lines (orange/brown) sit above tree-family lines (green) in most individual "
                "CONUS years, not just on average - this isn't one or two outlier years driving the effect.")

# ============================================================ SLIDE 5: PART 1 - SUMMARY TABLE
s = add_slide(); set_bg(s)
add_title(s, "Part 1 Summary: Median Pearson r by Class Family (Per-Site)", eyebrow="PART 1 — VEGETATION-CLASS BREAKDOWN")
page_num(s, 5)
top, h = content_box()
header = ["Class family", "CONUS median r", "Global median r"]
rows = [
    ["Shrubs", "0.26 – 0.50", "0.14 – 0.25"],
    ["Grass", "0.19 – 0.23", "0.17 – 0.19"],
    ["Trees", "0.16 – 0.22", "0.07 – 0.19"],
]
styled_table(s, MARGIN, top, SLIDE_W - 2 * MARGIN, Inches(1.8), header, rows, [0.34, 0.33, 0.33])
add_bullets(s, MARGIN, top + Inches(2.1), Inches(11.8), Inches(2.2), [
    "Ranges computed from per-site 11-year means (honest n), not pooled folds - shrubs > grass > trees "
    "still holds; Global's grass/trees ranges now overlap slightly once the inflated fold count is "
    "corrected for, so that distinction is less crisp in Global than in CONUS.",
    "Plausible mechanism (a hypothesis prompted by the pattern, not tested directly here): trees have "
    "slower, inertia-dominated canopy dynamics, so the year-to-year anomaly signal is small relative to "
    "noise; shrubs/grass respond faster to the same interannual weather drivers Chronos-2 sees in context.",
], size=14, space_after=9)
add_takeaway(s, "CONUS classes all have 6+ sites; a few Global classes have only 2-3 (TREES_ND, "
                "SHRUBS_ND/NE/BE) - treat those as suggestive, not definitive.")

# ============================================================ SLIDE 6: PART 2 - ROOT CAUSE
s = add_slide(); set_bg(s)
add_title(s, "Part 2: Why GPP Was Reported as “Only 2021-2022”", eyebrow="PART 2 — GPP DATA FIX")
page_num(s, 6)
top, h = content_box()
add_bullets(s, MARGIN, top, Inches(11.8), Inches(1.3), [
    "Not a request error - the original script's date range was correctly specified (startDate 2000-01-01). "
    "Not an actual limitation of MODIS GPP data. It was the wrong product.",
], size=15.5, space_after=10)
header = [" ", "Product requested (wrong)", "Product needed (fix)"]
rows = [
    ["Product", "MOD17A2H.061", "MOD17A2HGF.061 (“GF” = gap-filled)"],
    ["TemporalExtentStart (AppEEARS catalog)", "2021-01-01", "2000-01-01"],
    ["Layers / scale factor", "Gpp_500m, Psn_QC_500m, 0.0001", "same layers, same scale factor"],
]
styled_table(s, MARGIN, top + Inches(1.5), SLIDE_W - 2 * MARGIN, Inches(2.6), header, rows, [0.3, 0.35, 0.35],
             body_size=12.5)
add_takeaway(s, "Confirmed directly against AppEEARS' own product catalog (GET /api/product), not inferred "
                "from behavior - MOD17A2H.061 is a genuinely newer collection LP DAAC only serves from 2021.")

# ============================================================ SLIDE 7: PART 2 - SANITY CHECK
s = add_slide(); set_bg(s)
add_title(s, "Before Trusting the New Data: a Scale Sanity Check", eyebrow="PART 2 — GPP DATA FIX")
page_num(s, 7)
top, h = content_box()
add_bullets(s, MARGIN, top, Inches(11.8), Inches(2.6), [
    "Good-QC Gpp_500m values for forest/grass sites come out in the 0-0.1 kg C/m²/8-day range - looked "
    "suspiciously low at first glance, the same kind of place a 10x LAI scale-factor bug hid earlier in "
    "this project.",
    "Summed to an annual total per site instead of eyeballing 8-day values: e.g. px005_trees_bd "
    "(broadleaf-deciduous forest) comes out to ~0.9–1.0 kg C/m²/year across 2015–2018.",
    "This lines up with published typical annual GPP for temperate forest/grassland - confirming the "
    "scale factor is correct, not a repeat of the earlier bug.",
], size=15.5, space_after=12)
add_takeaway(s, "Verified empirically before using the data, rather than assuming either way.")

# ============================================================ SLIDE 8: PART 3 - PROTOCOL + HEADLINE RESULT
s = add_slide(); set_bg(s)
add_title(s, "Part 3: First Zero-Shot GPP vs. LAI Comparison", eyebrow="PART 3 — GPP vs. LAI, ZERO-SHOT")
page_num(s, 8)
top, h = content_box()
add_bullets(s, MARGIN, top, Inches(11.8), Inches(1.3), [
    "Identical LOYO-CV anomaly protocol already used for LAI (same 12-year rolling window, same "
    "no-leakage climatology, same weather covariates) - only the target column changes. Same sites, "
    "same folds, same model: apples-to-apples.",
], size=15, space_after=8)
header = [" ", "mean R²", "median R²", "mean Pearson r", "median Pearson r"]
rows = [
    ["LAI anomaly (20 sites)", f"{lai20['R2_anomaly'].mean():.3f}", f"{lai20['R2_anomaly'].median():.3f}",
     f"{lai20['Pearson_r_anomaly'].mean():.3f}", f"{lai20['Pearson_r_anomaly'].median():.3f}"],
    ["GPP anomaly (20 sites)", f"{gpp20['R2_anomaly'].mean():.3f}", f"{gpp20['R2_anomaly'].median():.3f}",
     f"{gpp20['Pearson_r_anomaly'].mean():.3f}", f"{gpp20['Pearson_r_anomaly'].median():.3f}"],
]
styled_table(s, MARGIN, top + Inches(1.5), SLIDE_W - 2 * MARGIN, Inches(1.6), header, rows,
             [0.26, 0.185, 0.185, 0.185, 0.185], highlight_rows=(1,))
add_takeaway(s, f"220 folds (20 sites × 11 LOYO years), all 8 CONUS vegetation classes represented. "
                f"GPP beats LAI on every metric shown, zero-shot, before any physics guidance.")

# ============================================================ SLIDE 9: PART 3 - BY CLASS
s = add_slide(); set_bg(s)
add_title(s, "GPP Beats LAI in 7 of 8 Vegetation Classes", eyebrow="PART 3 — GPP vs. LAI, ZERO-SHOT")
page_num(s, 9)
top, h = content_box()
order = lai20_pft.groupby("dominant_pft")["Pearson_r_anomaly"].mean().sort_values(ascending=False).index.tolist()
header = ["Vegetation class", "LAI mean r", "GPP mean r", "n folds"]
rows = []
for cls in order:
    lai_r = lai20_pft[lai20_pft["dominant_pft"] == cls]["Pearson_r_anomaly"].mean()
    gpp_r = gpp20_pft[gpp20_pft["dominant_pft"] == cls]["Pearson_r_anomaly"].mean()
    n = (lai20_pft["dominant_pft"] == cls).sum()
    rows.append([cls.replace("_", " ").title(), f"{lai_r:.3f}", f"{gpp_r:.3f}", str(n)])
styled_table(s, MARGIN, top, SLIDE_W - 2 * MARGIN, Inches(4.6), header, rows, [0.34, 0.22, 0.22, 0.22])
add_takeaway(s, "Grasses show the largest relative gain; needleleaf-evergreen trees is the one class "
                "essentially tied (GPP 0.226 vs. LAI 0.229).")

# ============================================================ SLIDE 10: INTERPRETATION + NEXT STEPS
s = add_slide(); set_bg(s)
add_title(s, "Interpretation and Next Steps", eyebrow="NEXT STEPS")
page_num(s, 10)
top, h = content_box()
add_bullets(s, MARGIN, top, Inches(11.8), Inches(2.6), [
    "Consistent with Prof. Wang's expectation that GPP is the more weather-coupled, more directly "
    "forecastable target - GPP responds to the same short-term weather drivers Chronos-2 sees in its "
    "covariates more directly than LAI, which is a slower-integrating structural/canopy variable. "
    "(Interpretation - not yet tested directly.)",
    "This zero-shot result does not yet test whether physics-guided fine-tuning helps GPP more than LAI - "
    "it only establishes that the baseline gap between the two targets is real and goes in the expected "
    "direction, before spending effort on the fine-tuning comparison.",
], size=15.5, space_after=12)
add_bullets(s, MARGIN, top + Inches(2.7), Inches(11.8), Inches(1.8), [
    "Next: confirm this result holds at the full 70-site scale (download in progress on AppEEARS).",
    "Then: physics-guided fine-tuning on GPP, using the existing phenology equation and fine-tuning "
    "machinery (already supports GPP as --target-col) - deliberately not started yet, per the agreed order of work.",
], size=15.5, space_after=10, bullet_color=BLUE)
add_takeaway(s, "Order of work, as agreed: data first, zero-shot baseline second (done here), physics-"
                "guided fine-tuning on GPP last.", tint=BLUE_TINT, dark=RGBColor(0x1A, 0x3A, 0x66), bar=BLUE)

prs.save(HERE / "GPP_vs_LAI_Progress_Update.pptx")
print("Saved", HERE / "GPP_vs_LAI_Progress_Update.pptx")
