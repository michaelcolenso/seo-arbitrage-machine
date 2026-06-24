# DataSiteForge — Directory template (Fixed Invariant)

A pristine Astro + Tailwind + Alpine.js theme for searchable B2B data
directories. **Do not let the agent rewrite this template.** The DataSiteForge
compiler only ever overwrites the data-hydration layer:

- `src/data/rows.json` — the directory rows.
- `src/data/meta.json` — the strict metadata contract (title, columns, SEO
  routing, monetisation pattern, lead-gen flag).

`src/pages/index.astro` renders a Tailwind table and uses Alpine.js (loaded from
CDN, zero-bundle) for client-side search and column sorting, plus an optional
lead-generation form.

## Local development

```bash
npm install
npm run dev      # preview with the placeholder data in src/data/
npm run build    # static output in dist/
```
