/**
 * Reads the forecast feed at BUILD TIME.
 *
 * The forecaster lives in a different repository from this site. Rather than
 * give it a token to write here, it publishes into its own public repo and
 * this fetches the result. No credential is involved anywhere in the path.
 *
 * ONE request per build, not one per post. The feed carries the full body of
 * every recent forecast, so a build with a hundred posts still makes a single
 * call. Walking the GitHub contents API instead would mean one request per
 * post against a 60-per-hour unauthenticated limit shared by every build
 * runner on that IP address, which fails intermittently and only under load.
 *
 * A failure here must NEVER break the site build. govallecito.com is a
 * business; the weather section is a feature of it. If the feed cannot be
 * reached the weather pages render an honest empty state and every other page
 * builds exactly as before.
 */

export const FEED_URL =
  "https://raw.githubusercontent.com/GoVallecito/govallecito-bot/main/site/weather/feed.json";

export const VERIFY_URL =
  "https://raw.githubusercontent.com/GoVallecito/govallecito-bot/main/state/forecast_log.json";

export const BYLINE = "Up the Pine Weather";

export interface Band {
  elevationFt?: number | null;
  precipType?: string | null;
  label?: string | null;
}

export interface Post {
  slug: string;
  title: string;
  date: string;
  forDate: string;
  postType: string;
  body: string;
  snowLineFt?: number | null;
  snowLineTrend?: string | null;
  bands?: Record<string, Band>;
  basinPercentOfMedian?: number | null;
  alerts?: string[];
  sources?: string[];
}

export interface Feed {
  generatedAt: string;
  count: number;
  truncated: boolean;
  posts: Post[];
}

const EMPTY: Feed = { generatedAt: "", count: 0, truncated: false, posts: [] };

/** Fetch the feed, or an empty one. Never throws. */
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

/**
 * The post body is deliberately plain prose, so this is deliberately not a
 * markdown parser. Paragraphs and links are the only structure that exists.
 */
export function bodyToHtml(body: string): string {
  const escape = (s: string) =>
    s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  return body
    .split(/\n\s*\n/)
    .map((p) => p.trim())
    .filter(Boolean)
    .map((p) => {
      const safe = escape(p).replace(
        /(https?:\/\/[^\s<]+[^\s<.,)])/g,
        '<a href="$1" rel="noopener">$1</a>',
      );
      return `<p>${safe.replace(/\n/g, "<br />")}</p>`;
    })
    .join("\n");
}

export function fmtDate(iso: string): string {
  if (!iso) return "";
  // A bare YYYY-MM-DD parses as UTC midnight. Formatting that in Mountain Time
  // subtracts six hours and prints the PREVIOUS DAY: "2026-09-08" rendered as
  // Monday, September 7. This project has now shipped a UTC-versus-Mountain
  // bug three separate times, so the date-only case is handled explicitly.
  // Noon UTC lands on the same calendar day in every timezone that matters.
  const dateOnly = /^\d{4}-\d{2}-\d{2}$/.test(iso.trim());
  const d = new Date(dateOnly ? `${iso.trim()}T12:00:00Z` : iso);
  if (Number.isNaN(d.valueOf())) return iso;
  return d.toLocaleDateString("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
    timeZone: dateOnly ? "UTC" : "America/Denver",
  });
}

export function fmtTime(iso: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.valueOf())) return "";
  return d.toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
    timeZone: "America/Denver",
  });
}

/** Description used for <meta name="description"> and cards. */
export function describe(post: Post): string {
  if (post.snowLineFt) {
    return `Snow line near ${post.snowLineFt} ft. Forecast by elevation for Vallecito Lake, Bayfield and Durango, ${fmtDate(post.forDate)}.`;
  }
  return `Forecast by elevation for Vallecito Lake, Bayfield and Durango, ${fmtDate(post.forDate)}.`;
}
