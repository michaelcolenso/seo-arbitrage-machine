import { defineConfig } from 'astro/config';
import tailwind from '@astrojs/tailwind';

// Fixed Invariant: pristine static directory theme. The compiler only ever
// rewrites src/data/*.json — never this configuration or the page templates.
export default defineConfig({
  output: 'static',
  integrations: [tailwind()],
  // Emit flat files (austin/chemical.html) so routes serve without a
  // trailing-slash 308 redirect — keeps the served URL identical to the
  // canonical tag and sitemap entry (both non-slash).
  build: { format: 'file' },
  trailingSlash: 'never',
});
