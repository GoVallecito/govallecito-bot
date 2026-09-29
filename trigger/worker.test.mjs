import W, { decide, hasPostFor, denverParts } from "./morning-trigger.js";
import { readFileSync } from "node:fs";
let fail = 0;
const t = (l, g, w) => { const ok = g === w; if (!ok) fail++; console.log(`${ok ? "ok  " : "FAIL"} ${l}: got ${JSON.stringify(g)}${ok ? "" : ` want ${JSON.stringify(w)}`}`); };
const at = s => new Date(s);

console.log("-- scheduling, MDT --");
t("11Z -> local 05 attempt", decide(at("2026-09-30T11:00:00Z")).action, "attempt");
t("12Z -> local 06 attempt", decide(at("2026-09-30T12:00:00Z")).action, "attempt");
t("13Z -> local 07 attempt", decide(at("2026-09-30T13:00:00Z")).action, "attempt");
t("14Z -> local 08 attempt", decide(at("2026-09-30T14:00:00Z")).action, "attempt");
t("15Z -> local 09 watchdog", decide(at("2026-09-30T15:00:00Z")).action, "watchdog");
t("16Z -> local 10 skip", decide(at("2026-09-30T16:00:00Z")).action, "skip");
t("10Z -> local 04 skip", decide(at("2026-09-30T10:00:00Z")).action, "skip");

console.log("-- scheduling, MST --");
t("11Z -> local 04 skip", decide(at("2026-11-10T11:00:00Z")).action, "skip");
t("12Z -> local 05 attempt", decide(at("2026-11-10T12:00:00Z")).action, "attempt");
t("15Z -> local 08 attempt", decide(at("2026-11-10T15:00:00Z")).action, "attempt");
t("16Z -> local 09 watchdog", decide(at("2026-11-10T16:00:00Z")).action, "watchdog");

console.log("-- DST transition days --");
t("2026-11-01 12Z is local 05", denverParts(at("2026-11-01T12:00:00Z")).hour, 5);
t("2027-03-14 11Z is local 05", denverParts(at("2027-03-14T11:00:00Z")).hour, 5);

console.log("-- invariants --");
for (const [label, day] of [["MDT", "2026-09-30"], ["MST", "2026-11-10"]]) {
  const hrs = [11, 12, 13, 14, 15, 16];
  const acts = hrs.map(h => decide(at(`${day}T${String(h).padStart(2, "0")}:00:00Z`)));
  t(`${label} attempts/day`, acts.filter(a => a.action === "attempt").length, 4);
  t(`${label} watchdogs/day`, acts.filter(a => a.action === "watchdog").length, 1);
  t(`${label} never attempts at/after local noon`,
    acts.some(a => a.action === "attempt" && a.hour >= 12), false);
  t(`${label} never attempts before local 05`,
    acts.some(a => a.action === "attempt" && a.hour < 5), false);
}

console.log("-- feed check, against the real live feed --");
const feed = JSON.parse(readFileSync(process.argv[2], "utf8"));
t("finds the real 09-27 post", hasPostFor(feed, "2026-09-27"), true);
t("no post for the silent 09-28", hasPostFor(feed, "2026-09-28"), false);
t("no post for the silent 09-29", hasPostFor(feed, "2026-09-29"), false);
t("empty object is safe", hasPostFor({}, "2026-09-29"), false);
t("null is safe", hasPostFor(null, "2026-09-29"), false);
t("an evening post does not satisfy the morning",
  hasPostFor({ posts: [{ forDate: "2026-09-30", postType: "evening" }] }, "2026-09-30"), false);

console.log("-- module shape --");
t("exports scheduled()", typeof W.scheduled, "function");
t("exports fetch()", typeof W.fetch, "function");

console.log(fail ? `\n${fail} FAILED` : "\nALL PASS");
process.exit(fail ? 1 : 0);
