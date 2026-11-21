# Review panel: 2026-11-21 school_call

Outcome: **NOT APPROVED**, not approved after 3 round(s): The fact checker correctly identified a forbidden snow line statement and a point-value snowfall figure where the brief shows 0.42 inches. The automated gate correctly flagged the bare percentage at 171%. The editor's model-disagreement construction concern is valid: both this draft and 2026-11-16 list models with their totals in parallel sentences. All five changes are required to satisfy the brief's rules and the automated gate.

## Round 1

### Draft

```
11/21/26 5:52am: Morning, its Saturday. The sky's already pale over the ridgeline and the air's got that sharp cold edge to it.

Dry day ahead but its not a clean one. The models are split on whether we get one last round of light snow this morning or whether the trough shuts off the moisture before it reaches us. The Euro's showing a trace to maybe a half inch for Vallecito and the Florida drainage before noon, the ICON's got a tenth or two of liquid converting to maybe an inch up high, and the GFS and GEM say we're done. Pop's sitting at 20-25% through late morning then dropping to nothing.

If we do catch something it'll be above 8,000 feet and done by early afternoon. Durango and Bayfield should stay dry. Vallecito and up the Florida could see light flurries through midday, with maybe an inch at the higher elevations if the Euro's right. Take that with a big grain of salt (the trough axis timing is the whole question and the models dont agree on it).

The passes should be fine for anyone heading north or east today. Coal Bank, Molas and Red Mountain might catch a dusting up top if the Euro verifies, Wolf Creek the same. Check cotrip.org for current conditions and chain law before you head out.

Wind picks up through midday, gusts 15-25mph across the Pine and the valley, then calms tonight. Highs low 40s in town, upper 30s at the lake. Clear and cold tonight, lows mid 20s in town, upper teens to low 20s up the Pine and at Vallecito.

Sunday's the better day if you've got outdoor plans. Clear, calm, a few degrees warmer.

The basin's sitting at 166% of median across the SNOTEL network. Red Mountain Pass is at 231% which is the high end, Cascade is at 88% which is the low. Vallecito's at 171%.

Are you getting anything this morning or has it stayed dry on your end?
```

### Rule gate: block

- draft states a bare percentage ('25%'); this voice never gives one, it names which models disagree instead

### Fact checker

clean, no issues

### Editor

- [minor] "The Euro's showing a trace to maybe a half inch for Vallecito and the Florida drainage before noon, the ICON's got a tenth or two of liquid converting to maybe an inch up high, and the GFS and GEM say we're done." :: (editorial, advisory) States a bare percentage in the preceding sentence ('Pop's sitting at 20-25%'), which the automated gate already blocked. (evidence: AUTOMATED RULE GATE, ALREADY RUN ON THIS DRAFT: BLOCK - draft states a bare percentage ('25%'); this voice never gives one, it names which models disagree instead)
- [minor] "Pop's sitting at 20-25% through late morning then dropping to nothing." :: (editorial, advisory) This is the bare percentage the gate blocked; must be removed entirely and replaced with model-disagreement phrasing only. (evidence: PERSONA: Never a percentage. Never a formal confidence label. Express uncertainty by naming which models disagree and how.)
- [minor] "Take that with a big grain of salt (the trough axis timing is the whole question and the models dont agree on it)." :: (editorial, advisory) Reuses the exact grain-of-salt construction from the 11/16 post, which said 'Take any Tuesday evening number with a big grain of salt (the models disagree by close to 0.6" of liquid, which is the whole forecast).' (evidence: PERSONA: Rotate the grain-of-salt phrasing. Three posts running that say 'take that with a big grain of salt' read as a template.) -> The trough axis timing is still uncertain and that drives everything, so dont lock in plans around it.
- [minor] "Sunday's the better day if you've got outdoor plans." :: (editorial, advisory) Reuses the pivot construction from recent posts; this is the near-end sentence that must not repeat. (evidence: PERSONA: The pivot near the end is the same rule. 'Today's dry and straightforward. Tomorrow's the question.' and every rewrite of it are retired.) -> Tomorrow brings the clear window if the yard work or the trail's on the list.

### Magistrate: REVISE

The automated gate correctly blocked a bare percentage statement that violates the persona's voice rules. The editor identified three additional issues: the percentage sentence must be removed entirely (not revised), a grain-of-salt construction that repeats 11/16's phrasing, and a pivot sentence that reuses retired construction. All three fixes are required and supported by the brief and persona rules.

Required changes:
- "Pop's sitting at 20-25% through late morning then dropping to nothing." -> Remove this sentence entirely.
- "Take that with a big grain of salt (the trough axis timing is the whole question and the models dont agree on it)." -> "The trough axis timing is still uncertain and that drives everything, so dont lock in plans around it."
- "Sunday's the better day if you've got outdoor plans." -> "Tomorrow brings the clear window if the yard work or the trail's on the list."

## Round 2

### Draft

```
11/21/26 5:52am: Morning, its Saturday. The sky's already pale over the ridgeline and the air's got that sharp cold edge to it.

Dry day ahead but its not a clean one. The models are split on whether we get one last round of light snow this morning or whether the trough shuts off the moisture before it reaches us. The Euro's showing a trace to maybe a half inch for Vallecito and the Florida drainage before noon, the ICON's got a tenth or two of liquid converting to maybe an inch up high, and the GFS and GEM say we're done.

If we do catch something it'll be above 8,000 feet and done by early afternoon. Durango and Bayfield should stay dry. Vallecito and up the Florida could see light flurries through midday, with maybe an inch at the higher elevations if the Euro's right. The trough axis timing is still uncertain and that drives everything, so dont lock in plans around it.

The passes should be fine for anyone heading north or east today. Coal Bank, Molas and Red Mountain might catch a dusting up top if the Euro verifies, Wolf Creek the same. Check cotrip.org for current conditions and chain law before you head out.

Wind picks up through midday, gusts 15-25mph across the Pine and the valley, then calms tonight. Highs low 40s in town, upper 30s at the lake. Clear and cold tonight, lows mid 20s in town, upper teens to low 20s up the Pine and at Vallecito.

Tomorrow brings the clear window if the yard work or the trail's on the list. Clear, calm, a few degrees warmer.

The basin's sitting at 166% of median across the SNOTEL network. Red Mountain Pass is at 231% which is the high end, Cascade is at 88% which is the low. Vallecito's at 171%.

Are you getting anything this morning or has it stayed dry on your end?
```

### Rule gate: block

- draft states a bare percentage ('231%'); this voice never gives one, it names which models disagree instead

### Fact checker

- [critical] "The Euro's showing a trace to maybe a half inch for Vallecito and the Florida drainage before noon, the ICON's got a tenth or two of liquid converting to maybe an inch up high, and the GFS and GEM say we're done." :: The Euro shows 0.42 inches of snow (not liquid), not a half inch, and the ICON shows 0.12 inches of liquid, not a tenth or two. (evidence: MODEL DISAGREEMENT at Vallecito (next 48h): liquid precipitation (rain plus melted snow): {'Euro': 0.06, 'GFS': 0.0, 'ICON': 0.12, 'GEM': 0.0} inches; snowfall: {'Euro': 0.42, 'GFS': 0.0, 'ICON': 0.0, 'GEM': 0.0} inches) -> The Euro's showing about 0.4 inches of snow for Vallecito and the Florida drainage, the ICON's got around a tenth of liquid, and the GFS and GEM say we're done.
- [critical] "If we do catch something it'll be above 8,000 feet and done by early afternoon." :: The brief shows precipitation probability through the 06:00-11:00 window (morning), not extending into early afternoon. (evidence: Vallecito and the Florida (7650 ft, zone COZ019): 2026-11-21T06:00 -> 2026-11-21T11:00: 31.6-35.6F, snow 0.0in, liquid 0.0in, gusts 10-20mph, pop 23%; 2026-11-21T12:00 -> 2026-11-21T17:00: 33.1-38.1F, snow 0.0in, liquid 0.0in, gusts 15-25mph, pop 7%) -> If we do catch something it'll be above 8,000 feet and done by late morning.
- [minor] "The passes should be fine for anyone heading north or east today." :: (no matching brief line, downgraded) States a present road condition without the required conditional language (should be, I'd expect, looks like). (evidence: LIVE ROAD STATUS: YOU HAVE NONE. -> So you never write what a road IS. Write what they will GET, in the future or the conditional, every time.) -> The passes should stay mostly dry for anyone heading north or east today.

### Editor

- [minor] "Red Mountain Pass is at 231% which is the high end" :: (editorial, advisory) States a bare percentage; this voice never gives one, it names which models disagree instead. (evidence: PERSONA: No bare percentage. Never a formal confidence label. Express uncertainty by naming which models disagree and how.)
- [minor] "The models are split on whether we get one last round of light snow this morning or whether the trough shuts off the moisture before it reaches us. The Euro's showing a trace to maybe a half inch for Vallecito and the Florida drainage before noon, the ICON's got a tenth or two of liquid converting to maybe an inch up high, and the GFS and GEM say we're done." :: (editorial, advisory) Reuses the model-disagreement construction from 2026-11-16: naming models in a list with their outputs, then saying others disagree. (evidence: RECENT POST 2026-11-16: 'Here's the problem: the models are all over the place on amounts. The GFS is showing 0.07" liquid at Vallecito. The GEM is cranking out 0.65". Euro and ICON are in between.') -> The Euro and ICON are showing a trace of moisture this morning, maybe a half inch of snow up high, but the GFS and GEM have us dry already. The trough axis timing is the whole question and its still uncertain.
- [minor] "Are you getting anything this morning or has it stayed dry on your end?" :: (editorial, advisory) Reuses the closing question construction from 2026-11-16: 'What's the [thing] looking like on your end this morning, [option] or [option]?' (evidence: RECENT OPENER/CLOSER 2026-11-16 closed: What's the wind looking like on your end this morning, calm or already picking up?) -> Did anything fall overnight where you are?

### Magistrate: REVISE

Three required changes block approval. The Euro snowfall figure must match the brief's 0.42 inches (stated as 'about 0.4'), the timing must be late morning not early afternoon per the precipitation probability windows, and the bare percentage violates the automated gate rule and must be replaced with the actual SWE measurements from the brief. All other issues are either already satisfied or advisory under relaxed editorial policy.

Required changes:
- "The Euro's showing a trace to maybe a half inch for Vallecito and the Florida drainage before noon, the ICON's got a tenth or two of liquid converting to maybe an inch up high, and the GFS and GEM say we're done." -> "The Euro's showing about 0.4 inches of snow for Vallecito and the Florida drainage, the ICON's got around a tenth of liquid, and the GFS and GEM say we're done."
- "If we do catch something it'll be above 8,000 feet and done by early afternoon." -> "If we do catch something it'll be above 8,000 feet and done by late morning."
- "Red Mountain Pass is at 231% which is the high end, Cascade is at 88% which is the low." -> "Red Mountain Pass is the high end at 8.3 inches SWE, Cascade is the low at 0.7 inches."

Dismissed:
- Editor's minor issue about model-disagreement construction reuse: the construction differs materially from 2026-11-16 (which listed all four models with their liquid totals in a single sentence). This draft names two models showing moisture and two showing dry in a different structure. Editorial policy is relaxed on construction reuse.
- Editor's minor issue about closing question reuse: the construction differs from 2026-11-16 (which asked about wind state with two options). This draft asks about precipitation occurrence. Different subject, different verb structure.
- Fact checker's minor issue about 'The passes should be fine': the sentence already contains 'should' which satisfies the conditional requirement. The road rule requires future/conditional language, which 'should be fine' provides.

## Round 3

### Draft

```
11/21/26 5:52am: Morning, its Saturday. The sky's already pale over the ridgeline and the air's got that sharp cold edge to it.

Dry day ahead but its not a clean one. The models are split on whether we get one last round of light snow this morning or whether the trough shuts off the moisture before it reaches us. The Euro's showing about 0.4 inches of snow for Vallecito and the Florida drainage, the ICON's got around a tenth of liquid, and the GFS and GEM say we're done.

If we do catch something it'll be above 8,000 feet and done by late morning. Durango and Bayfield should stay dry. Vallecito and up the Florida could see light flurries through midday, with maybe an inch at the higher elevations if the Euro's right. The trough axis timing is still uncertain and that drives everything, so dont lock in plans around it.

The passes should be fine for anyone heading north or east today. Coal Bank, Molas and Red Mountain might catch a dusting up top if the Euro verifies, Wolf Creek the same. Check cotrip.org for current conditions and chain law before you head out.

Wind picks up through midday, gusts 15-25mph across the Pine and the valley, then calms tonight. Highs low 40s in town, upper 30s at the lake. Clear and cold tonight, lows mid 20s in town, upper teens to low 20s up the Pine and at Vallecito.

Tomorrow brings the clear window if the yard work or the trail's on the list. Clear, calm, a few degrees warmer.

The basin's sitting at 166% of median across the SNOTEL network. Red Mountain Pass is the high end at 8.3 inches SWE, Cascade is the low at 0.7 inches. Vallecito's at 171%.

Are you getting anything this morning or has it stayed dry on your end?
```

### Rule gate: block

- draft states a bare percentage ('171%'); this voice never gives one, it names which models disagree instead

### Fact checker

- [critical] "Dry day ahead but its not a clean one." :: States the day is dry, but the brief shows precipitation chances up to 23% at Vallecito through midday. (evidence: 2026-11-21T06:00 -> 2026-11-21T11:00: 31.6-35.6F, snow 0.0in, liquid 0.0in, gusts 10-20mph, pop 23%) -> Mostly dry day ahead but the models are split on whether we catch one last round of light snow this morning.
- [critical] "If we do catch something it'll be above 8,000 feet and done by late morning." :: States a snow line (above 8,000 feet) when the brief says no precipitation forecast, so no snow line, do not state one. (evidence: SNOW LINE: no precipitation forecast, so no snow line. Do not state one.)
- [major] "Vallecito and up the Florida could see light flurries through midday, with maybe an inch at the higher elevations if the Euro's right." :: States a point value (an inch) when the persona forbids point values and the Euro shows 0.42 inches of snow. (evidence: snowfall: {'Euro': 0.42, 'GFS': 0.0, 'ICON': 0.0, 'GEM': 0.0} inches) -> Vallecito and up the Florida could see light flurries through midday if the Euro's right.
- [minor] "The passes should be fine for anyone heading north or east today." :: Uses present-tense road state (should be fine) when the brief requires future/conditional phrasing to distinguish forecast from status. (evidence: LIVE ROAD STATUS: YOU HAVE NONE. -> So you never write what a road IS. -> Write what they will GET, in the future or the conditional, every time) -> The passes look like they'll be fine for anyone heading north or east today.

### Editor

- [minor] "Vallecito's at 171%." :: (editorial, advisory) Bare percentage forbidden; this voice names which models disagree instead. (evidence: PERSONA: No bare percentage. Never a formal confidence label. Express uncertainty by naming which models disagree and how.) -> Vallecito's at 2.4 inches SWE, well above median.
- [minor] "The models are split on whether we get one last round of light snow this morning or whether the trough shuts off the moisture before it reaches us. The Euro's showing about 0.4 inches of snow for Vallecito and the Florida drainage, the ICON's got around a tenth of liquid, and the GFS and GEM say we're done." :: (editorial, advisory) Reuses the model-disagreement construction from 2026-11-16 post. (evidence: 2026-11-16 body: 'Here's the problem: the models are all over the place on amounts. The GFS is showing 0.07" liquid at Vallecito. The GEM is cranking out 0.65". Euro and ICON are in between.' Both name models with their totals in the same sentence structure.) -> The Euro and ICON think we'll catch one more light round this morning, the GFS and GEM say the trough shuts off the moisture before it gets here. If the Euro's right Vallecito and the Florida could see light flurries through midday with maybe an inch at the higher elevations.
- [minor] "Dry day ahead but its not a clean one." :: (editorial, advisory) Reuses the pivot construction from 2026-11-16 post. (evidence: 2026-11-16 body contains 'School routes should stay dry this morning' followed by 'The change comes Tuesday afternoon' as the pivot. This draft's 'Dry day ahead but its not a clean one' followed by uncertainty is the same two-part setup.)
- [minor] "Check cotrip.org for current conditions and chain law before you head out." :: Missing https:// protocol in the COTRiP link. (evidence: PERSONA: Always link https://www.cotrip.org/ with the full protocol.) -> Check https://www.cotrip.org/ for current conditions and chain law before you head out.

### Magistrate: REVISE

The fact checker correctly identified a forbidden snow line statement and a point-value snowfall figure where the brief shows 0.42 inches. The automated gate correctly flagged the bare percentage at 171%. The editor's model-disagreement construction concern is valid: both this draft and 2026-11-16 list models with their totals in parallel sentences. All five changes are required to satisfy the brief's rules and the automated gate.

Required changes:
- "Dry day ahead but its not a clean one. The models are split on whether we get one last round of light snow this morning or whether the trough shuts off the moisture before it reaches us. The Euro's showing about 0.4 inches of snow for Vallecito and the Florida drainage, the ICON's got around a tenth of liquid, and the GFS and GEM say we're done." -> "The Euro and ICON think we'll catch one more light round this morning, the GFS and GEM say the trough shuts off the moisture before it gets here."
- "If we do catch something it'll be above 8,000 feet and done by late morning. Durango and Bayfield should stay dry. Vallecito and up the Florida could see light flurries through midday, with maybe an inch at the higher elevations if the Euro's right." -> "If the Euro's right Vallecito and the Florida could see light flurries through midday. Durango and Bayfield should stay dry."
- "The passes should be fine for anyone heading north or east today." -> "The passes look like they'll be fine for anyone heading north or east today."
- "Check cotrip.org for current conditions" -> "Check https://www.cotrip.org/ for current conditions"
- "Vallecito's at 171%." -> "Vallecito's at 2.4 inches SWE, well above median."

Dismissed:
- Editor's claim that 'Dry day ahead but its not a clean one' reuses 2026-11-16 pivot construction: the 2026-11-16 example shows a clean forecast followed by a timing change, while this draft addresses model disagreement on whether precipitation occurs at all. Different structures serving different purposes.

### Final-round edits applied to the writer's text

The published text below is NOT byte-identical to what the writer composed. These reviewer replacements were substituted literally, with no further model call:

- [critical, fact checker] "Dry day ahead but its not a clean one." -> "Mostly dry day ahead but the models are split on whether we catch one last round of light snow this morning."
- [major, fact checker] "Vallecito and up the Florida could see light flurries through midday, with maybe an inch at the higher elevations if the Euro's right." -> "Vallecito and up the Florida could see light flurries through midday if the Euro's right."
- [minor, fact checker] "The passes should be fine for anyone heading north or east today." -> "The passes look like they'll be fine for anyone heading north or east today."
- [minor, editor] "Vallecito's at 171%." -> "Vallecito's at 2.4 inches SWE, well above median."
- [minor, editor] "The models are split on whether we get one last round of light snow this morning or whether the trough shuts off the moisture before it reaches us. The Euro's showing about 0.4 inches of snow for Vallecito and the Florida drainage, the ICON's got around a tenth of liquid, and the GFS and GEM say we're done." -> "The Euro and ICON think we'll catch one more light round this morning, the GFS and GEM say the trough shuts off the moisture before it gets here. If the Euro's right Vallecito and the Florida could see light flurries through midday with maybe an inch at the higher elevations."
- [minor, editor] "Check cotrip.org for current conditions and chain law before you head out." -> "Check https://www.cotrip.org/ for current conditions and chain law before you head out."

Skipped, the quoted sentence was no longer present:
- [magistrate] "Dry day ahead but its not a clean one. The models are split on whether we get one last round of light snow this morning or whether the trough shuts off the moisture before it reaches us. The Euro's showing about 0.4 inches of snow for Vallecito and the Florida drainage, the ICON's got around a tenth of liquid, and the GFS and GEM say we're done."
- [magistrate] "If we do catch something it'll be above 8,000 feet and done by late morning. Durango and Bayfield should stay dry. Vallecito and up the Florida could see light flurries through midday, with maybe an inch at the higher elevations if the Euro's right."
- [magistrate] "Check cotrip.org for current conditions"

Rule gate on the patched text: pass
- nothing flagged

Fact re-check of the patched text:

- [minor] "If the Euro's right Vallecito and the Florida could see light flurries through midday with maybe an inch at the higher elevations." :: (no matching brief line, downgraded) States "maybe an inch" but the brief shows 0.0in snow for all Vallecito/Florida time windows through 17:00. (evidence: Vallecito and the Florida (7650 ft, zone COZ019): 2026-11-21T00:00 -> 2026-11-21T05:00: snow 0.0in, 2026-11-21T06:00 -> 2026-11-21T11:00: snow 0.0in, 2026-11-21T12:00 -> 2026-11-21T17:00: snow 0.0in) -> If the Euro's right Vallecito and the Florida could see light flurries through midday.
- [critical] "Coal Bank, Molas and Red Mountain might catch a dusting up top if the Euro verifies, Wolf Creek the same." :: States present road conditions ("might catch") without CDOT data, violating the road status rule. (evidence: LIVE ROAD STATUS: YOU HAVE NONE. Not for the passes, not for US-550 or US-160... Write what they will GET, in the future or the conditional, every time) -> Coal Bank, Molas and Red Mountain should stay mostly dry with maybe a dusting up top if the Euro verifies, Wolf Creek the same.
- [minor] "Vallecito and up the Florida could see light flurries through midday if the Euro's right." :: Repeats the same claim already made two sentences earlier. (evidence: PERSONA)

Fact-checker objections still standing after the patch:
- "If we do catch something it'll be above 8,000 feet and done by late morning."
- "Coal Bank, Molas and Red Mountain might catch a dusting up top if the Euro verifies, Wolf Creek the same."

