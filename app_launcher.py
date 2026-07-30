"""Everspire launcher — starts the backend and opens the game window.

Runs in two modes from one file:

  • SOURCE (dev, `python app_launcher.py`) — git-pulls, rebuilds the frontend,
    and starts uvicorn as a subprocess out of backend/venv.
  • FROZEN (the packaged build a player downloads) — does none of that. There
    is no git checkout, no Node, and no venv on a player's machine, so the
    backend is imported and run IN-PROCESS inside this exe instead.

The packaged layout deliberately keeps game content OUTSIDE the PyInstaller
bundle, sitting next to the exe:

    Everspire/
      Everspire.exe        <- this script, frozen
      _internal/           <- PyInstaller runtime + deps (replaced on update)
      backend/             <- game code, static art, AND saves/  (kept on update)
      frontend/dist/       <- built UI

That split is the whole reason updating is safe: a new build replaces the exe
and _internal/ while backend/saves/ and the player's generated portraits stay
put. Bundling backend/ into the exe would wipe a roster on every patch.
"""

import sys
import os
import subprocess
import threading
import time
import multiprocessing
import ctypes
import urllib.request

IS_FROZEN = getattr(sys, "frozen", False)

HOST = "127.0.0.1"
PORT = 8000
# localhost (not 127.0.0.1) because backend/main.py's origin allowlist and the
# webview's localStorage partition are both keyed on this exact string.
URL = f"http://localhost:{PORT}"

# Something about this frozen build launches this script's process a second
# time on Windows (observed: backend AND ComfyUI both starting twice, with
# the second of each pair failing to bind its port and being left as an
# orphaned process the cleanup in __main__ never tracks or kills). A
# port-in-use check isn't reliable here — both copies were launching within
# the same second, well before uvicorn/ComfyUI actually finish binding —
# so this uses a Windows named mutex instead: CreateMutex is atomic across
# processes (no race window), and the OS auto-releases it if this process
# exits or crashes, so there's no stale-lock-file cleanup to get wrong.
_SINGLE_INSTANCE_MUTEX_NAME = "Everspire_SingleInstanceMutex"
ERROR_ALREADY_EXISTS = 183


def _acquire_single_instance_lock() -> bool:
    if os.name != 'nt':
        return True
    # ctypes.windll.kernel32.GetLastError() is unreliable here — ctypes can
    # make other internal Win32 calls between CreateMutexW and reading the
    # error code, clobbering it before you see it. use_last_error=True +
    # ctypes.get_last_error() is the documented-correct way to read the
    # real result of the immediately-preceding call. (Confirmed this
    # mattered: the windll.kernel32.GetLastError() version never detected
    # the second instance — both launches always proceeded.)
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    handle = kernel32.CreateMutexW(None, True, _SINGLE_INSTANCE_MUTEX_NAME)
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        return False
    globals()['_mutex_handle'] = handle  # keep a reference alive for the process lifetime
    return True


def get_base_dir():
    """Return the game root (the dir holding backend/ and frontend/).

    Frozen: the exe sits IN that root, but tolerate it living in a dist/
    subfolder too, which is where a local `pyinstaller` run drops it.
    """
    if IS_FROZEN:
        exe_dir = os.path.dirname(sys.executable)
        for candidate in (exe_dir, os.path.dirname(exe_dir)):
            if os.path.isdir(os.path.join(candidate, "backend")):
                return candidate
        return exe_dir
    return os.path.dirname(os.path.abspath(__file__))


def resource_path(*parts):
    """Locate a bundled asset in both frozen and source runs.

    PyInstaller unpacks `datas` into _internal/ (onedir) or a temp dir
    (onefile), neither of which is where the game root is, so get_base_dir()
    can't find them.
    """
    meipass = getattr(sys, '_MEIPASS', None)
    if meipass:
        candidate = os.path.join(meipass, *parts)
        if os.path.exists(candidate):
            return candidate
    return os.path.join(get_base_dir(), *parts)


# NOTE: do NOT SetCurrentProcessExplicitAppUserModelID here. Tried it —
# existing taskbar pins carry no AUMID, so they keep the exe-path identity
# while the running window gets the explicit one, and Windows shows TWO
# taskbar buttons for the same app (stale-icon pin + live window). Path-based
# identity groups pin and window correctly on its own for a single-exe app.


# ─── dev-only pre-flight (skipped entirely in the packaged build) ───────────

def update_codebase():
    """Pull the latest changes from git so the exe is always fully up to date."""
    base_dir = get_base_dir()
    if os.path.isdir(os.path.join(base_dir, ".git")):
        print("Checking for updates via git pull...")
        try:
            result = subprocess.run(
                ["git", "pull"],
                cwd=base_dir,
                capture_output=True, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            if result.returncode == 0:
                print("Codebase is up to date.")
            else:
                print(f"Git pull warning: {result.stderr}")
        except FileNotFoundError:
            print("Git not found — skipping auto-update.")


def build_frontend():
    """Auto-rebuild the React frontend before launch so code changes are
    always picked up without manually running npm commands."""
    base_dir = get_base_dir()
    frontend_dir = os.path.join(base_dir, "frontend")
    if not os.path.isdir(frontend_dir):
        print("Frontend directory not found — skipping build.")
        return
    # Find npm: try PATH first, then common Node install locations
    npm_candidates = ["npm", r"C:\Program Files\nodejs\npm.cmd", r"C:\Program Files (x86)\nodejs\npm.cmd"]
    npm_cmd = None
    for candidate in npm_candidates:
        try:
            subprocess.run([candidate, "--version"], capture_output=True, check=True,
                           creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            npm_cmd = candidate
            break
        except (FileNotFoundError, subprocess.CalledProcessError):
            continue
    if not npm_cmd:
        print("npm not found — skipping frontend build.")
        return
    print("Building frontend...")
    result = subprocess.run(
        [npm_cmd, "run", "build"],
        cwd=frontend_dir,
        capture_output=True, text=True,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    )
    if result.returncode == 0:
        print("Frontend built successfully.")
    else:
        print(f"Frontend build warning: {result.stderr[-500:] if result.stderr else 'unknown error'}")


# ─── backend startup ────────────────────────────────────────────────────────
#
# ComfyUI is deliberately NOT launched from here any more. The backend already
# does it properly on startup (services.comfy_service.ensure_comfy_running),
# which honours COMFYUI_DIR — the env var INSTALL_GENERATION.bat sets — and
# falls back to ~/ComfyUI and the portable layout. The old hardcoded
# C:\Users\liamh\ComfyUI path here only ever worked on the dev machine.

def _enter_backend_dir():
    """chdir + sys.path into backend/. Both are required: the backend reads
    relative paths ("saves", "static/portraits") throughout, and uvicorn needs
    to import "main" by name."""
    backend_dir = os.path.join(get_base_dir(), "backend")
    if not os.path.isdir(backend_dir):
        raise SystemExit(
            f"Game files not found — expected a 'backend' folder next to the exe.\n"
            f"Looked in: {get_base_dir()}\n\n"
            f"If you downloaded a zip, make sure you EXTRACTED it before running."
        )
    os.chdir(backend_dir)
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)
    return backend_dir


def start_backend_inprocess():
    """Frozen mode: run uvicorn on a daemon thread inside this process.

    There is no backend/venv on a player's machine, so there's nothing to
    spawn — the deps are frozen into this exe. uvicorn handles being started
    off the main thread on its own (capture_signals() no-ops when it isn't
    the main thread), so the window still owns the main thread.
    """
    _enter_backend_dir()
    import uvicorn
    config = uvicorn.Config("main:app", host=HOST, port=PORT, log_level="warning")
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, daemon=True, name="everspire-backend").start()
    return server


def start_backend_subprocess():
    """Source mode: the dev venv has the deps and reload-friendly tooling."""
    base_dir = get_base_dir()
    backend_dir = os.path.join(base_dir, "backend")
    python_exe = os.path.join(backend_dir, "venv", "Scripts", "python.exe")
    if not os.path.exists(python_exe):
        python_exe = sys.executable
    print("Starting backend...")
    # Run uvicorn without --reload so it doesn't spawn child processes that get orphaned
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    return subprocess.Popen(
        [python_exe, "-m", "uvicorn", "main:app", "--host", HOST, "--port", str(PORT)],
        cwd=backend_dir,
        creationflags=creationflags
    )


def wait_for_backend(timeout=180):
    """Poll until the API answers.

    The old code slept a flat 5 seconds, which was a guess in both directions:
    too long on a warm start, and far too short on a first run, where startup
    seeds the default portrait pool and reconciles the cache before uvicorn
    serves anything. A blank window was the failure mode. Polling removes the
    guess. The timeout is generous because that first-run seed is disk-bound
    and a player's machine may be much slower than the dev box.
    """
    deadline = time.time() + timeout
    probe = f"http://{HOST}:{PORT}/settings/generation"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(probe, timeout=2) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.4)
    return False


def open_window(icon_path):
    """Native window, falling back to the default browser.

    pywebview needs the Edge WebView2 runtime. It's preinstalled on Win11 and
    current Win10, but a missing/broken runtime should degrade to a browser
    tab rather than a silent no-launch.
    """
    try:
        import webview
    except Exception as e:
        print(f"Window backend unavailable ({e}) — opening in your browser.")
        return False

    try:
        # zoomable=True lets Ctrl+scroll / Ctrl+-/+ shrink or grow the page
        # content within the same window size — the practical way to "see
        # everything" without going fullscreen, since the window is already
        # resizable by default.
        webview.create_window('Everspire', URL, width=1280, height=800, zoomable=True)
        # private_mode defaults to True in pywebview, which runs an ephemeral
        # browser profile — localStorage (sound settings, etc.) silently
        # resets every launch. A persistent storage_path next to the exe
        # fixes that.
        storage_path = os.path.join(get_base_dir(), "webview_data")
        os.makedirs(storage_path, exist_ok=True)
        webview.start(private_mode=False, storage_path=storage_path, icon=icon_path)
        return True
    except Exception as e:
        print(f"Could not open the game window ({e}) — opening in your browser.")
        return False


if __name__ == "__main__":
    multiprocessing.freeze_support()

    if not _acquire_single_instance_lock():
        print("Another instance of Everspire is already running. Exiting.")
        sys.exit(0)

    print("Launching Everspire...")

    backend_process = None
    try:
        if IS_FROZEN:
            start_backend_inprocess()
        else:
            update_codebase()   # auto-update from git
            build_frontend()    # auto-rebuild frontend on every launch
            backend_process = start_backend_subprocess()

        print("Waiting for the game server...")
        if not wait_for_backend():
            print("The game server didn't start in time.")
            if IS_FROZEN:
                # Frozen builds have no console attached, so a bare print is
                # invisible — say it in a place the player will actually see.
                ctypes.windll.user32.MessageBoxW(
                    None,
                    "Everspire's game server didn't start in time.\n\n"
                    "If this keeps happening, check that no other copy is "
                    "running and that port 8000 is free.",
                    "Everspire", 0x10,
                )
            raise SystemExit(1)

        # Pass the icon explicitly. pywebview's docs claim `icon` is GTK/QT
        # only, but the WinForms backend does honour it — and without it that
        # backend falls back to ExtractIconW(exe, 0), which hands back a SINGLE
        # size that Windows then rescales for the taskbar. The .ico carries
        # 16-256, so letting the OS pick keeps every context crisp.
        icon_path = resource_path("assets", "icon.ico")
        if not os.path.isfile(icon_path):
            print(f"Window icon missing at {icon_path}; falling back to exe icon.")
            icon_path = None

        if not open_window(icon_path):
            import webbrowser
            webbrowser.open(URL)
            print(f"Everspire is running at {URL} — close this window to stop it.")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass

    finally:
        # Guarantee cleanup even if webview crashes.
        #
        # .terminate() only kills the PID we directly spawned. On this
        # machine, the venv's Scripts\python.exe is itself a thin stub that
        # immediately launches the real interpreter as a CHILD process —
        # confirmed by checking which PID actually held port 8000/8188: it
        # was never the one Popen() returned. .terminate() was killing the
        # stub and leaving the real uvicorn process running untracked in the
        # background, accumulating across every launch. taskkill /T kills the
        # whole descendant tree, not just one PID.
        #
        # The frozen path needs no taskkill for the backend — it's a daemon
        # thread in THIS process and dies with it. But ComfyUI is a real
        # subprocess either way, and left alone it sits on ~7GB of VRAM after
        # the window closes, which for this audience is exactly the memory
        # the game they open next wants. Ask the backend to stop the one IT
        # started (a ComfyUI the player launched themselves is left alone).
        if IS_FROZEN:
            try:
                from services.comfy_service import shutdown_comfy
                shutdown_comfy()
            except Exception:
                pass

        if backend_process is not None:
            print("Cleaning up background processes...")
            try:
                subprocess.run(
                    ["taskkill", "/T", "/F", "/PID", str(backend_process.pid)],
                    capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW,
                )
            except Exception as e:
                print(f"Failed to fully clean up backend (pid {backend_process.pid}): {e}")

        print("Shutdown complete.")
