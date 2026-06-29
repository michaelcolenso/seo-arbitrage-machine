import type { APIRoute } from 'astro';
import meta from '../data/meta.json';

// The calculator is a single parametric page; the sitemap covers just the root.
export const GET: APIRoute = () => {
  const base: string = (meta as Record<string, string>).canonical_base ?? '';
  const body =
    '<?xml version="1.0" encoding="UTF-8"?>\n' +
    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' +
    `  <url><loc>${base}/</loc></url>\n` +
    '</urlset>\n';
  return new Response(body, { headers: { 'Content-Type': 'application/xml' } });
};
