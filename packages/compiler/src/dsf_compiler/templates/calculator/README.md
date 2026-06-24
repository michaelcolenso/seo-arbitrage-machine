# DataSiteForge — Calculator template (Fixed Invariant)

A pristine Astro + Tailwind + Alpine.js theme for parametric analysis / ROI
calculators. **Do not let the agent rewrite this template.** The DataSiteForge
compiler only ever overwrites the data-hydration layer:

- `src/data/meta.json` — the strict metadata contract, including a `calculator`
  block (`base`, `result_label`, and weighted `inputs`).
- `src/data/rows.json` — optional supporting rows (unused by the default view).

`src/pages/index.astro` renders Tailwind inputs and uses Alpine.js (loaded from
CDN, zero-bundle) to compute `base + Σ(input · weight)` live on the client.

## Local development

```bash
npm install
npm run dev      # preview with the placeholder config in src/data/
npm run build    # static output in dist/
```
