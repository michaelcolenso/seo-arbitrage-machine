# datasiteforge-compiler

Phase 4 — the Astro compilation & component-assembly engine for **DataSiteForge**.

Turns an `APPROVED` `Evaluation` into a hydrated Astro site by writing the
**fluid data layer** into a copy of the chosen **fixed-invariant** template:

- `dsf_compiler.hydration` — pure payload builders (`build_rows_payload`,
  `build_meta_payload`) that produce the strict JSON contract the templates consume.
- `dsf_compiler.builder` — `SiteCompiler`: load evaluation → read dataset rows via
  the DuckDB broker → copy `templates/<type>` → overwrite `src/data/*.json` →
  record a `SiteGeneration` ledger row. Failures become structured reflections.
- `dsf_compiler.cli` — the `compile` command group (`seo-platform compile run / list`).

The compiler never rewrites template markup, styling, or config — only
`src/data/rows.json` and `src/data/meta.json`. The actual `astro build` is left to
Phase 5 / CI by default; pass `--build` to invoke it defensively.
