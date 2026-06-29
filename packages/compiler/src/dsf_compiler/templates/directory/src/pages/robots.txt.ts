import type { APIRoute } from 'astro';
import meta from '../data/meta.json';

// Static endpoint: emits dist/robots.txt pointing crawlers at the sitemap.
export const GET: APIRoute = () => {
  const base: string = (meta as Record<string, string>).canonical_base ?? '';
  const sitemap = base ? `${base}/sitemap.xml` : '/sitemap.xml';
  const body = `User-agent: *\nAllow: /\nSitemap: ${sitemap}\n`;
  return new Response(body, { headers: { 'Content-Type': 'text/plain' } });
};
