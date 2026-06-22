# Architecture Review Resume Notes - 2026-06-22

Source report:

- `/home/andrewgreen/.codex/attachments/f3b1abb0-46d7-476a-b98d-2fed658f32e6/architecture-review-20260619-hokuriku.html`

Explorers used:

- Provenance: `019eed83-7692-7683-b781-c4d41a0de10f`
- Scope: `019eed83-8492-7901-817e-0701cc694b20`
- Codebook: `019eed83-9975-7d03-888a-21ffcf716ce3`
- Chinese ingress and stats: `019eed83-af01-7002-9747-83159e37ac5e`

Verdict matrix:

| Candidate | Current status | Evidence | Main gap | Cheap next step |
| --- | --- | --- | --- | --- |
| Deepen provenance manifest Module | Partial, broadly adopted | `src/provenance.py`; used by sentiment, Chinese social, cross-language, presentation, sync scripts | Loose dict schema; no dedicated provenance tests; callers still remember forbidden-column checks | Add `tests/test_provenance.py`; optional manifest validator |
| Centralize Fukui-first scope Module | Partial, close | `src/scope.py`; used by sentiment and cross-language; `tests/test_scope.py` | Aggregate prefecture filters still inline; Chinese review comparison still raw `city` join | Add aggregate scope helper; decide city-level legacy behavior |
| Deepen reviewed codebook promotion Module | Partial | `src/reviewed_codebook.py`; `scripts/import_reviewed_codebook_config.py`; Chinese reviewed path active | JP/EN manual decisions blank; no `config/reviewed_jp_en_codebook.yaml`; sentiment still library-only | Finish JP/EN manual review, run importer, then add evidence columns/disagreement rates |
| Split Chinese-language posts ingress Adapters | Partial | One normalizer handles XHS and Douyin with platform branches | `normalize_social_csv()` mixes registry, parser, mapper, date policy | Extract `normalize_xhs_source()` and `normalize_douyin_comment_source()` wrapper-preserving |
| Separate statistical test family Modules | Not applied | `build_tests()` contains all JP/EN test families | Mixed categorical, score, bootstrap, POI, rating logic in one function | Extract pure row builders; keep output schema/order |

Overall state:

- Architecture review was directionally acted on for provenance and scope.
- Academic guardrails improved: fail-loud scope, provenance manifests, aggregate-only output checks, Chinese reviewed evidence path.
- Big remaining architecture blocker is JP/EN reviewed codebook evidence. Until manual decisions are complete, repo cannot satisfy dual-path sentiment evidence goal for JP/EN.
- Most useful implementation order:
  1. Complete JP/EN manual review decisions outside code.
  2. Generate reviewed JP/EN runtime config.
  3. Add JP/EN keyword evidence columns and disagreement-rate outputs.
  4. Then refactor stats families and Chinese ingress adapters.
