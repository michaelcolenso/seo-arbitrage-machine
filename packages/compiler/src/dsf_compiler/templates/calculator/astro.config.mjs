import { defineConfig } from 'astro/config';
import tailwind from '@astrojs/tailwind';

// Fixed Invariant: pristine static calculator theme. The compiler only ever
// rewrites src/data/*.json — never this configuration or the page templates.
export default defineConfig({
  output: 'static',
  integrations: [tailwind()],
});
