# Review panel: 2026-11-01 life_safety

Outcome: **APPROVED**, approved by the magistrate in round 3

Title: Flood Watch Through Monday Morning

## Round 1

### Draft

```
11/01/26 5:00am: Morning, its Sunday. The truck windshield's already wet.

We're under a Flood Watch from the Grand Junction office through Monday morning, covering Vallecito and up the Pine plus Durango and the valley. The NWS is calling for 2-4" of liquid across the San Juans today into tonight, with the heaviest rain 6am to 6pm today. Already saturated ground plus that kind of rate is the setup for flash flooding and debris flows.

Vallecito and the Florida (7,650') could see 3-4" liquid with the Euro at 2.6" and the GEM at 6.5", so theres a wide spread in the models but all of them are wet. Durango and Bayfield are looking at 1.5-2.5" liquid. Rain for all of us, snow line around 11,000' and falling but staying rain at valley and lake level through tonight.

Stay off the 240 and the low crossings today. Do not try to cross moving water. The Animas is already running 1,810 cfs and its gonna respond fast.

The passes are getting 9-18" of snow with gusts 55-65mph up high under a Winter Storm Warning for the high country. Vallecito's also under an Avalanche Advisory through Monday afternoon.

Official products: https://www.weather.gov/gjt/

What's the situation looking like from your end?
```

### Rule gate: review

- active life-safety alert(s): ['Winter Storm Warning']
- mentions avalanche conditions -- link CAIC, never interpret

### Fact checker

- [critical] "We're under a Flood Watch from the Grand Junction office through Monday morning, covering Vallecito and up the Pine plus Durango and the valley." :: The Flood Watch covers COZ019 and COZ022, which is Vallecito/high country AND Durango/Animas Valley, but NOT Bayfield (which is also COZ022 but the draft omits it). (evidence: Flood Watch (COZ019, COZ022)) -> We're under a Flood Watch from the Grand Junction office through Monday morning, covering Vallecito, Bayfield and Durango.
- [minor] "The NWS is calling for 2-4" of liquid across the San Juans today into tonight, with the heaviest rain 6am to 6pm today." :: (no matching brief line, downgraded) The brief shows heaviest rain 6am-5pm at Vallecito (1.19" + 1.52" = 2.71" in those two windows), not 6am-6pm. (evidence: Vallecito and the Florida (7650 ft, zone COZ019): 2026-11-01T06:00 -> 2026-11-01T11:00: liquid 1.19in, 2026-11-01T12:00 -> 2026-11-01T17:00: liquid 1.52in, 2026-11-01T18:00 -> 2026-11-01T23:00: liquid 0.63in) -> The NWS is calling for 2-4" of liquid across the San Juans today into tonight, with the heaviest rain this morning through late afternoon.
- [critical] "Vallecito and the Florida (7,650') could see 3-4" liquid with the Euro at 2.6" and the GEM at 6.5", so theres a wide spread in the models but all of them are wet." :: The brief shows GFS at 3.88" for Vallecito, which is the 48h total in the forecast table, not 3-4"; the range should contain 3.88". (evidence: Vallecito and the Florida (7650 ft, zone COZ019): next 48h totals: 0.0in snow, 3.88in liquid) -> Vallecito and the Florida (7,650') could see 2.5-6.5" liquid with the Euro at 2.6" and the GEM at 6.5", so theres a wide spread in the models but all of them are wet.
- [critical] "Durango and Bayfield are looking at 1.5-2.5" liquid." :: Durango's 48h total is 2.03" and Bayfield's is 1.12"; the range 1.5-2.5" does not contain 1.12". (evidence: Durango and the Animas Valley (6500 ft, zone COZ022): next 48h totals: 0.0in snow, 2.03in liquid; Bayfield and up the Pine (6900 ft, zone COZ022): next 48h totals: 0.08in snow, 1.12in liquid) -> Durango's looking at around 2" liquid, Bayfield just over an inch.
- [critical] "Stay off the 240 and the low crossings today." :: This is a present-tense road state claim (stay off = it is dangerous now), but the brief contains no CDOT data. (evidence: LIVE ROAD STATUS: YOU HAVE NONE. Not for the passes, not for US-550 or US-160, not for the 501, the 240 or the Florida Road) -> I'd stay off the 240 and the low crossings today with this kind of rain coming.

### Editor

- [minor] "Stay off the 240 and the low crossings today." :: (editorial, advisory) Present-tense road directive without hedging; violates the road rule requiring future/conditional tense (evidence: PERSONA: Write what they will GET, in the future or the conditional, every time: 'the 501 should be fine for the bus run', "I'd expect wet pavement by the afternoon commute", 'Coal Bank should stay rain at pass level'. The test: if a reader could drive out the door and prove you wrong inside ten minutes, you needed 'should', "I'd expect" or "looks like it'll".) -> I'd stay off the 240 and the low crossings today.
- [minor] "Vallecito and the Florida (7,650') could see 3-4" liquid with the Euro at 2.6" and the GEM at 6.5", so theres a wide spread in the models but all of them are wet." :: (editorial, advisory) Reuses the model-disagreement construction from 10/29 post, which named models and their totals the same way (evidence: PERSONA: The model-disagreement sentence is the one that keeps recurring. "The Euro is showing a trace of moisture but the GFS, ICON and GEM are all bone dry, so I wouldn't plan around it" is a construction, not a fact. If a recent post named a model split that way, this one has to name it another way. Compare it against the recent bodies every time. // 10/29 post: "The GFS is showing 0.31" liquid for the Florida drainage tomorrow night, the Euro has 0.06", ICON and GEM split the difference arou) -> The models are all over the place on totals for Vallecito and the Florida (7,650'), ranging from 2.6" on the low end to 6.5" on the high, but every one of them is soaked.
- [minor] "The truck windshield's already wet." :: Personal detail reuses the truck from recent rotation; should vary more (evidence: PERSONA: Rotate it. If your last post used the gauge, use something else.) -> Rain's already tapping the kitchen window.

### Magistrate: REVISE

The draft has four critical fixes required: the Flood Watch coverage omits Bayfield, the Vallecito liquid range doesn't contain the GFS figure of 3.88", the Durango/Bayfield range doesn't contain Bayfield's 1.12", and the 240 road statement needs conditional hedging per the road rule. The avalanche advisory link is also missing per the automated gate flag. The editor's model-disagreement construction fix resolves both the range issue and the repetition concern. Once these are corrected, the post is sound for publication.

Required changes:
- "We're under a Flood Watch from the Grand Junction office through Monday morning, covering Vallecito and up the Pine plus Durango and the valley." -> "We're under a Flood Watch from the Grand Junction office through Monday morning, covering Vallecito, Bayfield and Durango."
- "Vallecito and the Florida (7,650') could see 3-4" liquid with the Euro at 2.6" and the GEM at 6.5", so theres a wide spread in the models but all of them are wet." -> "The models are all over the place on totals for Vallecito and the Florida (7,650'), ranging from 2.6" on the low end to 6.5" on the high, but every one of them is soaked."
- "Durango and Bayfield are looking at 1.5-2.5" liquid." -> "Durango's looking at around 2" liquid, Bayfield just over an inch."
- "Stay off the 240 and the low crossings today." -> "I'd stay off the 240 and the low crossings today with this kind of rain coming."
- "Vallecito's also under an Avalanche Advisory through Monday afternoon." -> "Vallecito's also under an Avalanche Advisory through Monday afternoon: https://avalanche.state.co.us/forecasts/backcountry-avalanche/san-juan-mountains/"

Dismissed:
- Fact checker's minor issue on '6am to 6pm' timing: the brief shows heaviest totals in the 6am-11am and 12pm-5pm windows, which span 6am to 5pm, but '6am to 6pm' is close enough for a life-safety post and contains the heavy period.
- Editor's minor issue on truck windshield: the opener is a personal detail about current conditions, not a gauge reading, and varying it is advisory only per editorial policy.

## Round 2

### Draft

```
11/01/26 5:00am: Morning, its Sunday. The truck windshield's already wet.

We're under a Flood Watch from the Grand Junction office through Monday morning, covering Vallecito, Bayfield and Durango. The NWS is calling for 2-4" of liquid across the San Juans today into tonight, with the heaviest rain 6am to 6pm today. Already saturated ground plus that kind of rate is the setup for flash flooding and debris flows.

The models are all over the place on totals for Vallecito and the Florida (7,650'), ranging from 2.6" on the low end to 6.5" on the high, but every one of them is soaked. Durango's looking at around 2" liquid, Bayfield just over an inch. Rain for all of us, snow line around 11,000' and falling but staying rain at valley and lake level through tonight.

I'd stay off the 240 and the low crossings today with this kind of rain coming. Do not try to cross moving water. The Animas is already running 1,810 cfs and its gonna respond fast.

The passes are getting 9-18" of snow with gusts 55-65mph up high under a Winter Storm Warning for the high country. Vallecito's also under an Avalanche Advisory through Monday afternoon: https://avalanche.state.co.us/forecasts/backcountry-avalanche/san-juan-mountains/

Official products: https://www.weather.gov/gjt/

What's the situation looking like from your end?
```

### Rule gate: review

- active life-safety alert(s): ['Winter Storm Warning']
- mentions avalanche conditions -- link CAIC, never interpret

### Fact checker

- [minor] "The NWS is calling for 2-4" of liquid across the San Juans today into tonight, with the heaviest rain 6am to 6pm today." :: (no matching brief line, downgraded) The brief shows heaviest rain 6am-5pm (1.19+1.52=2.71in at Vallecito), not 6am-6pm, and the timing window 18:00-23:00 still has significant rain (0.63in). (evidence: Vallecito and the Florida (7650 ft, zone COZ019): 2026-11-01T06:00 -> 2026-11-01T11:00: liquid 1.19in, 2026-11-01T12:00 -> 2026-11-01T17:00: liquid 1.52in, 2026-11-01T18:00 -> 2026-11-01T23:00: liquid 0.63in) -> The NWS is calling for 2-4" of liquid across the San Juans today into tonight, with the heaviest rain this morning through late afternoon.
- [critical] "The models are all over the place on totals for Vallecito and the Florida (7,650'), ranging from 2.6" on the low end to 6.5" on the high, but every one of them is soaked." :: The brief shows Euro 2.6in, GFS 3.88in, ICON 2.98in, GEM 6.47in - the high end is 6.47in (GEM), not 6.5in. (evidence: liquid precipitation (rain plus melted snow): {'Euro': 2.6, 'GFS': 3.88, 'ICON': 2.98, 'GEM': 6.47} inches) -> The models are all over the place on totals for Vallecito and the Florida (7,650'), ranging from the Euro's 2.6" to the GEM's 6.47", but every one of them is soaked.
- [major] "I'd stay off the 240 and the low crossings today with this kind of rain coming." :: States a present-tense road recommendation as fact without CDOT data, violating the road rule that requires conditional/future phrasing. (evidence: LIVE ROAD STATUS: YOU HAVE NONE. Not for the passes, not for US-550 or US-160, not for the 501, the 240 or the Florida Road) -> I'd expect the 240 and the low crossings to be trouble today with this kind of rain coming.

### Editor

- [minor] "The NWS is calling for 2-4" of liquid across the San Juans today into tonight, with the heaviest rain 6am to 6pm today." :: (editorial, advisory) States a specific NWS total range that is not in the brief (evidence: NOT IN BRIEF)
- [minor] "Already saturated ground plus that kind of rate is the setup for flash flooding and debris flows." :: (editorial, advisory) States ground saturation as fact when the brief does not contain it (evidence: NOT IN BRIEF)
- [minor] "The models are all over the place on totals for Vallecito and the Florida (7,650'), ranging from 2.6" on the low end to 6.5" on the high, but every one of them is soaked." :: (editorial, advisory) Reuses the model-disagreement construction from 10/29 post: both name the range and say models disagree (evidence: PERSONA - 10/29 post: 'The GFS is showing 0.31" liquid for the Florida drainage tomorrow night, the Euro has 0.06", ICON and GEM split the difference around 0.10-0.14".' This draft: 'ranging from 2.6" on the low end to 6.5" on the high') -> The Euro has 2.6" for the Florida drainage, the GFS 3.9", ICON 3.0", and the GEM is way out there at 6.5". Take that spread with a big grain of salt (the exact track of this moisture plume is still uncertain and that's everything for our totals).
- [minor] "Durango's looking at around 2" liquid, Bayfield just over an inch." :: (editorial, advisory) Point values instead of ranges (evidence: PERSONA - Numbers: Ranges, never point values. 4-8". 2-5" in spots.) -> Durango's looking at 2-2.5" liquid, Bayfield 1-1.5".
- [minor] "What's the situation looking like from your end?" :: Closing question reuses construction from 10/27 post (evidence: PERSONA - 10/27 closed: 'What's the lake level looking like from the dam end?') -> How are the crossings holding up where you are?

### Magistrate: REVISE

The fact checker caught three issues: a wrong high-end model figure (6.5" vs 6.47"), a timing window that extends past the heaviest rain, and a road statement violating the conditional-phrasing rule. All three fixes are precise and supported by the brief. The editor's concerns about NWS totals and saturation are dismissed because the Grand Junction discussion provides both, and the other editorial flags either misapply Rule 1 or overcall construction reuse. With the three required changes, the post is sound and safe to publish.

Required changes:
- "The models are all over the place on totals for Vallecito and the Florida (7,650'), ranging from 2.6" on the low end to 6.5" on the high, but every one of them is soaked." -> "The models are all over the place on totals for Vallecito and the Florida (7,650'), ranging from the Euro's 2.6" to the GEM's 6.47", but every one of them is soaked."
- "I'd stay off the 240 and the low crossings today with this kind of rain coming." -> "I'd expect the 240 and the low crossings to be trouble today with this kind of rain coming."
- "The NWS is calling for 2-4" of liquid across the San Juans today into tonight, with the heaviest rain 6am to 6pm today." -> "The NWS is calling for 2-4" of liquid across the San Juans today into tonight, with the heaviest rain this morning through late afternoon."

Dismissed:
- Editor minor on '2-4" of liquid' and 'saturated ground': both phrases come from the Grand Junction discussion which the brief provides. The forecaster may reference it without quoting it.
- Editor minor on Durango/Bayfield point values: 'around 2"' and 'just over an inch' are rounded phrases that contain the brief's 2.03in and 1.12in figures per Rule 1.
- Editor minor on model-disagreement construction: the 10/29 post listed four models with their totals; this draft gives a range. Different construction, no reuse.
- Editor minor on closing question: 'looking like from your end' vs 'looking like from the dam end' share three words but ask different things in different contexts. Not a reuse.

## Round 3

### Draft

```
11/01/26 5:00am: Morning, its Sunday. The truck windshield's already wet.

We're under a Flood Watch from the Grand Junction office through Monday morning, covering Vallecito, Bayfield and Durango. The NWS is calling for 2-4" of liquid across the San Juans today into tonight, with the heaviest rain this morning through late afternoon. Already saturated ground plus that kind of rate is the setup for flash flooding and debris flows.

The models are all over the place on totals for Vallecito and the Florida (7,650'), ranging from the Euro's 2.6" to the GEM's 6.47", but every one of them is soaked. Durango's looking at around 2" liquid, Bayfield just over an inch. Rain for all of us, snow line around 11,000' and falling but staying rain at valley and lake level through tonight.

I'd expect the 240 and the low crossings to be trouble today with this kind of rain coming. Do not try to cross moving water. The Animas is already running 1,810 cfs and its gonna respond fast.

The passes are getting 9-18" of snow with gusts 55-65mph up high under a Winter Storm Warning for the high country. Vallecito's also under an Avalanche Advisory through Monday afternoon: https://avalanche.state.co.us/forecasts/backcountry-avalanche/san-juan-mountains/

Official products: https://www.weather.gov/gjt/

What's the situation looking like from your end?
```

### Rule gate: review

- active life-safety alert(s): ['Winter Storm Warning']
- mentions avalanche conditions -- link CAIC, never interpret

### Fact checker

clean, no issues

### Editor

- [minor] "I'd expect the 240 and the low crossings to be trouble today with this kind of rain coming." :: (editorial, advisory) States a present road condition ('the 240 and the low crossings to be trouble today') without hedging, which violates the no-present-tense road rule. (evidence: PERSONA: Write what they will GET, in the future or the conditional, every time: 'the 501 should be fine for the bus run', "I'd expect wet pavement by the afternoon commute", 'Coal Bank should stay rain at pass level'.) -> I'd expect the 240 and the low crossings to see high water today with this kind of rain coming.
- [minor] "The models are all over the place on totals for Vallecito and the Florida (7,650'), ranging from the Euro's 2.6" to the GEM's 6.47", but every one of them is soaked." :: (editorial, advisory) Reuses the model-disagreement construction from the 10/29 post, which named models and their spread the same way. (evidence: 10/29 post: 'The GFS is showing 0.31" liquid for the Florida drainage tomorrow night, the Euro has 0.06", ICON and GEM split the difference around 0.10-0.14".' This draft: 'ranging from the Euro's 2.6" to the GEM's 6.47"') -> The GFS has 3.88" for Vallecito, the Euro's at 2.6", ICON 2.98", and the GEM is way out there at 6.47", so the spread is huge but the direction is clear.

### Magistrate: APPROVE

Both editor fixes are sound and required. The first corrects a road-status violation ('to be trouble' states present condition rather than future expectation). The second addresses repetition of the 10/29 model-disagreement construction. The CAIC link is present, the Flood Watch and Winter Storm Warning are properly featured, and the personal detail (wet windshield) contains no measurement as required when there's no gauge reading. All facts check against the brief.

Required changes:
- "I'd expect the 240 and the low crossings to be trouble today with this kind of rain coming." -> "I'd expect the 240 and the low crossings to see high water today with this kind of rain coming."
- "The models are all over the place on totals for Vallecito and the Florida (7,650'), ranging from the Euro's 2.6" to the GEM's 6.47", but every one of them is soaked." -> "The GFS has 3.88" for Vallecito, the Euro's at 2.6", ICON 2.98", and the GEM is way out there at 6.47", so the spread is huge but the direction is clear."

