; Giltgrave installer (Inno Setup 6).
;
; Build:
;   backend\venv\Scripts\python -m PyInstaller Giltgrave.spec --noconfirm
;   backend\venv\Scripts\python tools\make_release.py --no-zip
;   "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" tools\everspire.iss
;
; Produces release\Giltgrave-Setup.exe — one file, double-click, play.
;
; PER-USER INSTALL, ON PURPOSE. PrivilegesRequired=lowest puts the game in
; %LOCALAPPDATA%\Programs\Giltgrave, which means:
;   * no UAC prompt, no admin rights, no "ask your IT department"
;   * the install dir is WRITABLE, so backend\saves\ and the portraits the
;     player generates work exactly as they do in the zip build
; A Program Files install would need elevation AND would break both of those,
; since the game keeps player state next to itself.

#define AppName        "Giltgrave"
#define AppVersion     "2026.07.30"
#define AppPublisher   "Liam Holloway"
#define AppExe         "Giltgrave.exe"
#define SrcDir         "..\release\Giltgrave"

[Setup]
; Never change AppId — it's how Windows recognises an upgrade instead of
; installing a second copy alongside the first.
AppId={{8F3A1C74-2E19-4B6D-9A55-7C0E4D8B21F6}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
OutputDir=..\release
OutputBaseFilename=Giltgrave-Setup
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; The payload is ~1GB of already-compressed PNG and OGG. lzma2/max would spend
; a long time to shave off very little; fast gets the real wins (the Python
; runtime, the JS bundle) without the wait.
Compression=lzma2/fast
SolidCompression=yes
; Fewest clicks that still lets someone back out: no directory page, no start
; menu group page. Install -> done -> play.
DisableDirPage=yes
DisableProgramGroupPage=yes
DiskSpanning=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
; webview_data is a WebView2 profile that only exists if someone launched the
; staged build to test it — it must never ship (it carries that session's
; localStorage). make_release.py refuses to zip a dirty stage for the same
; reason; this is the belt to its braces.
Source: "{#SrcDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "webview_data\*,webview_data"

[InstallDelete]
; Wipe the previous PyInstaller runtime before laying down the new one, so an
; upgrade can't leave an orphaned module from the old build shadowing the new.
; Scoped to _internal ONLY — backend\saves\ and the player's generated
; portraits live under {app} too and must survive every upgrade.
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"
Name: "{group}\Set up hero generation (NVIDIA GPU)"; Filename: "{app}\INSTALL_GENERATION.bat"; WorkingDir: "{app}"
Name: "{group}\Read me first"; Filename: "{app}\README_FIRST.txt"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

[Code]
// Uninstall removes everything the installer put down, but NOT the files the
// game created while being played — saves and generated portraits. That's the
// behaviour we want (reinstalling picks a roster back up), but it leaves a
// folder behind, so say so plainly rather than letting someone discover it.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  SavesDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    SavesDir := ExpandConstant('{app}\backend\saves');
    if DirExists(SavesDir) then
      MsgBox('Your Giltgrave saves and generated hero art were kept at:' + #13#10 + #13#10 +
             ExpandConstant('{app}') + #13#10 + #13#10 +
             'Reinstalling will pick them back up. Delete that folder yourself if ' +
             'you want them gone for good.', mbInformation, MB_OK);
  end;
end;
