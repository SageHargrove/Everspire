import sys
import os
import subprocess
import time
import multiprocessing
import ctypes
import webview

# Something about this frozen build launches this script's process a second
# time on Windows (observed: backend AND ComfyUI both starting twice, with
# the second of each pair failing to bind its port and being left as an
# orphaned process the cleanup in __main__ never tracks or kills). A
# port-in-use check isn't reliable here — both copies were launching within
# the same second, well before uvicorn/ComfyUI actually finish binding —
# so this uses a Windows named mutex instead: CreateMutex is atomic across
# processes (no race window), and the OS auto-releases it if this process
# exits or crashes, so there's no stale-lock-file cleanup to get wrong.
_SINGLE_INSTANCE_MUTEX_NAME = "InfiniteGacha_SingleInstanceMutex"
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
    """Return the project root regardless of frozen vs source."""
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        # Check if the exe is in tower-gacha/ or tower-gacha/dist/
        if os.path.isdir(os.path.join(exe_dir, "frontend")):
            return exe_dir
        parent_dir = os.path.dirname(exe_dir)
        if os.path.isdir(os.path.join(parent_dir, "frontend")):
            return parent_dir
        return os.path.dirname(parent_dir)
    return os.path.dirname(os.path.abspath(__file__))

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

def start_backend():
    base_dir = get_base_dir()
    backend_dir = os.path.join(base_dir, "backend")
    python_exe = os.path.join(backend_dir, "venv", "Scripts", "python.exe")
    print("Starting backend...")
    # Run uvicorn without --reload so it doesn't spawn child processes that get orphaned
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    return subprocess.Popen(
        [python_exe, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8000"],
        cwd=backend_dir,
        creationflags=creationflags
    )

def start_comfyui():
    comfy_dir = r"C:\Users\liamh\ComfyUI"
    python_exe = os.path.join(comfy_dir, "venv", "Scripts", "python.exe")
    print("Starting ComfyUI...")
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    return subprocess.Popen(
        [python_exe, "main.py"],
        cwd=comfy_dir,
        creationflags=creationflags
    )

if __name__ == "__main__":
    multiprocessing.freeze_support()
    
    if not _acquire_single_instance_lock():
        print("Another instance of Infinite Gacha is already running. Exiting.")
        sys.exit(0)

    print("Launching Infinite Gacha services...")
    update_codebase()  # auto-update from git
    build_frontend()   # auto-rebuild frontend on every launch

    comfy_process = None
    backend_process = None
    try:
        comfy_process = start_comfyui()
        backend_process = start_backend()

        # Wait a moment for servers to spin up
        print("Waiting for servers to start...")
        time.sleep(5)

        # Open native webview window. zoomable=True lets Ctrl+scroll /
        # Ctrl+-/+ shrink or grow the page content within the same window
        # size — the practical way to "see everything" without going
        # fullscreen, since the window is already resizable by default.
        print("Opening application window...")
        webview.create_window('Tower of Eternity', 'http://localhost:8000', width=1280, height=800, zoomable=True)
        # private_mode defaults to True in pywebview, which runs an ephemeral
        # browser profile — localStorage (sound settings, etc.) silently
        # resets every launch. A persistent storage_path next to the exe
        # fixes that.
        storage_path = os.path.join(get_base_dir(), "webview_data")
        os.makedirs(storage_path, exist_ok=True)
        webview.start(private_mode=False, storage_path=storage_path)
        
    finally:
        # Guarantee cleanup even if webview crashes.
        #
        # .terminate() only kills the PID we directly spawned. On this
        # machine, the venv's Scripts\python.exe is itself a thin stub that
        # immediately launches the real interpreter as a CHILD process —
        # confirmed by checking which PID actually held port 8000/8188: it
        # was never the one Popen() returned. .terminate() was killing the
        # stub and leaving the real uvicorn/ComfyUI process running
        # untracked in the background, accumulating across every launch.
        # taskkill /T kills the whole descendant tree, not just one PID.
        print("Cleaning up background processes...")
        for proc, label in ((backend_process, "backend"), (comfy_process, "ComfyUI")):
            if not proc:
                continue
            try:
                subprocess.run(
                    ["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                    capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW,
                )
            except Exception as e:
                print(f"Failed to fully clean up {label} (pid {proc.pid}): {e}")

        print("Shutdown complete.")
