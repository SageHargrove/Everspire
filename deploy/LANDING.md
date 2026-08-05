# Landing page

`https://170.9.255.240.nip.io/` now serves a real page instead of a JSON stub.
Eventually **playeverspire.com** points at this same box and this same page.

**Not deployed yet** — the code is in the repo and verified locally; it goes
live on the next `redeploy_world_server.sh`.

## Why it lives in the API server, not Caddy

Serving it from `arena_server/main.py` needs no new vhost, no second TLS
certificate, and no reverse-proxy rule that could shadow an API route. It also
ships through the deploy script that already exists.

The safety check that made this fine: **nothing in the game client ever
requests the bare root.** Every call is under `/auth` or `/arena`
(`frontend/src/api/arenaServerClient.js`). The old `GET /` handler was an
explicitly "human-friendly" JSON stub for people who pasted the URL into a
browser — so this replaces a placeholder, not an endpoint.

## Routes

| route | what |
|---|---|
| `GET /` | the landing page (`arena_server/landing/index.html`) |
| `GET /download` | 302 → `github.com/SageHargrove/Giltgrave/releases/latest` |
| `GET /status` | the JSON that used to be at `/` — kept for uptime checks |

`/download` is indirection on purpose: publishing a new release needs no edit
here and no redeploy. GitHub redirects `/releases/latest` to the newest
release, and to the releases index when there are none, so the button never
404s even before the first build exists.

## Deploy

Same flow as any world-server change (host + key are in `RUNBOOK.local.md`):

```bash
tar czf toe_deploy.tgz arena_server backend
scp -i "$TOE_KEY" deploy/redeploy_world_server.sh toe_deploy.tgz "$TOE_HOST":/home/ubuntu/
ssh -i "$TOE_KEY" "$TOE_HOST" 'bash redeploy_world_server.sh'
```

`arena_server/Dockerfile` does `COPY arena_server /app`, so `landing/` is
picked up with no Dockerfile change.

Verify after:

```bash
curl -s "$TOE_URL"/ | head -5                     # HTML, not JSON
curl -s -o /dev/null -w '%{http_code}\n' "$TOE_URL"/status    # 200
curl -s -o /dev/null -w '%{redirect_url}\n' "$TOE_URL"/download
```

## Known gap

**The download button has nothing to download.** No release has been published
(`/repos/SageHargrove/Giltgrave/releases` returns `[]`), so the button lands on
an empty releases page. Publish a build first, or accept that it's a
placeholder until then:

```bash
python tools/make_release.py          # stages release/Giltgrave + zip + setup exe
gh release create v0.1.0-playtest release/Giltgrave-playtest.zip release/Giltgrave-Setup.exe
```

## The visual pass (2026-08-03)

The page now uses the game's actual Illuminated design system — the exact
tokens from `frontend/src/index.css` (ink `#08060e`, gold `#b89762`/`#d8bb84`,
violet bloom, notched panels, parallelogram buttons, ghost/solid stacked
titles, Cinzel + Cormorant Garamond).

Still **zero external requests**: the fonts are self-hosted WOFF2s and all art
is compressed local copies, served by the same container.

| piece | where |
|---|---|
| Page | `arena_server/landing/index.html` (self-contained CSS/JS) |
| Fonts, key art, zone art, sigils | `arena_server/landing/assets/` — mounted at `/landing/assets` in `main.py` |
| Screenshot gallery | hidden until captures land in `assets/shots/` — see `deploy/SHOTLIST.md` |
| Edition chooser | every Download button opens a Standard vs With-Generation modal; deep-linkable via `#choose` |
| `GET /download?edition=gpu` | redirects to `Giltgrave-Setup-GPU.exe` on the latest release, degrading to the standard installer, then the releases page |
| `?capture` query param | reveals everything and drops the 100vh hero so one tall headless screenshot shows the whole page (used for design review) |

Regenerating the compressed art (source images stay where they were):
the prep script lives in the session scratchpad; it is 30 lines of PIL —
resize zone paintings to 900w JPEG q74, key art to 1400w q82.

Release-asset contract grew by one OPTIONAL name: publishing
`Giltgrave-Setup-GPU.exe` alongside `Giltgrave-Setup.exe` makes the GPU
button real; until then it falls back to the standard installer.
