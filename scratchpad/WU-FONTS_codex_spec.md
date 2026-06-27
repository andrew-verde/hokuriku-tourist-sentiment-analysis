# Task: enlarge figure text for presentation legibility

Caveman mode: terse, full substance. Do NOT commit. Repo:
/home/andrewgreen/Repositories/andrew-verde/hokuriku-tourist-sentiment-analysis. Python: `.venv/bin/python`.

## Problem
The SVG figures embedded in the seminar deck / dashboard have text that is too small to read when
projected. Increase font sizes for presentation legibility WITHOUT causing overlap, clipping, or
collisions.

## Scope — the SVG figure generators
- `scripts/build_nudge_figures.py` (nudge_aspect / nudge_poi / nudge_info figures)
- `scripts/build_statistical_test_figures.py` (H1/H2/H3, cross-source, text-length, overview, etc.)
- `scripts/build_cn_anchor_comparison_figure.py` (output/presentation_safe/multilingual/*.svg:
  cn anchor, volume_context, sentiment_share_by_language_source, statistical_evidence_summary)

Do NOT touch non-figure code, data, provenance, or the slide/dashboard HTML text.

## What to change
- Raise the SMALL font sizes first — tick labels, point/halo labels, axis annotations, legend text,
  footnotes (the size=9/10/12/13 values). Bring the smallest readable text up to a presentation
  floor (target: nothing below ~16px in the rendered figure; bump titles/subtitles proportionally so
  hierarchy is preserved).
- Scale CONSISTENTLY across all three generators so figures look like one family. Prefer raising a
  shared base/scale (many of these helpers take a `size=` param with defaults) rather than hand-
  editing each call where a default exists.
- CRITICAL — prevent overlap/clipping when text grows:
  - widen left/right/top margins, row heights, bar spacing, and the canvas width/height
    proportionally so larger labels still fit inside the viewBox and don't collide;
  - keep label-wrapping / truncation helpers working (e.g. `_wrapped_label_lines`, `_safe_label`)
    — raise their width budgets if needed so labels don't get cut mid-word;
  - verify the viewBox still contains all drawn elements.

## Verify (you cannot "see" SVGs — verify structurally + by rasterizing)
1. Regenerate every figure: `make nudge-figures statistical-test-figures cn-anchor-figure`
   (and `presentation-safe` if it emits figures). All must build clean.
2. Regenerate consumers so embeds refresh: `make nudge-slides nudge-pptx dashboard`.
3. `.venv/bin/python -m pytest -q` stays green (if a figure test asserts on an exact font-size or
   canvas dimension, update it as a legitimate snapshot with a one-line comment — do not weaken
   data assertions).
4. Structural overlap check: for each regenerated SVG, confirm every `<text>`/element x,y stays
   within the declared viewBox width/height (no negative coords, nothing past the edges). Report any
   figure where text now exceeds bounds and FIX it (grow canvas/margins) before finishing.
5. Rasterize 3 representative figures to PNG so the orchestrator can eyeball them — e.g. use the
   same rasterization the pptx builder uses, or cairosvg/rsvg if available — and write the PNGs to
   `scratchpad/fontcheck_<name>.png`. List the paths in your report.

## Report (caveman)
Which size defaults/params you raised (old→new) per generator; canvas/margin/spacing adjustments
made to avoid overlap; any figure that needed bounds fixes; the 3 rasterized PNG paths; test +
regen result. Flag anything that still looks tight.
