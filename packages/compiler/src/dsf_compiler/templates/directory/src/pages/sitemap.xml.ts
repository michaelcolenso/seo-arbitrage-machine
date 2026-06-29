import type { APIRoute } from 'astro';
import meta from '../data/meta.json';
import routes from '../data/routes.json';

// Static endpoint: emits dist/sitemap.xml covering the index + every route page.
export const GET: APIRoute = () => {
  const base: string = (meta as Record<string, string>).canonical_base ?? '';
  const paths = ['/', ...((routes as { path: string }[]) ?? []).map((r) => r.path)];
  const urls = paths
    .map((p) => `  <url><loc>${base}${p}</loc></url>`)
    .join('\n');
  const body =
    '<?xml version="1.0" encoding="UTF-8"?>\n' +
    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' +
    urls +
    '\n</urlset>\n';
  return new Response(body, { headers: { 'Content-Type': 'application/xml' } });
};
