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
| `GET /download` | 302 → `github.com/SageHargrove/Everspire/releases/latest` |
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
(`/repos/SageHargrove/Everspire/releases` returns `[]`), so the button lands on
an empty releases page. Publish a build first, or accept that it's a
placeholder until then:

```bash
python tools/make_release.py          # stages release/Everspire + zip + setup exe
gh release create v0.1.0-playtest release/Everspire-playtest.zip release/Everspire-Setup.exe
```

## Left for the real frontend pass

The page is deliberately plain — structure and working links, no art direction.
Whoever does the visual pass gets:

- No external requests. Fonts are system serif, styles are inline, no CDN.
  Keep it that way; the page is served by the game's API container.
- Screenshots are the obvious missing element. Parallax cards photograph well
  and are already built.
- Copy currently leads on permadeath, the tower, hero egos, and the base, with
  API key + GPU generation framed as strictly optional.
