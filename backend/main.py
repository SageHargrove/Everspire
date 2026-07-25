from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
import os
import threading
import time

env_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(env_path)

from database import init_db, db
from routers import heroes, gacha, tower, base, runs, equipment, profiles, chat, relics, crafting, arena, achievements, raid, herald
from routers import settings as settings_router

init_db()

app = FastAPI(title="Tower of Eternity Backend")

# ─── drive-by request guard (local single-player backend) ─────────────
#
# This backend has no login by design: it's the player's own machine and
# owns only their local save. But it listens on localhost while an ordinary
# browser is running, and CORS does NOT stop a hostile page from SENDING a
# cross-origin POST — it only stops that page from READING the response. So
# any site the player visits could fire state-changing requests at
# http://localhost:8000 (dismiss heroes, spend gold, wipe a roster) purely
# blind. Nothing in CORS prevents that.
#
# Fix: reject requests carrying an Origin/Referer that isn't ours. Browsers
# always attach Origin to cross-origin POSTs and cannot forge it, while the
# game's own webview and the Vite dev server both present allowed origins.
# Non-browser callers (the game client itself, curl, tests) send no Origin
# and are unaffected.
_ALLOWED_LOCAL_ORIGINS = {
    "http://localhost:8000", "http://127.0.0.1:8000",
    "http://localhost:5173", "http://127.0.0.1:5173",
}


@app.middleware("http")
async def _block_foreign_origins(request, call_next):
    from fastapi.responses import JSONResponse
    origin = request.headers.get("origin")
    if origin and origin not in _ALLOWED_LOCAL_ORIGINS:
        return JSONResponse(
            {"detail": "Cross-origin requests are not allowed against the local game backend."},
            status_code=403,
        )
    # A cross-site form/navigation POST can omit Origin in some browsers but
    # still carries a foreign Referer — treat that the same way.
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        referer = request.headers.get("referer")
        if referer and not any(referer.startswith(o) for o in _ALLOWED_LOCAL_ORIGINS):
            return JSONResponse(
                {"detail": "Cross-origin requests are not allowed against the local game backend."},
                status_code=403,
            )
    return await call_next(request)


app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(_ALLOWED_LOCAL_ORIGINS),
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs("static/portraits", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

def _reconcile_loop():
    """reconcile_pending_profiles() only ran once, at startup — a hero whose
    LLM enrichment thread dies mid-flight *after* that point (a transient
    Gemini outage, rate limit, etc.) was stuck on a placeholder identity for
    the rest of the session with nothing to retry it. Re-run the same scan
    periodically instead so it self-heals without needing a backend restart."""
    from routers.gacha import reconcile_pending_profiles
    while True:
        time.sleep(300)
        try:
            reconcile_pending_profiles()
        except Exception as e:
            print(f"[Reconcile] Periodic profile reconciliation failed: {e}")

@app.on_event("startup")
async def startup():
    init_db()
    from services.portrait_cache import cleanup_portraits, start_cache_worker, reconcile_pending_portraits, queue_missing_enemy_portraits, queue_missing_boss_portraits, queue_missing_family_portraits, maybe_reset_portrait_pipeline, seed_default_pool
    maybe_reset_portrait_pipeline()  # full-body pipeline bump — wipe old bust portraits before reconcile re-queues them
    cleanup_portraits()
    seed_default_pool()  # confirmed_heroes double as the default portrait pool
    start_cache_worker()
    reconcile_pending_portraits()
    queue_missing_enemy_portraits()
    queue_missing_boss_portraits()
    queue_missing_family_portraits()
    from services.chat_service import start_chat_worker
    start_chat_worker()
    from routers.gacha import reconcile_pending_profiles
    reconcile_pending_profiles()
    threading.Thread(target=_reconcile_loop, daemon=True).start()
    # Launch-everything UX: if the player has image generation turned on and a
    # local ComfyUI install exists, bring the generator up with the game so
    # portraits Just Work. Off / no install = bundled-art mode.
    def _gen_boot():
        try:
            from routers.settings import get_image_generation_enabled
            if get_image_generation_enabled():
                from services.comfy_service import ensure_comfy_running
                ensure_comfy_running()
        except Exception as e:
            print(f"[Gen] boot check skipped: {e}")
    threading.Thread(target=_gen_boot, daemon=True).start()
    print("Portrait and Chat workers started.")


app.include_router(heroes.router, prefix="/heroes", tags=["heroes"])
app.include_router(gacha.router, prefix="/gacha", tags=["gacha"])
app.include_router(tower.router, prefix="/tower", tags=["Tower"])
app.include_router(base.router, prefix="/base", tags=["Base"])
app.include_router(settings_router.router, prefix="/settings", tags=["Settings"])
app.include_router(runs.router, prefix="/runs", tags=["Runs"])
app.include_router(equipment.router, prefix="/equipment", tags=["Equipment"])
app.include_router(relics.router, prefix="/relics", tags=["Relics"])
app.include_router(profiles.router, prefix="/profiles", tags=["Profiles"])
app.include_router(chat.router, prefix="/chat", tags=["Chat"])
app.include_router(crafting.router, prefix="/forge", tags=["Forge"])
app.include_router(arena.router, prefix="/arena", tags=["Arena"])
app.include_router(achievements.router, prefix="/achievements", tags=["Achievements"])
app.include_router(raid.router, prefix="/raid", tags=["Raid"])
app.include_router(herald.router, prefix="/herald", tags=["Herald"])


@app.get("/portrait-cache/status")
def cache_status():
    from services.portrait_cache import get_cache_counts
    counts = get_cache_counts()
    total = sum(counts.values())
    return {"counts_by_star": counts, "total_available": total}

@app.post("/portrait-cache/cleanup")
def cache_cleanup():
    """Manually trigger portrait cleanup — removes orphaned files and clears cache pool."""
    from services.portrait_cache import cleanup_portraits
    cleanup_portraits()
    seed_default_pool()  # confirmed_heroes double as the default portrait pool
    return {"ok": True, "message": "Portrait cache cleaned. Orphaned files removed. Cache worker will regenerate fresh portraits."}

@app.post("/portrait-cache/regenerate")
def cache_regenerate():
    """Delete ALL cached portraits (not hero-owned) and regenerate from scratch with new diverse prompts."""
    import os, json
    from services.portrait_cache import cleanup_portraits, get_cache_counts

    portrait_dir = "static/portraits"
    with db() as conn:
        # Get hero-owned portrait filenames
        rows = conn.execute("SELECT portrait_path FROM heroes WHERE portrait_path IS NOT NULL").fetchall()
        owned = {os.path.basename(r["portrait_path"]) for r in rows}
        # Clear entire cache pool
        conn.execute("DELETE FROM portrait_cache")

    # Delete all non-owned portrait files in subdirectories
    deleted = 0
    for subdir in ["main", "cached"]:
        dir_path = os.path.join(portrait_dir, subdir)
        if os.path.isdir(dir_path):
            for fname in os.listdir(dir_path):
                if fname.endswith(".png") and fname not in owned and not fname.startswith("default_"):
                    try:
                        os.remove(os.path.join(dir_path, fname))
                        deleted += 1
                    except Exception:
                        pass

    return {
        "ok": True,
        "deleted": deleted,
        "kept_hero_portraits": len(owned),
        "message": f"Deleted {deleted} cached portraits. Cache worker will regenerate with new diversity system."
    }

frontend_dist = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "dist")
if os.path.exists(os.path.join(frontend_dist, "assets")):
    app.mount("/assets", StaticFiles(directory=os.path.join(frontend_dist, "assets")), name="assets")

@app.get("/{catchall:path}")
def serve_react_app(catchall: str):
    file_path = os.path.join(frontend_dist, catchall)
    if catchall and os.path.exists(file_path) and os.path.isfile(file_path):
        return FileResponse(file_path)
    index_path = os.path.join(frontend_dist, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path, headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache", "Expires": "0"})
    return {"error": "Frontend not built. Run 'npm run build' in frontend directory."}
