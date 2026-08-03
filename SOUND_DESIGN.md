# Everspire — Sound Design Plan (v2 — Sacred-Jazz Fusion)

Music: **Suno Pro** (v5.5). SFX: keep synth kit, upgrade hero moments later (ElevenLabs free tier if ever needed). VO: deferred indefinitely — stingers carry the payoffs.

---

## 1. The style anchor — SACRED-JAZZ FUSION (locked 2026-07-16)

Winner of the theme bake-off: **acid-jazz fusion with gothic orchestral flourishes** — funky bass and jazzy keys (the Atlus cool) under cathedral choir and bells (the illuminated art). One reference song is the DNA source: the winning combat roll ("the chorus one").

### House prompt prefix — start every prompt with:

```
Instrumental, acid-jazz fusion with gothic orchestral flourishes,
```

### The tone dial (COMMITTED 2026-07-17 after alternatives review — no more direction second-guessing)
Every track sets one dial: funk ↔ sacred. The groove is the gacha's seduction; the choir is what it costs.
- **Funk-forward**: Arena, Tavern, Expeditions, Herald
- **Balanced**: Combat, Boss, Elite, Hub, Tower Ascent, Title, Athenaeum
- **Sacred-only (no groove)**: Synthesis, Memorial, Summon ritual bed
- **Sacred + MAX energy (the exception)**: 6★ flourish, 7★ Ascension — these are hype payoffs; full band + choir together, NOT solemn (see HYPE PRINCIPLE in stingers).
Tonal misfits are fixed by sliding THAT track's dial darker, never by re-litigating the direction.

### House palette
- Rhythm: funky/slap bassline, tight punchy drums (brushes when quiet)
- Color: jazzy electric piano (Rhodes), brass hits, vibraphone for quiet screens
- Sacred layer: cathedral choir swells, church bells, organ (bosses only), harp
- Tempo bands: menus 60–85, exploration 95–110, combat 155–165, boss 170+

### Consistency stack (in order of strength)
1. **Cover** the winning combat roll for anything that should share its melody (boss, title) — leitmotif.
2. **+ Inspo** with the winner attached for new-melody tracks in the same family.
3. **Saved Style** — save the winner's expanded style text (right panel → Styles) and reuse it.
4. House prefix + palette words in every prompt.

**Inspo bleed-through** (the chorus reappearing near-identically across Inspo tracks): a MOTIF recurring = good (cohesion); a literal 15–30s arrangement REPEAT = bad. Fixes, cheapest first: (a) **vary the reference** — don't Inspo everything off the combat track; use a calmer keeper (Tavern/Athenaeum) as the reference for calm tracks; (b) **drop Inspo** on identity-critical tracks and rely on prompt + house palette (Synthesis/Memorial already Inspo-free); (c) lower the influence slider if present. **Matters most for the Hub ×3 rotation** — if all three share the same chunk the rotation is pointless, so vary-reference or drop-Inspo across A/B/C. Barely matters for screens never heard back-to-back.

### Length rule
Err longer, NEVER shorter. Loops get loop-cut to a seamless internal section in-engine; one-shots get cropped to their payoff — so source length barely matters, and a shorter loop only repeats more often. 2:30–4:00 = ideal loop length (all tracks fine here). **Arena short-loop RESOLVED: made 2 Arena tracks instead of extending → Arena joins the rotation club** (better than a long loop — real variety, like Tavern/World/Hub). Extend was finicky (regenerates in a different key/feel); 2 tracks was the cleaner fix.

**Download format: WAV for ALL** (Pro perk). These are masters — I normalize/loop-cut/compress-once in post; starting from lossless avoids generation loss. WAV masters don't ship, size is a non-issue.

### MUSICAL TAKEOVER (6★ Pull + 7★ Ascension) — Liam idea 2026-07-19
These two are NOT cropped — they play FULL as an audio takeover: the reveal ducks normal BGM and plays the whole track start-to-finish, continuing even if the player navigates away, so the hype moment is unmissable. Engine rules: (1) ONE takeover per event — best rarity in a multi-pull fires one, no stacking/restarting per card; (2) skippable navigation but audio keeps playing until the track ends or combat/another takeover starts. These are the only full-length-as-composed tracks in the OST.

### Post-production (later, in Suno Studio + Audacity/ffmpeg)
- Crop chorus → victory stinger raw material; Get Stems → drums-less low-intensity variants.
- Loop-cut at bar boundaries, crossfade tail→head.
- Engine: Web Audio gapless looping (MP3 + `loop=true` always gaps), per-screen routing, crossfades, ducking. Files → `frontend/public/audio/bgm/`, `.../stingers/`.
- Loudness-normalize: −16 LUFS loops, stingers ~3 dB hotter.

---

## Status (2026-07-19)

**KEPT (~19):** Combat, Boss, Elite, Title, Tavern 1, Tavern 2, Summon Altar, Synthesis, Athenaeum, Expeditions, Tower Ascent, Herald, Memorial, Victory, Defeat, Arena, World 1 (swaggering) + World 2 (orchestral ambient — both kept, different vibes), Hub 1.

6★ flourish DONE (nailed it), 7★ Ascension DONE (Option C coronation), Hub 1 + Hub 2 DONE.

**Still to generate — ONE track left: Hub 3** (nocturne or lounge, funk prefix, moodier — see below).

**Cut to SFX kit (no longer OST tracks):** all rarity reveals (except 6★ flourish), all 2★–6★ evolution stings.

## 2. Track list + prompts (all get the house prefix)

### Combat family — via COVER of the winning roll (shared melody)

**Combat — standard**: the winning roll itself (loop-cut it).

**Boss** (Cover, style text:)
```
epic desperate boss battle, aggressive slap bassline, thunderous double-time drums, full cathedral choir, pipe organ stabs, urgent brass, the main melody returning bigger and darker each time, overwhelming and climactic, 172 BPM, no vocals
```

**Elite / miniboss** (Cover:)
```
aggressive relentless battle, driving slap bass, pounding drums, choir accents, brass stabs, tense and unyielding, the main melody fragmented and urgent, 165 BPM, no vocals
```

**Title screen** (Cover — the foreshadow trick:)
```
slow mysterious noir arrangement, brushed drums, upright bass, sparse glassy electric piano carrying the main melody gently, distant cathedral choir, church bells, smoky and inviting, awe at the foot of an infinite tower, 75 BPM, no vocals
```

### New-melody tracks — via + INSPO with the winner attached

**Base hub — ROTATION SET of 3** (most-heard screen; the BGM manager shuffles per-screen playlists, no back-to-back repeats. Rotation policy: Hub ×4, Tavern ×2, World ×2, Arena ×2, everything else ×1 — expand by exposure in live-service patches.)

**Hub 1 KEPT** (cinematic chamber folk, 75 BPM, brushed groove, soft Rhodes/harp — owns the soft/restful lane). First A/B/C attempts all DIED — they were all "gentle & warm" = lifeless furniture. Hub 2/3 need DIFFERENT moods with a PULSE (melody or groove), plain-gen (no Inspo — avoids combat bleed + cloning Hub 1). Judge by "unobtrusive but not dead."

*Hub 2 — cozy, grooving, base-is-alive:*
```
cozy warm home theme with a gentle groove, soft walking upright bass, lightly swinging brushed drums, mellow Rhodes and vibraphone trading a relaxed melody, faint choir pad and distant bells, the stronghold bustling with life between climbs, comfortable and unhurried, 90 BPM, no vocals
```
**Hub 2 KEPT** (cozy grooving, 90 BPM). Hub 3 still needed — "hopeful dawn" (orchestral prefix, bright/major) FAILED; keep the FUNK prefix and go MOODIER (winners are restful + lively; missing mood = reflective). Last track needed:

*Hub 3 — late-night nocturne (rec):*
```
late-night nocturne, smoky Rhodes and soft muted trumpet trading a wistful melody, gentle upright bass, brushes on the drums, distant choir pad and low bells, the quiet hours in the stronghold, reflective and warm, bittersweet calm, 70 BPM, no vocals
```
*Hub 3 — alt (elegant noble lounge):*
```
elegant noble lounge theme, graceful piano melody, warm bass, soft brushed swing, tasteful brass swells and harp flourishes, gentle choir and bells woven through, refined and calm with quiet dignity, 85 BPM, no vocals
```

**Tavern** (have one — regen under Pro in-theme if the old one clashes)
```
lively jazz lounge, walking upright bass, playful piano trio, brushed swing drums, warm brass, rowdy but cozy medieval tavern after a long climb, 110 BPM, no vocals
```

**Summon Altar** (ritual bed — tension, no resolution; reveal stingers do the payoff)
```
dark ambient jazz ritual, low sustained drone, sparse ominous piano voicings, deep ceremonial drums, choir fragments rising and receding, tension that never resolves, the moment before something answers, 90 BPM, no vocals
```

**Synthesis Chamber** (hero sacrifice — ominous ritual dread, NOT a happy miracle; distinct from Memorial: Memorial = grief after, Synthesis = dread during)
```
dark sacrificial ritual, low ominous drone, slow tolling bell, deep male choir chanting underneath, sparse dissonant piano notes, heartbeat-like muffled drum pulse, dread and solemn gravity, a price being paid, tension that never resolves, 55 BPM, no vocals
```

**Athenaeum / research**
```
quiet late-night jazz study, soft piano, vibraphone, upright bass, brushed drums barely there, faint choir pad, candlelit and scholarly, patient, 60 BPM, no vocals
```

**Expeditions / world map**
```
adventurous mid-tempo jazz fusion, traveling groove, warm bassline, bright electric piano, hopeful brass melody, open road under a wide sky, 105 BPM, no vocals
```

**Arena / PvP / tournaments** (v2 — less big-band show, more gladiator)
```
hard-hitting competitive battle groove, gritty slap bass, driving aggressive drums, dark brass riffs, two dueling lead melodies trading bars like opponents, choir surges on the impacts, fierce and confident, a coliseum under cathedral banners, 145 BPM, no vocals
```

**World / overworld map** (distinct from Expeditions — the "OST - World" roll used the deprecated swaggering-arena prompt; regen with this. Grand and exploratory, not a battle groove.)
```
grand exploratory overworld theme, sweeping mid-tempo groove, warm walking bassline, wide string pads, bright electric piano and harp motif, distant cathedral choir and bells, a vast world seen from above, wonder and forward pull, 100 BPM, no vocals
```

**Memorial / Death Ceremony** (v2 — Suno loves resolving to a major "happy" cadence; forbid it. If a roll is perfect except the ending, just trim the last bars in post instead of discarding.)
```
mournful slow elegy, solo piano, upright bass, distant wordless choir, single tolling church bell, long silences between phrases, grief and honor, stays in minor key throughout, ends unresolved on a suspended fading chord, no triumphant resolution, 50 BPM, no vocals
```

**Tower Ascent (floor select / pre-climb)**
```
tense simmering jazz groove, pulsing bassline, ticking hi-hats, sparse electric piano stabs, low choir pad building anticipation, church bell accents, gathering resolve before the climb, restrained energy that never fully releases, 100 BPM, no vocals
```

**Herald / seasonal (Emberfall)**
```
smoldering minor-key jazz groove, low brass, crackling hand percussion, embers rising into a night sky, ceremonial but ominous, 85 BPM, no vocals
```

### Stingers (non-looping; trim tight)

**On length:** Suno ignores "10 seconds" etc. and always makes a full track — that's EXPECTED and fine. Stingers are carved out in post: generate full, scrub the whole clip (the big choir/bell payoff is often ~15–20s in, NOT at the start), crop the best 3–8s window. Crop in Suno (Edit ▸ Crop) or Audacity (zero-crossing cut + fast fade-out to kill end-clicks — worth it for stingers). Loops don't care: longer = repeats less often = better.

**Victory** — COVER of the winning combat track (so the jingle bursts with the combat melody — FF-style), style text:
```
short triumphant victory fanfare, brass and bells over a funky bass run, one big choir hit, celebratory, resolves cleanly within ten seconds, no vocals
```
Fallback if covers come out weird at short form: plain generation with the same prompt. All OTHER stingers (Defeat, reveals, evo stings, Ascension) = plain generations, NO Inspo — the choir/bell language carries the consistency, and a funk battle reference would drag them toward groove.
I like this one; it is 28 seconds tohugh, but since suno can generate 30 second ones apparently sometimes, I'm fine with that.

**Defeat** (v2 — old one was a limp fade; this is a gut-punch then hollow silence. Two flavors, pick whichever lands.)
```
sudden crushing defeat sting, one heavy dissonant low brass and organ swell collapsing downward, a single cracked bell, choir gasping then cut to cold silence, final and hollow, no vocals
```
*Quieter alt:*
```
quiet devastating defeat, a low piano chord falling into emptiness, distant bell, a breath of choir dying away, the weight of loss, ends unresolved in silence, no vocals
```

**HYPE PRINCIPLE (correction 2026-07-19):** the 6★/7★ payoffs are the game's most EXCITING moments, and hype ≠ grandeur. Sacred/choral/solemn = holy, not thrilling. Euphoria needs ENERGY — tempo, driving drums, slap bass, and a DROP. Earlier "sacred-only, no groove" was wrong for these. Fix: sacred-jazz fusion at MAX energy, structured build → DROP → triumphant sustain, full choir+organ+brass ON TOP of the full band, not alone.

**Rarity reveals — DROPPED as OST tracks (Liam call 2026-07-19: bespoke music per rarity is overkill).** 1★–5★ reveals = **SFX kit** (graphics-synced shimmer/chime/whoosh). ONE exception: a short **6★ jackpot flourish** (the top pull's payoff burst):
```
explosive triumphant jackpot hit, a fast rising choir-and-bell swell that SLAMS into a full drop, massive cathedral choir and deep organ over driving slap bass and pounding drums all hitting together, brass fanfare on top, euphoric and overwhelming, the best possible outcome, high energy, no vocals
```
(Plain-gen, or Crop the drop out of a triumphant combat Cover.)

**Evolution stings — 2★–6★ DROPPED as OST (Liam call 2026-07-19), use SFX kit.** Evolution music shrinks to ONE piece: the 7★ Ascension — being the only evolution with real music is what sells 7★ as the game's peak.

**7★ Ascension ceremony** (evolution-exclusive peak — 20–30s set piece; sacred AND hype). 6★ NAILED IT; Ascension kept failing (inspo/cover/standalone) because its slow "sacred build that explodes" arc doesn't land — the reverent intro isn't hype and the payoff comes too late. Lesson from 6★: **immediate + triumphant beats slow + sacred.**
- *Best: EXTEND the winning 6★* into the full ceremony (Edit ▸ Extend) — build it from the sound that already works. Continuation text: `continue into a soaring sustained climax, full cathedral choir and organ over driving drums and funky slap bass, blazing brass fanfares, church bells pealing in celebration, euphoric victory growing wave on wave, no vocals`
- *Stay-hype anthem:* `triumphant coronation anthem, immediately huge and euphoric, driving drums and funky slap bass locked in, full cathedral choir and blazing brass carrying a soaring heroic melody, deep organ and pealing church bells, relentless celebration that keeps climbing, the pinnacle achieved, 150 BPM, no vocals`
- *Coronation (choir as accent, if sacred layer muddies it):* `epic triumphant fanfare anthem with funk energy, huge brass fanfares and pounding taiko drums, driving slap-bass groove, soaring string melody, choir and church bells as bright accents, glorious and celebratory, a hero crowned in golden light, powerful and hype, 155 BPM, no vocals`

### Reuse map
- Forge / Market / Facilities / Farm → Base hub
- Guild Hall → Tavern; Guild War → Elite
- 10 tower zones → standard combat (low bands) / elite (mid) / boss-adjacent tension (top) — per-zone music is v2
- Chat drawer / modals / codex → no music switch

---

## 2.5 Adaptive combat music (fights are shorter than songs — solved)

1. **Session-persistent BGM**: combat track runs continuously across consecutive floors in a zone; resets only on leaving the tower. (Hades / Slay the Spire model — fits chained-floor climbing perfectly.)
2. **Layered intensity**: Get Stems on the combat track → drums-less mix plays on Tower Ascent / between fights, full mix crossfades in when combat starts — same timeline, so the drums just "kick in" with the fight. Two synced Web Audio buffers + gain crossfade.
3. **Boss phase → chorus jump**: on phase transition, seek the boss track to its chorus timestamp (mark once in Audacity). Roadmap already has boss phases; this makes the music feel composed per-fight.
4. **Jukebox** in Tavern/Hearth ("the bard's repertoire"): unlocked tracks play in full; unlocks tied to progression (clear zone → zone track; first 7★ → Ascension ceremony). OST as collectible content.
5. **Loop-cut placement**: combat loops start near the hook, not the intro — the first 30s are the only guaranteed listen. Slow intros are for linger-screens only.

## 3. Order of operations

1. ~~Lock the winner, Cover chain, most Inspo tracks~~ — DONE (14 kept, see Status).
2. **Hub ×3 rotation set** (Inspo) — top remaining priority.
3. Regen: **Defeat** (v2), **World** (World/Arena v2).
4. **7★ Ascension ceremony** (plain gen).
5. **SFX kit**: reveal + evolution sounds (synth kit or ElevenLabs samples), optional 6★ flourish.
6. Engine: Web Audio BGM manager (gapless loops, per-screen routing, crossfade, ducking, session-persistent combat, stem layering).
7. Video-ad music: COVER the winner. Two options (judge rolls by the final 15s — the ending must slam shut, not noodle):

   *Instrumental:*
   ```
   epic cinematic trailer arrangement, starts sparse and mysterious with solo piano and distant choir, builds with rising drums and slap bass, explodes into full cathedral choir and brass carrying the main melody, dramatic pause before the final hit, huge clean ending, no fade out, no vocals
   ```

   *Vocal (Atlus-style anthem — uncheck Instrumental; optionally add "lyrics about climbing an endless tower, defying fate"):*
   ```
   epic stylish trailer anthem, confident female vocalist singing a short soaring hook over the main melody, funky slap bass, driving drums, cathedral choir answering the vocal line, church bells, builds to a massive final chorus with a clean powerful ending, no fade out, minimal lyrics, anthemic
   ```

## ENGINE — BUILT 2026-07-19 ✅
- 25 WAV masters → normalized OGG in `frontend/public/audio/` via `frontend/scripts/encode_audio.mjs` (ffmpeg-static, loudnorm I=-16 loops / -14 hot). Re-run the script whenever masters change (700MB WAV → 70MB OGG).
- `frontend/src/audio.js` = scene-based Web Audio BGM manager: lazy decode+cache, rotation (Hub×4 / Tavern×2 / World×2 / Arena×2, no immediate repeat), 1s crossfades, session-persistent combat (same-scene = no restart), `setBgmScene(scene)`, `playMusicStinger` (ducks bed) for Victory/Defeat, `playTakeover` (full-track override, one-per-event, persists across navigation) for 6★ pull + 7★ Ascension. `useBgmScene(scene)` hook (src/useBgmScene.js) for panels.
- Wired (ALL screens): App.jsx tab→scene; TowerPage combat / boss (10th or boss-typed) / elite (miniboss floors) + victory/defeat + ascent; SummoningOverlay 6★ takeover; HeroesPage handleAscend → ascension takeover; Synthesis/Memorial/Athenaeum panels; BasePage Dining Hall + Tavern facilities → tavern; GuildHall → tavern; ArenaPage bout → arena, else world.
- NOT wired (enhancements only, not screen routing): per-track seamless LOOP_POINTS (whole-buffer loop for now — tune if a seam clicks); stem-layered intensity + boss-phase chorus jump; SFX real-sample upgrades. Old `public/bgm.mp3` now unused (safe to delete).

## 4. Odds and ends

- **Suno Studio**: use at post phase for loop-cutting/stem work, not for generation.
- **Voices (née Personas)**: vocal-identity tool — irrelevant for instrumental OST. Ignored.
- **Licensing**: everything shipping must be generated while subscribed (Pro). Old f2p favorites can seed Covers/Inspo but can't ship themselves.
- **Logo**: SVG illuminated wordmark (drop-cap initial, gold leaf) + optional SD-generated emblem. Suno cover-art gen: not for this.
- **Publishing the OST**: never naked, always wearing the game. No Suno publishing (wrong audience), no pre-launch Spotify album (no discovery value + AI-music platform/backlash friction). DO: trailer, short-form gameplay clips with the boss chorus, teaser tracks in Discord pre-playtest, free OST playlist on the game's YouTube channel at launch.
