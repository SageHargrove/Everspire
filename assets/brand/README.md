# GILTGRAVE brand assets

`Giltgrave_Icon.png` (1254×1254) is the **master**. Liam's final approved mark:
a stepped spire piercing a broken ring, split into two interlocking pieces —
ivory (left arc + main spire) and violet (right arc + broken tower fragment) —
with bevelled edges and gradient shading.

**The master is a raster, deliberately.** An earlier flat-vector trace was
rejected: vector flat-fills throw away the bevel and gradient that make this
mark look finished, and nothing in the pipeline needs SVG. Windows `.ico`
is a bitmap container, favicons take PNG, and the React UI takes `<img>`.
Do not "upgrade" this to SVG.

## Derived files (regenerate from the master, never edit by hand)

| file | use |
|---|---|
| `giltgrave-icon.ico` | Windows exe / taskbar / shortcut — 9 sizes, 16→256 |
| `giltgrave-icon-1024.png` | RGBA master export, source for any new size |
| `giltgrave-icon-{16,20,24,32,40,48,64,128,256}.png` | favicon, web, in-app, store |
| `giltgrave-discord-512.png` | Discord server icon: mark at 62% height on the violet-to-ink radial so it survives the circle crop. Never upload the black-background master to Discord; the mark reads tiny. Circle-cropped contexts get ~62%, square contexts ~85%. |

**How they're built** (the master has a solid black background, no alpha):
1. Key black out via `alpha = clip(max(R,G,B) / 70, 0, 1)` — max-channel, so
   the violet stays fully opaque while anti-aliased edges ramp.
2. Un-premultiply RGB by that alpha, so edges carry no black halo on light
   grounds.
3. Crop to content, pad to square, LANCZOS down-sample.
4. **Two framings**: ≤32px uses a tight crop (0.99 fill) because the mark is
   tall and narrow and goes to a sliver otherwise; >32px uses an airy 0.88.

## Known constraint

The ivory piece has **low contrast on light backgrounds** — on a light-theme
Windows taskbar roughly half the mark fades out. Fine as-is on dark (Win11
default, and the game's own chrome). If light-ground use matters later, the
fix is a dark rounded-plate variant or an outlined cut — a new master from
Liam, not a code change.

## Colour tokens

ivory `#efe8da` · violet `#8b46d6` · gold `#ffd88a` · dim gold `#b89762` ·
ink `#14101e`

## Status

**Wired in 2026-08-04.** `assets/icon.ico` is this mark, the exe was rebuilt
as `Giltgrave.exe`, and the landing favicon matches. The previous icon is kept as
`assets/icon.everspire-backup.ico`.

Wordmark set (rendered in the game's own bundled Cinzel, transparent PNG):
`giltgrave-wordmark-{ivory,gold,black}.png`, plus `giltgrave-lockup-stacked.png`,
`giltgrave-lockup-horizontal.png` and `giltgrave-lockup-mark-word.png`.
`giltgrave-lockup-tagline.png` (diamond + GILTGRAVE + "Heroes die. Legacies do not."
between gold rules, violet glow baked in) is the hero/marketing lockup for
dark grounds — Steam library logo, trailer cards.

2026-08-04: the old tower-mark exports (tower_mark, discord/app icons, a
second giltgrave.ico) were removed — the spire-and-ring mark is the ONLY mark
going forward. The tower survives only in `assets/icon.everspire-backup.ico`
and `assets/concepts/` for history.

Still owed: the trademark / domain / handle sweep on "Giltgrave".
