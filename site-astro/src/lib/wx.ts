/**
 * The forecast feed, and the one renderer that turns a post into HTML.
 *
 * ONE renderer, used by both the Astro build and the /weather Pages Function.
 * They render the same post in two different places at two different times,
 * and if each had its own template they would drift, which a reader would see
 * as the page changing shape when it went live.
 *
 * Reading the feed NEVER throws. govallecito.com is a business and the weather
 * section is a feature of it; a bad fetch must produce an empty page, not a
 * failed build and not a 500.
 */

export const FEED_URL =
  "https://raw.githubusercontent.com/GoVallecito/govallecito-bot/main/site/weather/feed.json";
export const BYLINE = "Up the Pine Weather";

export interface Band { elevationFt?: number | null; precipType?: string | null; label?: string | null; }
export interface Post {
  slug: string; title: string; date: string; forDate: string; postType: string; body: string;
  snowLineFt?: number | null; snowLineTrend?: string | null;
  bands?: Record<string, Band>; alerts?: string[]; sources?: string[];
}
export interface Feed { generatedAt: string; count: number; truncated: boolean; posts: Post[]; }

export function escapeHtml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
          .replace(/"/g, "&quot;");
}

export function bodyToHtml(body: string): string {
  return body.split(/\n\s*\n/).map((p) => p.trim()).filter(Boolean)
    .map((p) => {
      const safe = escapeHtml(p).replace(/(https?:\/\/[^\s<]+[^\s<.,)])/g,
        '<a href="$1" rel="noopener">$1</a>');
      return `<p>${safe.replace(/\n/g, "<br />")}</p>`;
    }).join("\n");
}

export function fmtDate(iso: string): string {
  if (!iso) return "";
  const dateOnly = /^\d{4}-\d{2}-\d{2}$/.test(iso.trim());
  const d = new Date(dateOnly ? `${iso.trim()}T12:00:00Z` : iso);
  if (Number.isNaN(d.valueOf())) return iso;
  return d.toLocaleDateString("en-US", {
    weekday: "long", month: "long", day: "numeric", year: "numeric",
    timeZone: dateOnly ? "UTC" : "America/Denver",
  });
}

export function fmtTime(iso: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.valueOf())) return "";
  return d.toLocaleTimeString("en-US", {
    hour: "numeric", minute: "2-digit", timeZone: "America/Denver" });
}

export function describe(post: Post): string {
  if (post.snowLineFt) {
    return `Snow line near ${post.snowLineFt.toLocaleString()} ft. Forecast by elevation for Vallecito Lake, Bayfield and Durango, ${fmtDate(post.forDate)}.`;
  }
  return `Forecast by elevation for Vallecito Lake, Bayfield and Durango, ${fmtDate(post.forDate)}.`;
}

/** The post as HTML. Shared by the Astro build and the Pages Function so the
 *  live version and the built version can never render differently. */
export function postToHtml(post: Post, heading: "h1" | "h2" = "h1"): string {
  const bands = Object.values(post.bands ?? {}).filter((b) => b?.elevationFt);
  const head = heading === "h1"
    ? `<h1>${escapeHtml(post.title)}</h1>`
    : `<h2><a href="/weather/${post.slug}/">${escapeHtml(post.title)}</a></h2>`;
  return [
    `<article class="wx-post">`,
    head,
    `<p class="wx-meta"><span>${escapeHtml(fmtDate(post.forDate))}</span>` +
      (post.date ? `<span> &middot; posted ${escapeHtml(fmtTime(post.date))} MT</span>` : "") +
      `<span> &middot; ${escapeHtml(BYLINE)}</span></p>`,
    (post.alerts?.length
      ? `<p class="wx-alert">Active National Weather Service alert: ${escapeHtml(post.alerts.join(", "))}. <a href="https://www.weather.gov/gjt/" rel="noopener">Official product</a></p>`
      : ""),
    (post.snowLineFt
      ? `<p class="wx-snowline"><strong>Snow line about ${post.snowLineFt.toLocaleString()} ft</strong>${post.snowLineTrend ? `<span>, ${escapeHtml(post.snowLineTrend)}</span>` : ""}</p>`
      : ""),
    `<div class="wx-body">${bodyToHtml(post.body)}</div>`,
    (bands.length
      ? `<table class="wx-bands"><caption>By elevation</caption>` +
        `<thead><tr><th>Where</th><th>Elevation</th><th>Falling as</th></tr></thead><tbody>` +
        bands.map((b) => `<tr><td>${escapeHtml(b.label ?? "")}</td><td>${b.elevationFt?.toLocaleString()} ft</td><td>${escapeHtml(b.precipType ?? "dry")}</td></tr>`).join("") +
        `</tbody></table>`
      : ""),
    (post.sources?.length
      ? `<p class="wx-sources">Sources: ${escapeHtml(post.sources.join(", "))}.</p>`
      : ""),
    `</article>`,
  ].filter(Boolean).join("\n");
}


export const VERIFY_URL =
  "https://raw.githubusercontent.com/GoVallecito/govallecito-bot/main/state/forecast_log.json";

const EMPTY: Feed = { generatedAt: "", count: 0, truncated: false, posts: [] };

/** Fetch the feed at build time. Never throws. */
export async function getFeed(): Promise<Feed> {
  try {
    const res = await fetch(FEED_URL, {
      headers: { Accept: "application/json" },
      signal: AbortSignal.timeout(15000),
    });
    if (!res.ok) {
      console.warn(`[wx] feed returned ${res.status}; weather pages will be empty`);
      return EMPTY;
    }
    const data = (await res.json()) as Feed;
    if (!data || !Array.isArray(data.posts)) return EMPTY;
    return data;
  } catch (err) {
    console.warn(`[wx] could not read the forecast feed: ${err}`);
    return EMPTY;
  }
}

/** The verification record, for the track-record page. Never throws. */
export async function getVerifications(): Promise<any[]> {
  try {
    const res = await fetch(VERIFY_URL, { signal: AbortSignal.timeout(15000) });
    if (!res.ok) return [];
    const data = await res.json();
    return Array.isArray(data?.forecasts) ? data.forecasts : [];
  } catch {
    return [];
  }
}
