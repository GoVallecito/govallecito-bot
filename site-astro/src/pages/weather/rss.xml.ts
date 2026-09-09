import { getFeed, describe, BYLINE } from "../../lib/wx";

// A feed is cheap and it is how other local pages and aggregators pick this up
// without anyone having to ask.
export async function GET({ site }: { site?: URL }) {
  const base = site ?? new URL("https://govallecito.com");
  const feed = await getFeed();
  const esc = (s: string) =>
    s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const items = feed.posts
    .slice(0, 30)
    .map(
      (p) => `    <item>
      <title>${esc(p.title)}</title>
      <link>${new URL(`/weather/${p.slug}/`, base).href}</link>
      <guid>${new URL(`/weather/${p.slug}/`, base).href}</guid>
      <pubDate>${new Date(p.date || p.forDate).toUTCString()}</pubDate>
      <description>${esc(describe(p))}</description>
    </item>`,
    )
    .join("\n");
  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>${esc(BYLINE)}</title>
    <link>${new URL("/weather/", base).href}</link>
    <description>Forecast by elevation for Vallecito Lake, Bayfield and Durango.</description>
    <language>en-us</language>
${items}
  </channel>
</rss>`;
  return new Response(xml, {
    headers: { "Content-Type": "application/xml; charset=utf-8" },
  });
}
