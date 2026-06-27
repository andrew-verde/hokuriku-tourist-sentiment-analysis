#!/usr/bin/env python3
"""Build the next-semester nudge experiment register as provenance-locked HTML.

The register turns exploratory nudge opportunities into concrete experiment
cards for stakeholder planning. Every statistic, POI name, aspect code, nudge
type, and mechanism is fetched live from aggregate CSV outputs and wrapped in a
provenance anchor. Missing inputs or missing rows fail loud.
"""

from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.build_pbl_dashboard import _sha256, disp_to_text, pfmt  # noqa: E402


ROOT = Path(__file__).resolve().parent.parent
OUT_HTML = ROOT / "docs" / "nudge_experiment_register.html"
SOURCES = {
    "aspect": ROOT / "output" / "nudge_analysis" / "aspect_opportunity_map.csv",
    "poi": ROOT / "output" / "nudge_analysis" / "poi_opportunity_index.csv",
    "tax": ROOT / "output" / "nudge_analysis" / "nudge_taxonomy.csv",
    "priority": ROOT / "output" / "nudge_analysis" / "cross_language_solution_priorities.csv",
}
FORBIDDEN_COLUMNS = {
    "review_text",
    "text_content",
    "review_author",
    "author",
    "author_url",
    "note_url",
    "source_url",
    "url",
    "place_id",
    "poi_id",
    "review_id",
    "source_review_id",
    "source_record_id",
}

DATA: dict[str, pd.DataFrame] = {}
SHA: dict[str, str] = {}
COMMAND: dict[str, str] = {}
REFS: list[dict[str, object]] = []


class RegisterBuildError(RuntimeError):
    pass


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def dashboard_css() -> str:
    """Reuse the CSS literal from the dashboard builder instead of copying it."""
    source = (ROOT / "scripts" / "build_pbl_dashboard.py").read_text(encoding="utf-8")
    match = re.search(r"css = r\"\"\"\n(.*?)\n\"\"\"", source, flags=re.S)
    if not match:
        raise RegisterBuildError("Could not locate dashboard CSS literal")
    return match.group(1)


def load() -> None:
    for sid, path in SOURCES.items():
        if not path.exists():
            raise RegisterBuildError(f"missing source: {path}")
        df = pd.read_csv(path)
        blocked = sorted(FORBIDDEN_COLUMNS & set(df.columns))
        if blocked:
            raise RegisterBuildError(f"{path} contains forbidden columns: {', '.join(blocked)}")
        DATA[sid] = df
        SHA[sid] = _sha256(path)
        COMMAND[sid] = str(df["command"].dropna().iloc[0]) if "command" in df.columns and df["command"].notna().any() else ""


def stat(src_id: str, getter, fmt="{}", unit: str = "", field: str = "") -> str:
    """Resolve one live value and wrap it in a dashboard-style provenance anchor."""
    raw = getter(DATA[src_id])
    disp = fmt(raw) if callable(fmt) else fmt.format(raw) + unit
    src_path = rel(SOURCES[src_id])
    sha = SHA[src_id]
    cmd = COMMAND.get(src_id, "")
    REFS.append({
        "value": disp_to_text(str(disp)),
        "raw": raw,
        "source": src_path,
        "field": field,
        "sha256": sha,
        "command": cmd,
    })
    tip = (
        f"raw value: {raw}\nfield: {field}\nsource: {src_path}\n"
        f"sha256: {sha}\nscript: {cmd}"
    )
    return (
        f'<a class="stat" href="{src_path}" target="_blank" '
        f'title="{html.escape(tip)}" data-raw="{html.escape(str(raw))}" '
        f'data-source="{src_path}" data-source-path="{src_path}" '
        f'data-field="{html.escape(field)}" data-sha256="{sha}">{disp}'
        f'<span class="prov-dot">●</span></a>'
    )


def aspect_value(aspect: str, col: str, analysis: str = "A_primary", segment: str = "pooled"):
    def g(d: pd.DataFrame):
        r = d[(d["analysis"] == analysis) & (d["segment"] == segment) & (d["aspect"] == aspect)]
        if r.empty:
            raise KeyError(f"missing aspect row: {analysis}/{segment}/{aspect}")
        return r[col].iloc[0]
    return g


def taxonomy_value(aspect: str, col: str):
    def g(d: pd.DataFrame):
        r = d[d["aspect"] == aspect]
        if r.empty:
            raise KeyError(f"missing taxonomy row: {aspect}")
        return r[col].iloc[0]
    return g


def priority_value(rank: int, col: str):
    def g(d: pd.DataFrame):
        r = d[d["rank"] == rank]
        if len(r) != 1:
            raise KeyError(f"expected one priority rank {rank}; found {len(r)}")
        if col not in r.columns:
            raise KeyError(f"missing priority column: {col}")
        return r[col].iloc[0]
    return g


def poi_ranked(kind: str, index: int, col: str):
    def g(d: pd.DataFrame):
        if kind == "fix":
            work = d[d["is_fix_it"].astype(bool)].sort_values("fix_it_score", ascending=False)
        elif kind == "promote_fukui":
            work = d[(d["is_promote_it"].astype(bool)) & (d["is_fukui"].astype(bool))].sort_values("promote_it_score", ascending=False)
        elif kind == "crowding":
            work = d[d["is_crowding_hotspot"].astype(bool)].sort_values("waiting_crowding_prevalence", ascending=False)
        else:
            raise KeyError(f"unknown POI rank kind: {kind}")
        if len(work) <= index:
            raise KeyError(f"missing {kind} rank {index}")
        return work.iloc[index][col]
    return g


def poi_count(col: str, fukui: bool | None = None):
    def g(d: pd.DataFrame):
        work = d
        if fukui is not None:
            work = work[work["is_fukui"].astype(bool) == fukui]
        return int(work[col].astype(bool).sum())
    return g


def pct(x: object) -> str:
    return f"{float(x) * 100:.1f}%"


def yes_no(x: object) -> str:
    return "yes" if str(x).strip().lower() in {"true", "1", "yes"} else "no"


def source_values() -> dict[str, str]:
    """Collect all live values used by the cards."""
    values = {
        "opening_type": stat("tax", taxonomy_value("opening_hours_availability", "nudge_type"), "{}", field="opening_hours_availability nudge_type"),
        "opening_mechanism": stat("tax", taxonomy_value("opening_hours_availability", "mechanism"), "{}", field="opening_hours_availability mechanism"),
        "opening_prev": stat("aspect", aspect_value("opening_hours_availability", "prevalence"), pct, field="opening_hours_availability prevalence"),
        "opening_or": stat("aspect", aspect_value("opening_hours_availability", "odds_ratio"), "{:.2f}", field="opening_hours_availability Firth OR"),
        "opening_fdr": stat("aspect", aspect_value("opening_hours_availability", "p_value_bh_fdr"), pfmt, field="opening_hours_availability BH-FDR p"),
        "time_type": stat("tax", taxonomy_value("itinerary_fit_time_cost", "nudge_type"), "{}", field="itinerary_fit_time_cost nudge_type"),
        "time_mechanism": stat("tax", taxonomy_value("itinerary_fit_time_cost", "mechanism"), "{}", field="itinerary_fit_time_cost mechanism"),
        "time_prev": stat("aspect", aspect_value("itinerary_fit_time_cost", "prevalence"), pct, field="itinerary_fit_time_cost prevalence"),
        "time_or": stat("aspect", aspect_value("itinerary_fit_time_cost", "odds_ratio"), "{:.2f}", field="itinerary_fit_time_cost Firth OR"),
        "time_fdr": stat("aspect", aspect_value("itinerary_fit_time_cost", "p_value_bh_fdr"), pfmt, field="itinerary_fit_time_cost BH-FDR p"),
        "fix_count": stat("poi", poi_count("is_fix_it"), "{:,.0f}", field="count is_fix_it"),
        "fix1_name": stat("poi", poi_ranked("fix", 0, "poi_name"), "{}", field="top fix-it poi_name"),
        "fix1_n": stat("poi", poi_ranked("fix", 0, "n_reviews"), "{:,.0f}", field="top fix-it n_reviews"),
        "fix1_codes": stat("poi", poi_ranked("fix", 0, "dominant_nudgeable_friction_codes"), "{}", field="top fix-it nudgeable friction codes"),
        "fix2_name": stat("poi", poi_ranked("fix", 1, "poi_name"), "{}", field="second fix-it poi_name"),
        "fix2_n": stat("poi", poi_ranked("fix", 1, "n_reviews"), "{:,.0f}", field="second fix-it n_reviews"),
        "fix2_codes": stat("poi", poi_ranked("fix", 1, "dominant_nudgeable_friction_codes"), "{}", field="second fix-it nudgeable friction codes"),
        "fix3_name": stat("poi", poi_ranked("fix", 2, "poi_name"), "{}", field="third fix-it poi_name"),
        "fix3_n": stat("poi", poi_ranked("fix", 2, "n_reviews"), "{:,.0f}", field="third fix-it n_reviews"),
        "fix3_codes": stat("poi", poi_ranked("fix", 2, "dominant_nudgeable_friction_codes"), "{}", field="third fix-it nudgeable friction codes"),
        "promote_type": stat("tax", taxonomy_value("scenic_value", "nudge_type"), "{}", field="scenic_value nudge_type"),
        "promote_mechanism": stat("tax", taxonomy_value("scenic_value", "mechanism"), "{}", field="scenic_value mechanism"),
        "promote_fukui_count": stat("poi", poi_count("is_promote_it", True), "{:,.0f}", field="count is_promote_it and is_fukui"),
        "promote1_name": stat("poi", poi_ranked("promote_fukui", 0, "poi_name"), "{}", field="top Fukui promote-it poi_name"),
        "promote1_share": stat("poi", poi_ranked("promote_fukui", 0, "positive_share"), pct, field="top Fukui promote-it positive_share"),
        "promote1_low": stat("poi", poi_ranked("promote_fukui", 0, "positive_share_ci_low"), pct, field="top Fukui promote-it positive_share_ci_low"),
        "promote1_high": stat("poi", poi_ranked("promote_fukui", 0, "positive_share_ci_high"), pct, field="top Fukui promote-it positive_share_ci_high"),
        "promote1_conf": stat("poi", poi_ranked("promote_fukui", 0, "promote_confidence"), "{}", field="top Fukui promote-it confidence"),
        "promote2_name": stat("poi", poi_ranked("promote_fukui", 1, "poi_name"), "{}", field="second Fukui promote-it poi_name"),
        "promote2_share": stat("poi", poi_ranked("promote_fukui", 1, "positive_share"), pct, field="second Fukui promote-it positive_share"),
        "promote2_low": stat("poi", poi_ranked("promote_fukui", 1, "positive_share_ci_low"), pct, field="second Fukui promote-it positive_share_ci_low"),
        "promote2_high": stat("poi", poi_ranked("promote_fukui", 1, "positive_share_ci_high"), pct, field="second Fukui promote-it positive_share_ci_high"),
        "promote2_conf": stat("poi", poi_ranked("promote_fukui", 1, "promote_confidence"), "{}", field="second Fukui promote-it confidence"),
        "crowd1_name": stat("poi", poi_ranked("crowding", 0, "poi_name"), "{}", field="top crowding hotspot poi_name"),
        "crowd1_prev": stat("poi", poi_ranked("crowding", 0, "waiting_crowding_prevalence"), pct, field="top crowding hotspot waiting_crowding_prevalence"),
        "crowd_base": stat("poi", poi_ranked("crowding", 0, "waiting_crowding_global_base_prevalence"), pct, field="waiting_crowding global base prevalence"),
        "crowd2_name": stat("poi", poi_ranked("crowding", 1, "poi_name"), "{}", field="second crowding hotspot poi_name"),
        "crowd2_prev": stat("poi", poi_ranked("crowding", 1, "waiting_crowding_prevalence"), pct, field="second crowding hotspot waiting_crowding_prevalence"),
    }
    for aspect in ["english_information_gap", "wayfinding_signage", "transport_access"]:
        key = aspect.replace("_", "")
        values[f"{key}_type"] = stat("tax", taxonomy_value(aspect, "nudge_type"), "{}", field=f"{aspect} nudge_type")
        values[f"{key}_mechanism"] = stat("tax", taxonomy_value(aspect, "mechanism"), "{}", field=f"{aspect} mechanism")
        values[f"{key}_prev"] = stat("aspect", aspect_value(aspect, "prevalence", "C_inbound", "inbound_pooled"), pct, field=f"C_inbound {aspect} prevalence")
        values[f"{key}_under"] = stat("aspect", aspect_value(aspect, "underpowered", "C_inbound", "inbound_pooled"), yes_no, field=f"C_inbound {aspect} underpowered")
    return values


def ranked_solution_values() -> list[dict[str, str]]:
    """Resolve register cards from the same ranked output used by the deck."""
    rows: list[dict[str, str]] = []
    fields = [
        "rank",
        "solution_id",
        "solution_label_en",
        "impact_tier",
        "ease_tier",
        "evidence_summary_en",
        "experiment_hypothesis_en",
        "intervention_en",
        "randomization_unit",
        "primary_outcomes",
        "secondary_outcomes",
        "evidence_caveat",
    ]
    for rank in (1, 2, 3):
        row: dict[str, str] = {}
        for field in fields:
            row[field] = stat(
                "priority",
                priority_value(rank, field),
                "{:.0f}" if field == "rank" else "{}",
                field=f"priority rank {rank} {field}",
            )
        rows.append(row)
    return rows


def card(title: str, body: str) -> str:
    return f"<div class='hyp'><div class='hyp-head'><span class='hyp-tag'>Experiment</span><h3>{title}</h3></div>{body}</div>"


def build_html() -> str:
    v = source_values()
    ranked = ranked_solution_values()
    css = dashboard_css()
    H: list[str] = []
    H.append("<!doctype html><html lang='en'><head><meta charset='utf-8'>")
    H.append("<meta name='viewport' content='width=device-width,initial-scale=1'>")
    H.append("<title>Next-Semester Nudge Experiment Register</title>")
    H.append(f"<style>{css}</style>")
    # The dashboard's .stat provenance links are nowrap (fine for short numbers),
    # but in the register a provenance-wrapped value can be a full mechanism
    # sentence, which then overflows the card. Inside cards, let those links wrap.
    H.append(
        "<style>.hyp .stat{white-space:normal;overflow-wrap:break-word}"
        ".hyp p{overflow-wrap:break-word}</style></head><body>"
    )
    H.append("<div class='wrap'><header class='masthead'>")
    H.append("<p><a class='jump-link' href='../PBL-Dashboard.html'>← Back to dashboard</a></p>")
    H.append("<p class='eyebrow'>Hokuriku Nudge Opportunity Register</p>")
    H.append("<h1>Next-semester experiments for high-impact nudge opportunities</h1>")
    H.append("<p class='standfirst'>Concrete exploratory tests derived from aggregate aspect and POI opportunity maps. These cards rank what to test next; they do not claim effectiveness.</p>")
    H.append("</header></div><main class='wrap'>")

    H.append("<section><span class='sec-num'>REGISTER — EXPERIMENT CARDS</span>")
    H.append("<h2 class='sec'>What to test next semester</h2>")
    H.append("<p class='lead'>Every statistic, POI name, nudge type, and mechanism below is loaded from aggregate CSV outputs at build time and wrapped in a provenance link.</p>")

    for row in ranked:
        H.append(card(
            f"Priority {row['rank']}: {row['solution_label_en']}",
            f"<p><b>Solution ID.</b> {row['solution_id']}</p>"
            f"<p><b>Ranking.</b> {row['impact_tier']} impact; implementation ease {row['ease_tier']}.</p>"
            f"<p><b>Cross-language evidence.</b> {row['evidence_summary_en']}</p>"
            f"<p><b>Hypothesis.</b> {row['experiment_hypothesis_en']}</p>"
            f"<p><b>Intervention.</b> {row['intervention_en']}</p>"
            f"<p><b>Randomization unit.</b> {row['randomization_unit']}</p>"
            f"<p><b>Primary outcomes.</b> {row['primary_outcomes']}</p>"
            f"<p><b>Secondary outcomes.</b> {row['secondary_outcomes']}</p>"
            f"<p><b>Evidence boundary.</b> {row['evidence_caveat']}</p>"
        ))

    H.append("<h2 class='sec'>Supporting analysis cards</h2>")
    H.append("<p class='lead'>These preserve the aspect-level and POI-level rationale behind the ranked solution families.</p>")

    H.append(card(
        "Fix-it information levers",
        f"<p><b>Opportunity.</b> Opening-hours availability and itinerary fit / time cost are the strongest nudge-able friction signals.</p>"
        f"<p><b>Nudge type + mechanism.</b> {v['opening_type']}: {v['opening_mechanism']} Also {v['time_type']}: {v['time_mechanism']}</p>"
        f"<p><b>Evidence so far.</b> Opening-hours availability prevalence {v['opening_prev']}, Firth OR {v['opening_or']}, {v['opening_fdr']}. "
        f"Itinerary fit / time cost prevalence {v['time_prev']}, Firth OR {v['time_or']}, {v['time_fdr']}.</p>"
        "<p><b>Proposed experiment.</b> Intervention: clearer hours / closure information plus itinerary-fit prompts before arrival. Unit: POI or visitor session. Primary outcome: low-rating share and complaint-code prevalence. Rough design: stepped rollout or matched POI/session comparison.</p>"
        "<p><b>Collect next.</b> Pre/post visitor-session exposure, review rating, aspect-code evidence, and POI/date controls.</p>"
        "<p><b>Why effectiveness is not quantified yet.</b> Current evidence is observational association; assignment and exposure must be measured next semester.</p>"
    ))

    H.append(card(
        "POI-specific fix-it trials",
        f"<p><b>Opportunity.</b> {v['fix_count']} fix-it POIs have high volume and elevated nudge-able friction.</p>"
        f"<p><b>Evidence so far.</b> {v['fix1_name']} has {v['fix1_n']} reviews and elevated codes {v['fix1_codes']}; "
        f"{v['fix2_name']} has {v['fix2_n']} reviews and elevated codes {v['fix2_codes']}; "
        f"{v['fix3_name']} has {v['fix3_n']} reviews and elevated codes {v['fix3_codes']}.</p>"
        "<p><b>Proposed experiment.</b> Intervention: targeted signage, translation, booking QR, or hours/route prompt matched to the elevated friction codes. Unit: venue entrance, booking page, or visitor session. Primary outcome: friction-code prevalence and low-rating share.</p>"
        "<p><b>Collect next.</b> Site-level exposure logs, intervention dates, QR scans, visitor counts, review ratings, and reviewed aspect tags.</p>"
        "<p><b>Why effectiveness is not quantified yet.</b> Current POI ranking identifies where friction concentrates; it does not isolate an intervention effect.</p>"
    ))

    H.append(card(
        "Promote-it demand redistribution",
        f"<p><b>Opportunity.</b> {v['promote_fukui_count']} Fukui promote-it candidates can be paired against crowding hotspots.</p>"
        f"<p><b>Nudge type + mechanism.</b> {v['promote_type']}: {v['promote_mechanism']}</p>"
        f"<p><b>Evidence so far.</b> {v['promote1_name']} positive share {v['promote1_share']} "
        f"(CI {v['promote1_low']}–{v['promote1_high']}), confidence {v['promote1_conf']}; "
        f"{v['promote2_name']} positive share {v['promote2_share']} "
        f"(CI {v['promote2_low']}–{v['promote2_high']}), confidence {v['promote2_conf']}. "
        f"Redirect-from hotspots include {v['crowd1_name']} with waiting/crowding {v['crowd1_prev']} versus base {v['crowd_base']}, "
        f"and {v['crowd2_name']} with {v['crowd2_prev']}.</p>"
        "<p><b>Proposed experiment.</b> Intervention: itinerary card, map placement, hotel/front-desk prompt, or transit/wayfinding message that steers visitors from crowded hotspots toward high-satisfaction under-visited POIs. Unit: itinerary channel or visitor session. Primary outcome: visit-share redistribution plus satisfaction / complaint prevalence.</p>"
        "<p><b>Collect next.</b> Channel exposure, click/scan or itinerary choice, POI visit counts, short satisfaction intercepts, and follow-up review aspect tags.</p>"
        "<p><b>Why effectiveness is not quantified yet.</b> Current evidence ranks candidate redirect-to and redirect-from POIs; randomized or staggered exposure is needed to estimate behaviour change.</p>"
    ))

    H.append(card(
        "Underpowered but promising inbound information gaps",
        f"<p><b>Opportunity.</b> English-information gap, wayfinding signage, and transport access are rare but stakeholder-relevant inbound levers.</p>"
        f"<p><b>Nudge type + mechanism.</b> {v['englishinformationgap_type']}: {v['englishinformationgap_mechanism']} "
        f"{v['wayfindingsignage_type']}: {v['wayfindingsignage_mechanism']} "
        f"{v['transportaccess_type']}: {v['transportaccess_mechanism']}</p>"
        f"<p><b>Evidence so far.</b> Inbound English-information gap prevalence {v['englishinformationgap_prev']}, underpowered {v['englishinformationgap_under']}; "
        f"wayfinding signage prevalence {v['wayfindingsignage_prev']}, underpowered {v['wayfindingsignage_under']}; "
        f"transport access prevalence {v['transportaccess_prev']}, underpowered {v['transportaccess_under']}.</p>"
        "<p><b>Proposed experiment.</b> Intervention: targeted oversampling and hand-labelled collection around signage, English information, and access prompts before choosing a full trial. Unit: sampled visitor session or reviewed POI-language stratum. Primary outcome: powered aspect prevalence and low-rating association.</p>"
        "<p><b>Collect next.</b> More inbound-language reviews, intercept notes, QR exposure counts, and human-reviewed aspect labels for the rare information codes.</p>"
        "<p><b>Why effectiveness is not quantified yet.</b> The current inbound slice is too sparse for confident effect ranking; collection comes before effectiveness testing.</p>"
    ))
    H.append("</section>")

    H.append("<section id='prov'><span class='sec-num'>PROVENANCE</span>")
    H.append("<h2 class='sec'>Every value, traced to source</h2>")
    H.append("<table class='prov-table'><thead><tr><th>#</th><th>Value</th><th>Field</th><th>Source file</th><th>SHA256</th></tr></thead><tbody>")
    seen = set()
    i = 0
    for r in REFS:
        key = (r["value"], r["field"], r["source"])
        if key in seen:
            continue
        seen.add(key)
        i += 1
        H.append(
            f"<tr><td class='num'>{i}</td><td class='num'>{html.escape(str(r['value']))}</td>"
            f"<td>{html.escape(str(r['field']))}</td><td><a href='{r['source']}' target='_blank'>{r['source']}</a></td>"
            f"<td>{str(r['sha256'])[:16]}…</td></tr>"
        )
    H.append("</tbody></table></section></main>")
    H.append("<footer><div class='wrap'>Generated by <code>scripts/build_nudge_experiment_register.py</code> from aggregate nudge outputs. Exploratory only; no causal or effectiveness claims.</div></footer>")
    H.append("</body></html>")
    return "\n".join(H)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUT_HTML)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    load()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(build_html(), encoding="utf-8")
    print(f"wrote {args.output} ({args.output.stat().st_size:,} bytes); {len(REFS)} provenance-locked values")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
