# Chinese-language evidence strategy & Hokuriku scope decisions

Canonical record of the decisions taken in the 2026-06-27 session that expanded the
project from Fukui-only to all of Hokuriku and reworked the Chinese-language evidence.
Written for an independent rigor/reproducibility review.

## 1. Two Chinese sources, deliberately split by role

| Source | Role | Why |
|---|---|---|
| **Chinese-language Google reviews** (`chinese`) | **Primary statistical evidence** | POI-linked (56 POIs), star-rated (real outcome variable), region-wide (Kanazawa 113 / Toyama 88 / Fukui 42), scored with the same reviewed codebook as EN/JP, organic post-visit sampling. |
| **Xiaohongshu (XHS)** | **Demoted directional guidepost** | Fukui-only, no POI link, no rating, ~35% fan-pilgrimage skew, promotional pre-trip social text. Useful for *direction of demand/opinion*, not as a measurement input. |

**Decision (user, explicit):** rely on the Chinese Google data for real statistical
evidence; keep XHS only as a demoted, directional guidepost.

### Convergence: the two sources point the same way
Convergence rests on the **keyword-based** evidence (topic and friction codes), which is
comparable across the two sources; it deliberately does **not** rest on SnowNLP sentiment
(see §5 — SnowNLP negatives are mostly false on short text, so the sentiment shares are not
a usable convergence signal).
- **Top-6 topics: 5/6 shared** (temples_spiritual, history_culture, scenic_nature, food_local_cuisine, dinosaurs_museums).
- **Top-6 friction: 5/6 shared** — `transport_access` is the #1 friction in **both**; waiting_crowding, booking_ticketing, price_value, cleanliness_comfort all shared.

This topic/friction convergence is *why* XHS is safe to keep as a directional guidepost: it
agrees with the statistically stronger Google evidence on the dominant keyword/comment
themes, while the Google data (star ratings, POI-linked) is what we actually measure on.

## 2. Hokuriku expansion done as "run both"
JP/EN analyses now run region-wide **in parallel** to original Fukui runs; Fukui
confirmatory results are retained. See `make hokuriku-all` and
[`repo_guidance.md`](repo_guidance.md). Intentionally Fukui-only tests remain
Fukui by design.

## 3. Codebook transfer fix (simplified → traditional)
The reviewed Chinese codebook keywords are all **simplified**; Google reviews are ~75%
**traditional**, so friction codes silently missed (e.g. 廁所 vs codebook 厕所, 人擠人 vs 挤,
貴 vs 贵). Fix: `load_chinese_codebook()` now expands every keyword to its traditional form at
load time via `zhconv` (single chokepoint; tagging + reviewed-terms both inherit it). Effect:
Google-zh negatives-with-friction 7% → 22%; XHS unchanged; **Lynn's reviewed CSV is never edited.**
Colloquial review-register gaps (收舖, 全是人, 態度冰冷, …) were staged in
`docs/codebook_templates/chinese_google_review_friction_candidates.csv` and have now been
**reviewed and approved by Lynn** (status=reviewed, reviewer=Lynn). The loader merges
approved candidates at the same chokepoint, so they are applied in tagging. Effect: folded
Chinese any_friction coverage 13.6% → 16.5% (≤3★ Chinese 7/30 → 11/30). The approved-candidate
merge is gated on `status=reviewed`, so any future pending terms stay excluded until approved.

## 4. Folding Chinese into the POI pipeline
`scripts/build_chinese_folded_multilingual.py` is a **local post-validation stage**:
it reads the external `tagged_reviews_multilingual.csv` from a separately
obtained `platform-review-scraper` checkout, promotes zh rows to
`language_group='chinese'`, and writes
`..._chinese_folded.csv` (external file untouched). `build_nudge_opportunity_analysis.py` and
`build_poi_opportunity_index.py` now read the folded file by default.

### CN-code → multilingual-aspect mapping (researcher judgment)
All six POI-index `NUDGEABLE_FRICTION_ASPECTS` map 1:1. Enjoyment side is partial:

| multilingual aspect | ← CN codebook code |
|---|---|
| transport_access, wayfinding_signage, staff_communication, booking_ticketing, waiting_crowding, price_value, cleanliness_comfort, opening_hours_availability, itinerary_fit_time_cost, accessibility_mobility, food_amenities_gap | same name (1:1) |
| english_information_gap | language_information_gap |
| scenic_value | scenic_nature |
| worthwhile_destination | recommendation_intent |
| friendly_service, underpromoted_feature, easy_if_guided, good_for_itinerary_bundle | *no CN equivalent → 0* |

Consequence: Chinese contributes fully to the **fix-it** lever, partially to **promote-it**
(2 of 3 draw aspects; the 4 zeroed aspects under-count Chinese promote-it draw). Star ratings
drive the positive signal directly, so SnowNLP noise does not corrupt promote-it.

### Headline effect of the fold
A naive fold (pre-gate) produced thin-Chinese-driven flips — e.g. Higashi Chaya District into
`is_fix_it` and Asuwa River into `is_promote_it_strict` — each resting on 1–6 Chinese reviews. A
**language-aware confidence gate** now blocks any flip whose driving aspect is supported by
<3 tags or is plurality-driven by a per-POI-thin language group (n<10 at that POI), so those
spurious flips are removed: Higashi Chaya is **not** `is_fix_it` (Chinese n=9 < 10, gate blocked)
even though 收舖 now codes `opening_hours_availability` after Lynn's approval, and Asuwa is **not**
`is_promote_it_strict` (Chinese n=6 < 10). Region-wide totals after the gate + approved keywords:
**10 fix-it, 7 promote-it, 0 promote-it-strict**. Surviving flips pass via non-thin EN/JP aspects.
`off_peak_alternative_prompt` impact Medium → High (Chinese crowding evidence; directional). Promotion was
run into the committed headline but **left uncommitted** in git, pending this review.

## 5. Known limitations (for the reviewer)
- **POI-level Chinese is thin**: median ~3 reviews/POI; only 5/56 POIs clear `LOW_CONFIDENCE_N=10`; 16 POIs have ≤2. The language-aware gate (§4) now prevents this thinness from driving headline flips; per-POI Chinese friction remains directional, not confirmatory.
- **SnowNLP sentiment is unvalidated** on short Chinese review text (median ~30 chars). Of the 243 zh Google reviews, SnowNLP tags **81 "negative"**, but **64 of those 81 (79%) are rated 4-5 stars** and only **6 are ≤2 stars** — i.e. the "negative" category is mostly false negatives. The Google-zh "0.63 / 33% negative" figure is therefore **not a reportable Chinese sentiment outcome**; POI positives correctly use star ratings instead.
- **Chinese friction tags are topic-presence, not polarity.** The friction codes are keyword matches that fire regardless of sentiment — e.g. `transport_access` tags 5★ reviews like 自駕停車很方便 ("parking very convenient") and 搭巴士很快抵達 ("quick by bus"). A Chinese "friction" tag means the topic was *mentioned*, not that there was a problem, so per-POI Chinese "friction" overstates problems. Lynn has approved the colloquial *keyword vocabulary* (improving recall), but the tagging is still polarity-blind — keyword approval does not add negation/positive-context handling, so this limitation stands.
- **Mixed instruments** across languages: EN=VADER, JP=oseti, CN=SnowNLP. Cross-language *sentiment* comparison is apples-to-oranges (caveated in code); friction/topic comparison is keyword-based and more comparable.
- **Codebook transfer** is zhconv s2t expansion plus Lynn-approved colloquial candidates (merged at the loader chokepoint, gated on status=reviewed); tagging recall improved, polarity-blindness unchanged.
- **Provenance**: `build_chinese_google_reviews_dataset.py` and `build_chinese_folded_multilingual.py` now emit manifests (SHA + dep versions + caveats), consistent with the rest of the pipeline.

## 6. Reproducibility
`make hokuriku-all`, `make poi-opportunity` / `make nudge-analysis` (now depend on the fold),
`make cn-anchor-figure`. New deps: `zhconv` (in `requirements.txt` + sentiment bootstrap lock).
`multilingual_review_analysis/` is a private external artifact. A full rebuild
requires a separately obtained source checkout supplied through
`PLATFORM_REVIEW_SCRAPER_DIR`.
