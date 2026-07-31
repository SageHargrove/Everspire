@echo off
setlocal
REM ─── Everspire — personal hero generation installer ─────────────────────
REM Sets up local AI generation so YOUR summons get unique, never-before-
REM seen heroes instead of the shared base gallery.
REM
REM Requirements: an NVIDIA GPU (8GB+ VRAM recommended) and ~12GB free disk.
REM Downloads: ComfyUI portable (~1.5GB), the art model (~7GB), the game's
REM style models (~450MB). Resume-safe — rerun if interrupted.
REM After it finishes: launch the game with PLAY.bat and turn ON
REM "Hero Portrait Generation" under Settings -> AI.

where nvidia-smi >nul 2>nul
if errorlevel 1 (
    echo.
    echo   No NVIDIA GPU detected ^(nvidia-smi not found^).
    echo   Local generation needs an NVIDIA card — the game itself still
    echo   works fine with the built-in art. Nothing was installed.
    pause
    exit /b 1
)

set "GEN_DIR=%USERPROFILE%\ToE-Generation"
set "PORTABLE=%GEN_DIR%\ComfyUI_windows_portable"
set "COMFY=%PORTABLE%\ComfyUI"
mkdir "%GEN_DIR%" 2>nul
cd /d "%GEN_DIR%"

if exist "%COMFY%\main.py" goto models
echo [1/4] Downloading ComfyUI portable (~1.5GB)...
curl -L -C - -o ComfyUI_windows_portable_nvidia.7z "https://github.com/comfyanonymous/ComfyUI/releases/latest/download/ComfyUI_windows_portable_nvidia.7z" || goto fail
echo       Extracting...
if not exist 7zr.exe curl -L -o 7zr.exe "https://7-zip.org/a/7zr.exe" || goto fail
7zr.exe x -y ComfyUI_windows_portable_nvidia.7z >nul || goto fail
del ComfyUI_windows_portable_nvidia.7z 2>nul

:models
echo [2/4] Downloading the art model (~7GB — grab a coffee)...
curl -L -C - -o "%COMFY%\models\checkpoints\noobaiXLNAIXL_vPred10Version.safetensors" "https://huggingface.co/Laxhar/noobai-XL-Vpred-1.0/resolve/main/NoobAI-XL-Vpred-v1.0.safetensors" || goto fail

echo [3/5] Downloading the Everspire style models (~450MB)...
curl -L -C - -o "%COMFY%\models\loras\ToE_Heroes_Main.safetensors" "https://media.githubusercontent.com/media/SageHargrove/Everspire/main/generation/loras/ToE_Heroes_Main.safetensors" || goto fail
curl -L -C - -o "%COMFY%\models\loras\AddMicroDetails_NoobAI_v5.safetensors" "https://media.githubusercontent.com/media/SageHargrove/Everspire/main/generation/loras/AddMicroDetails_NoobAI_v5.safetensors" || goto fail

echo [4/5] Installing the content-aware cutout node (transparent hero art)...
if not exist "%COMFY%\custom_nodes\toe_rembg" mkdir "%COMFY%\custom_nodes\toe_rembg"
copy /Y "%~dp0generation\comfy_nodes\toe_rembg\__init__.py" "%COMFY%\custom_nodes\toe_rembg\__init__.py" >nul
"%PORTABLE%\python_embeded\python.exe" -m pip install rembg onnxruntime >nul 2>&1

echo [5/5] Registering with the game...
setx COMFYUI_DIR "%COMFY%" >nul

echo.
echo   ✔ Done. Start the game with PLAY.bat, then turn ON "Hero Portrait
echo     Generation" under Settings -^> AI. The generator starts with the
echo     game automatically from now on.
pause
exit /b 0

:fail
echo.
echo   A download failed — check your connection and rerun this installer.
echo   It resumes where it left off.
pause
exit /b 1
