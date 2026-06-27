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
JP/EN analyses now run region-wide **in parallel** to the original Fukui runs; the Fukui
confirmatory results are byte-identical and retained. See [[hokuriku-scope-expansion]] memo and
`make hokuriku-all`. Intentionally-Fukui pieces (within-POI paired test, the Fukui JP/EN
confirmatory deck) are left Fukui by design — not a scope miss.

## 3. Codebook transfer fix (simplified → traditional)
The reviewed Chinese codebook keywords are all **simplified**; Google reviews are ~75%
**traditional**, so friction codes silently missed (e.g. 廁所 vs codebook 厕所, 人擠人 vs 挤,
貴 vs 贵). Fix: `load_chinese_codebook()` now expands every keyword to its traditional form at
load time via `zhconv` (single chokepoint; tagging + reviewed-terms both inherit it). Effect:
Google-zh negatives-with-friction 7% → 22%; XHS unchanged; **Lynn's reviewed CSV is never edited.**
Remaining colloquial review-register gaps (收舖, 全是人, 態度冰冷, …) are staged as candidates
for human review in `docs/codebook_templates/chinese_google_review_friction_candidates.csv`
(status=pending, reviewer=auto). Until Lynn approves, Chinese friction is **under-counted**.

## 4. Folding Chinese into the POI pipeline
`scripts/build_chinese_folded_multilingual.py` is a **local post-sync stage**: it reads the
synced `tagged_reviews_multilingual.csv` (the `multilingual_review_analysis/` dir is synced from
the sibling `english-fukui-tourism` repo, which is **not present on this machine**, so the fold
cannot live upstream here), promotes zh rows to `language_group='chinese'`, and writes
`..._chinese_folded.csv` (synced file untouched). `build_nudge_opportunity_analysis.py` and
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
`is_fix_it`: Higashi Chaya District **in**, TAD Toyama **out**. *Correction:* this flip does **not**
trace to a closes-too-early / opening-hours signal — the tagged data has **zero**
`opening_hours_availability` tags for Higashi Chaya Chinese reviews (收舖 is uncoded, on the pending
candidate list). The real driver was **polarity-blind `transport_access` matching on 2 reviews**, one
of which is a 5★ crowd-avoidance review, so the flip is spurious; the orchestrator is removing it by
fixing the gate. `is_promote_it_strict`: 0 → 1 (Asuwa River cherry promenade).
`off_peak_alternative_prompt` impact Medium → High (Chinese crowding evidence). Promotion was
run into the committed headline but **left uncommitted** in git, pending this review.

## 5. Known limitations (for the reviewer)
- **POI-level Chinese is thin**: median ~3 reviews/POI; only 5/56 POIs clear `LOW_CONFIDENCE_N=10`; 16 POIs have ≤2. Per-POI Chinese friction (and the fix-it/promote flips above) may rest on 1–2 reviews — directional, not confirmatory.
- **SnowNLP sentiment is unvalidated** on short Chinese review text (median ~30 chars). Of the 243 zh Google reviews, SnowNLP tags **81 "negative"**, but **64 of those 81 (79%) are rated 4-5 stars** and only **6 are ≤2 stars** — i.e. the "negative" category is mostly false negatives. The Google-zh "0.63 / 33% negative" figure is therefore **not a reportable Chinese sentiment outcome**; POI positives correctly use star ratings instead.
- **Chinese friction tags are topic-presence, not polarity.** The friction codes are keyword matches that fire regardless of sentiment — e.g. `transport_access` tags 5★ reviews like 自駕停車很方便 ("parking very convenient") and 搭巴士很快抵達 ("quick by bus"). A Chinese "friction" tag means the topic was *mentioned*, not that there was a problem, so per-POI Chinese "friction" overstates problems. Human validation (Lynn) pending.
- **Mixed instruments** across languages: EN=VADER, JP=oseti, CN=SnowNLP. Cross-language *sentiment* comparison is apples-to-oranges (caveated in code); friction/topic comparison is keyword-based and more comparable.
- **Codebook transfer is mechanical-only** (zhconv) until Lynn approves the colloquial candidates.
- **Provenance**: `build_chinese_google_reviews_dataset.py` and `build_chinese_folded_multilingual.py` now emit manifests (SHA + dep versions + caveats), consistent with the rest of the pipeline.

## 6. Reproducibility
`make hokuriku-all`, `make poi-opportunity` / `make nudge-analysis` (now depend on the fold),
`make cn-anchor-figure`. New deps: `zhconv` (in `requirements.txt` + sentiment bootstrap lock).
Caveat: `multilingual_review_analysis/` is a synced artifact; `make multilingual-reviews` cannot
run on this machine (sibling repo is a Mac path) — a fully clean-room rebuild requires the sibling repo.
