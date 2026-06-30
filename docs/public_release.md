# Public Release and Data Availability

## Release rule

Commit material needed to inspect methods and aggregate claims, provided it
cannot reconstruct a source row or identify a reviewer/post author.

Public:

- source code, tests, dependency files, runtime configs
- human-reviewed keyword decisions without source excerpts
- aggregate processed tables, denominators, effect estimates, manifests
- statistical/publication figures and backing aggregate data
- methodological decisions, limitations, readiness reports

Private:

- raw or row-level post/review text
- titles/excerpts paired with dates, POIs, source IDs, record IDs, people, URLs
- screenshots, XML/manual captures, local caches
- slide decks, speaker notes, handouts, dashboards, delivery-only builders
- agent scratchpads, handoffs, machine-specific state

## Reproducibility levels

1. **Public inspection:** committed methods, codebooks, aggregate tables,
   manifests, and figures can be reviewed without private data.
2. **Aggregate regeneration:** figure/test builders can rerun when their
   disclosure-safe aggregate prerequisites are present.
3. **Full rebuild:** requires separately obtained local source repositories and
   row-level data. Their paths are supplied through environment variables.

Missing restricted input must stop a build. Do not synthesize fallback rows.

## Pre-publication check

Before pushing:

```bash
git ls-files
.venv/bin/python3 scripts/check_public_release.py
.venv/bin/python3 -m pytest
```

Inspect every newly tracked CSV/JSON/workbook for text excerpts, people,
URLs, exact source dates, source/record IDs, and cells small enough to disclose
a row. Inspect manifests for personal absolute paths. Keep only repo-relative
paths or documented environment-variable inputs.

Git deletion does not remove content from earlier commits. If forbidden
row-level material reached a remote, rewrite remote history before treating the
repository as safely public; coordinate that disruptive operation separately.
