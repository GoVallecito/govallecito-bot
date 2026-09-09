/**
 * /weather -- served live, falling back to the built page.
 *
 * WHY THIS EXISTS. govallecito-web is a direct-upload Pages project, not a
 * Git-connected one, so Cloudflare offers no deploy hook to poke when a new
 * forecast lands. The site redeploys itself every few hours through its own
 * rebake, which is fine for the dated archive pages but not for the one page
 * whose entire value is being current at 6am.
 *
 * So this page does not wait for a rebuild. It asks for the statically built
 * page, fetches the forecast feed, and swaps the newest forecast into it.
 *
 * THE IMPORTANT PART is that it starts from `context.next()`, the real built
 * page, rather than rendering its own HTML. That means the site's own header,
 * nav, footer, styles and analytics come through untouched, and this file
 * never has to know anything about them. It replaces the contents of one
 * element and leaves every other byte alone.
 *
 * FAILURE IS A NO-OP. If the feed is slow, unreachable, malformed, or empty,
 * or if the built page has no marker in it, the built page is returned exactly
 * as it came. There is no path through this function that produces an error
 * page. The weather section must never be able to break govallecito.com.
 */

import { FEED_URL, describe, postToHtml, type Feed } from "../../src/lib/wx";

const MARKER_ID = "wx-live";

// Long enough that a burst of traffic is one origin fetch, short enough that a
// 5am forecast is visible within minutes. The feed only changes twice a day.
const FEED_TTL_SECONDS = 120;
const FEED_TIMEOUT_MS = 2500;

// The page itself may sit in Cloudflare's cache this long. stale-while-
// revalidate means a visitor never waits on a refetch.
const PAGE_CACHE = "public, max-age=60, s-maxage=120, stale-while-revalidate=600";

interface PagesContext {
  request: Request;
  next: () => Promise<Response>;
  waitUntil: (p: Promise<unknown>) => void;
}

async function loadFeed(): Promise<Feed | null> {
  const abort = new AbortController();
  const timer = setTimeout(() => abort.abort(), FEED_TIMEOUT_MS);
  try {
    const res = await fetch(FEED_URL, {
      signal: abort.signal,
      headers: { Accept: "application/json" },
      // Cached at the edge, so this is one origin fetch per couple of minutes
      // across every visitor, not one per request.
      cf: { cacheTtl: FEED_TTL_SECONDS, cacheEverything: true },
    } as RequestInit);
    if (!res.ok) return null;
    const feed = (await res.json()) as Feed;
    return feed && Array.isArray(feed.posts) && feed.posts.length ? feed : null;
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

// Handlers are plain objects with only an `element` method, deliberately.
//
// The first version used classes, and `class ReplaceText { constructor(private
// readonly text: string) }` failed at runtime with "Incorrect type for the
// 'text' field on 'ElementContentHandlers'". HTMLRewriter inspects the handler
// for `element`, `text`, `comments` and `end` properties, and the private field
// named `text` shadowed the callback it expects there with a string. Never give
// a handler a property with one of those four names.

function replaceInner(html: string, stamp: string) {
  return {
    element(el: Element) {
      el.setInnerContent(html, { html: true });
      el.setAttribute("data-wx-generated", stamp);
      el.setAttribute("data-wx-source", "live");
    },
  };
}

function replaceTextContent(value: string) {
  return {
    element(el: Element) {
      el.setInnerContent(value);
    },
  };
}

function setAttribute(name: string, value: string) {
  return {
    element(el: Element) {
      el.setAttribute(name, value);
    },
  };
}

export const onRequestGet = async (context: PagesContext): Promise<Response> => {
  const staticRes = await context.next();

  // Anything that is not a successful HTML document is passed straight
  // through: redirects, 404s, assets, HEAD-ish responses.
  const type = staticRes.headers.get("content-type") || "";
  if (!staticRes.ok || !type.includes("text/html")) return staticRes;

  // Buffered rather than streamed, deliberately. The page is a few kilobytes,
  // and reading it first is what lets this check for the marker BEFORE
  // rewriting anything. Streaming would mean the <title> is rewritten before
  // reaching the point in the document where we learn the marker is missing,
  // and the page would end up advertising a forecast it does not contain.
  const original = await staticRes.text();
  const passthrough = () =>
    new Response(original, {
      status: staticRes.status,
      statusText: staticRes.statusText,
      headers: staticRes.headers,
    });

  if (!original.includes(`id="${MARKER_ID}"`)) return passthrough();

  const feed = await loadFeed();
  if (!feed) return passthrough();

  const latest = feed.posts[0];
  if (!latest?.body) return passthrough();

  let html: string;
  try {
    html = postToHtml(latest, "h1");
  } catch {
    return passthrough();
  }

  const out = new HTMLRewriter()
    .on(`#${MARKER_ID}`, replaceInner(html, latest.date || latest.forDate))
    .on("title", replaceTextContent(`${latest.title} | Up the Pine Weather`))
    .on('meta[name="description"]', setAttribute("content", describe(latest)))
    .transform(new Response(original, { headers: staticRes.headers }));

  const headers = new Headers(out.headers);
  headers.set("cache-control", PAGE_CACHE);
  headers.set("x-wx-forecast-for", latest.forDate || "");
  return new Response(out.body, {
    status: out.status,
    statusText: out.statusText,
    headers,
  });
};
