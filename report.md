================================================================
1) adventure_setup.py — functions, one line each (focus: launch, prepare_environment)
================================================================

Module constants (not functions):
- PYTHON_VERSION = "3.12.14"                              (adventure_setup.py:17)
- PILLOW_VERSION = "12.3.0"                               (adventure_setup.py:18)
- OWNER = {"format": "ultra-project-setup-owned", "version": 1}        (adventure_setup.py:19)
- ENV_OWNER = {"format": "ultra-project-environment-owned", "version": 1} (adventure_setup.py:20)
- HANDOFF = "ULTRA_MANAGED_INTERPRETER_HANDOFF"          (adventure_setup.py:21)
- EXPECTED = {runtime: (cpython-3.12.14+20260814-x86_64-pc-windows-msvc-install_only.tar.gz, 46097715, sha256, url),
              pillow: (pillow-12.3.0-cp312-cp312-win_amd64.whl, 7227137, sha256, url)}   (adventure_setup.py:22-29)
- PROBE (interpreter env probe via `python -I -B -c`)   (adventure_setup.py:30-39)
- TK_PROBE (Tk window creation probe)                   (adventure_setup.py:40-51)

Functions:
- SetupError.__init__ (adventure_setup.py:53) — stores code+message, subclasses RuntimeError.
- elevated() (adventure_setup.py:58) — True iff sys.platform == "win32" and windll admin check.
- checked_path(root, path, *, allow_root=False) (adventure_setup.py:61) — rejects symlink/junction/path escape.
- read_json(path, *, limit=262144) (adventure_setup.py:84) — bounded JSON read.
- atomic_json(root, path, value) (adventure_setup.py:94) — atomic write via .partial-<uuid> + fsync + os.replace.
- owned_folder(root, name) (adventure_setup.py:108) — creates folder + owner.json marker; UNOWNED_SETUP_FOLDER if mismatch.
- load_lock(root) (adventure_setup.py:119) — validates runtime-lock.json contents (format/version/platform/pillow/version/hashes).
- project_lock(root, name) contextmanager (adventure_setup.py:132) — msvcrt/flock lock on .setup/<name>.
- check_idle(root, *names) (adventure_setup.py:164) — acquires named locks.
- _SetupJob class (adventure_setup.py:169) — Win32 job object process cleanup.
- run_trusted(arguments, *, cwd, timeout=180) (adventure_setup.py:229) — spawns verified child process with pipes.
- inspect_python(executable, root, *, require_pillow=False) (adventure_setup.py:268) — runs PROBE, validates version/impl/bits/platform/tk/pillow.
- artifact_matches(path, spec) (adventure_setup.py:282) — size + sha256 match check.
- acquire_artifact(root, spec, *, offline, artifact_dir, opener) (adventure_setup.py:292) — download + hash check.
- managed_python(root) (adventure_setup.py:332) — returns <root>/.venv/Scripts/python.exe.
- payload_name(name) (adventure_setup.py:335) — validates supplied payload filename.
- validate_payload(root, lock=None, lock_hash=None) (adventure_setup.py:346) — validates .setup-payload manifest + per-file hashes.
- ensure_environment(root, source_python, *, inspect, runner) (adventure_setup.py:414) — decides recreate; venv --copies; returns managed python.
- BUNDLED_LAUNCHER_FILES (adventure_setup.py:438) — ("python.exe", "pythonw.exe", "python3.dll", "python312.dll", "vcruntime140.dll", "vcruntime140_1.dll").
- direct_bundled_launchers(root, executable, manifest_hash, *, verify_only) (adventure_setup.py:442) — verifies/copies bundled launcher files into .venv/Scripts.
- prepare_environment(root, *, source_python, offline, artifact_dir, prepare_only, inspect, runner, gui_probe, bundled, progress) (adventure_setup.py:494) — full setup pipeline (details below).
- check_ready(root, *, inspect) (adventure_setup.py:549) — validates environment-ready.json and returns managed executable.
- launch(root, *, application, inspect, current_executable, handoff_runner) (adventure_setup.py:578) — entry used by main.py.

Focus — prepare_environment (adventure_setup.py:494-547):
- checked_path(root, allow_root=True) -> owned_folder(.setup) -> project_lock(setup.lock) -> check_idle -> load_lock -> (if bundled: validate_payload, require source == supplied python.exe else BUNDLED_RUNTIME_REQUIRED) -> inspect source -> ensure_environment -> direct_bundled_launchers (if bundled) -> inspect managed python -> pillow check (acquire/install) -> final inspect(require_pillow=True) -> build result dict -> Tk gui probe (or gui_probe) -> TK_WINDOW_FAILED if no window -> write environment-ready.json -> return result.

Focus — launch (adventure_setup.py:578-596):
- check_ready(root, inspect=inspect_python) -> interpreter handoff via subprocess (or INTERPRETER_HANDOFF via HANDOFF env) -> with project_lock(root, "workbench.lock"): check_idle -> import src.workbench.gui main -> return application(root).

================================================================
2) Windows-specific places (exact line, quote, file:line)
================================================================

adventure_setup.py:
- adventure_setup.py:22-29 — EXPECTED runtime entry: "cpython-3.12.14+20260814-x86_64-pc-windows-msvc-install_only.tar.gz" and pillow entry "pillow-12.3.0-cp312-cp312-win_amd64.whl"; load_lock at :124 requires lock["platform"] == "win_amd64".
- adventure_setup.py:31 — PROBE: `elevated=bool(ctypes.windll.shell32.IsUserAnAdmin()) if sys.platform=='win32' else False)`.
- adventure_setup.py:59 — `return sys.platform == "win32" and bool(ctypes.windll.shell32.IsUserAnAdmin())`.
- adventure_setup.py:143-145 and :156-158 — `if os.name == "nt": import msvcrt; msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)`.
- adventure_setup.py:172, :187-225 — _SetupJob: `from ctypes import wintypes as wt`; `self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)`; CreateJobObjectW; flags 0x2000 (JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE); AssignProcessToJobObject; TerminateJobObject; QueryInformationJobObject; CloseHandle.
- adventure_setup.py:230-231 — `options = ({"creationflags": subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True})`.
- adventure_setup.py:241-242 — `if os.name == "nt": job = _SetupJob(process)`.
- adventure_setup.py:256-257 — taskkill: `subprocess.run([str(Path(os.environ["SystemRoot"]) / "System32/taskkill.exe"), "/PID", str(process.pid), "/T", "/F"], ... creationflags=subprocess.CREATE_NO_WINDOW)`.
- adventure_setup.py:276-277 — inspect_python: `observed.get("platform") != "win32"` -> SetupError WRONG_RUNTIME "Adventure needs CPython 3.12.14 for Windows x64 with Tk."
- adventure_setup.py:333 — managed_python: `Path(root) / ".venv" / "Scripts" / "python.exe"`.
- adventure_setup.py:377 — required payload files include "python/python.exe", "python/python312.dll", "python/Lib/venv/__init__.py", "python/Lib/ensurepip/__init__.py", "python/DLLs/_tkinter.pyd", "python/tcl/tk8.6/license.terms", "python/LICENSE.txt", "wheels/" + pillow filename.
- adventure_setup.py:438-439 — BUNDLED_LAUNCHER_FILES = ("python.exe", "pythonw.exe", "python3.dll", "python312.dll", "vcruntime140.dll", "vcruntime140_1.dll").
- adventure_setup.py:471 — `target = checked_path(root, environment / "Scripts" / name)`.
- adventure_setup.py:474 — SETUP_REQUIRED "Adventure's local interpreter changed."
- adventure_setup.py:510-513 — supplied python.exe normcase compare -> SetupError BUNDLED_RUNTIME_REQUIRED.
- adventure_setup.py:528 and :565 — interpreter string ".venv/Scripts/python.exe".

src/workbench/gui.py:
- gui.py:57 — `if sys.platform=='win32:` ; gui.py:59 — `import ctypes` / `self.gesture_seconds=max(.2,min(1.0,ctypes.windll.user32.GetDoubleClickTime()/1000))`.

src/workbench/process.py:
- process.py:203-204 — `options = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True})`.

src/workbench/__main__.py:
- __main__.py:9 — `import platform`; :40 — `(current.exists() and current.lstat().st_file_attributes & 1024 if os.name == "nt" else False)`; :79 — `supported = platform.python_implementation() == "CPython" and platform.python_version() == "3.12.14"`.

src/workbench/runtime_files.py:
- runtime_files.py:87-89 — GUI_RUNTIME_FILES includes "setup_windows.ps1", "SETUP.cmd", "START.cmd".

src/renderer/expedition/display.py (imported by gui.py):
- display.py:1 — docstring "GUI-only Windows awareness and measured display data".
- display.py:6-14 — class WindowsDisplay: `import ctypes` / `from ctypes import wintypes`; `self.user = ctypes.WinDLL("user32", use_last_error=True)`; shcore WinDLL.
- display.py:98 — `if (platform_name or sys.platform) != "win32": return result`.
- display.py:100 — `api = api or WindowsDisplay()`.
- display.py:122-123 — `if sys.platform == "win32": try: result.update(WindowsDisplay().measurements(root))`.

src/framework/source_support.py (imported via process.py):
- source_support.py:52-55 — `if os.name == "nt": subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], ...)`.

Setup/runtime integrity (Windows-flavored) checks:
- adventure_setup.py:346-412 (validate_payload) — required set includes "python/python.exe", "python/python312.dll", "python/Lib/venv/__init__.py", "python/Lib/ensurepip/__init__.py", "python/DLLs/_tkinter.pyd", "python/tcl/tk8.6/license.terms", "python/LICENSE.txt", "wheels/"+pillow filename; per-file artifact_matches sha256; wheel identity :396-398; walk :399-409.
- adventure_setup.py:442-491 (direct_bundled_launchers) — per-file sha256 vs manifest rows (:469-470); copy via .partial- + os.replace (:477-487); final verify (:488-489); SETUP_REQUIRED (:474).
- adventure_setup.py:19,20,108-117,414-436 — ".venv owned" marker: ENV_OWNER, .ultra-environment-owner.json, owned_folder owner.json OWNER.

================================================================
3) main.py flow when run, and which checks can raise SetupError
================================================================

main.py main() (main.py:6-17):
- root = Path(__file__).resolve().parent; sys.path.insert(0, str(root)); from adventure_setup import SetupError, launch.
- if len(sys.argv) != 1 -> print to stderr, return 2.
- try: return launch(root) except SetupError -> print exc.message, return 2. except (OSError, ImportError) -> print, return 2.

launch() flow (adventure_setup.py:578-596) invoked by main:
1. adventure_setup.py:579-580 — root resolve; executable = check_ready(root, inspect=inspect_python).
2. check_ready body (adventure_setup.py:549-576) — checks in order: checked_path; load_lock (UNVERIFIED_ARTIFACT); .setup/owner.json (SETUP_REQUIRED); environment-ready.json marker (SETUP_REQUIRED); data fields incl. interpreter == ".venv/Scripts/python.exe" (SETUP_REQUIRED, PROJECT_MOVED); optional bundled payload block (PAYLOAD_INTEGRITY / SETUP_REQUIRED); managed_python + inspect(require_pillow=True) -> RUNTIME_IDENTITY / WRONG_RUNTIME / GUI_DEPENDENCY.
3. adventure_setup.py:581-582 — current = Path(current_executable or sys.executable).resolve(); normcase compare with executable.
4. adventure_setup.py:583-588 — if differ: HANDOFF in os.environ -> SetupError INTERPRETER_HANDOFF (adventure_setup.py:584); else runner handoff: [str(executable), "-X", "utf8", "-B", str(root / "main.py")] -> return returncode.
5. adventure_setup.py:589-595 — with project_lock(root, "workbench.lock"): check_idle(root, "bootstrap.lock", "setup.lock"); application = from src.workbench.gui import main; return application(root).

Then src/workbench/gui.py:main (gui.py:494-503) -> initialize_display() (src/renderer/expedition/display.py:94) -> tkinter.Tk -> Workbench.build -> root.mainloop().

Checks that can raise SetupError along this main.py path (codes):
- checked_path -> LINKED_PROJECT / PATH_ESCAPE (adventure_setup.py:61-82).
- read_json -> METADATA_LIMIT / METADATA_INVALID (adventure_setup.py:84-92).
- load_lock -> UNVERIFIED_ARTIFACT (adventure_setup.py:119-130).
- owned_folder -> UNOWNED_SETUP_FOLDER (adventure_setup.py:108-117).
- project_lock -> PROJECT_BUSY (adventure_setup.py:132-162).
- _SetupJob/run_trusted -> SETUP_PROCESS_OWNERSHIP / SETUP_CLEANUP / ENVIRONMENT_COMMAND_FAILED / SETUP_TIMEOUT / RUNTIME_UNAVAILABLE (adventure_setup.py:169-266).
- inspect_python -> RUNTIME_IDENTITY / WRONG_RUNTIME / GUI_DEPENDENCY (adventure_setup.py:268-280).
- acquire_artifact -> ARTIFACT_INTEGRITY / OFFLINE_SETUP / DOWNLOAD_FAILED (adventure_setup.py:292-330).
- payload_name/validate_payload -> PAYLOAD_INTEGRITY (adventure_setup.py:335-412).
- ensure_environment -> UNOWNED_ENVIRONMENT (adventure_setup.py:414-436).
- direct_bundled_launchers -> SETUP_REQUIRED / PATH_ESCAPE / PAYLOAD_INTEGRITY (adventure_setup.py:442-491).
- prepare_environment -> SETUP_REQUIRED etc. (adventure_setup.py:494-547).
- check_ready -> SETUP_REQUIRED / PROJECT_MOVED / PAYLOAD_INTEGRITY / SETUP_REQUIRED / RUNTIME_IDENTITY / WRONG_RUNTIME / GUI_DEPENDENCY (adventure_setup.py:549-576).
- launch -> INTERPRETER_HANDOFF (adventure_setup.py:578-596).

================================================================
4) Which of those checks would fail on Linux, and which would be fine
================================================================

Would FAIL on Linux (Windows-gated checks reached during main.py -> launch -> check_ready -> inspect):
- WRONG_RUNTIME (adventure_setup.py:276-277): inspect_python requires observed platform == "win32" (and CPython 3.12.14, 64-bit, Tk 8.6). On Linux the running interpreter reports platform "linux", so check_ready (via :575 inspect during launch) raises SetupError WRONG_RUNTIME.
- BUNDLED_RUNTIME_REQUIRED (adventure_setup.py:512-513): requires source interpreter to equal .setup-payload/python/python.exe (a Windows binary).
- Downstream interpreter expectations: managed_python returns ".venv/Scripts/python.exe" (adventure_setup.py:333); a Linux venv would use bin/python, so handoff/launch of main.py via that path fails on Linux.

Would be FINE on Linux (cross-platform or guarded code):
- checked_path, read_json, atomic_json, owned_folder, load_lock content checks, artifact_matches/acquire_artifact/validate_payload hashing and JSON checks, payload_name.
- project_lock via fcntl branch (adventure_setup.py:143-148 else-branch uses fcntl.flock).
- _SetupJob not instantiated on non-win32 (adventure_setup.py:241-242 guard).
- run_trusted Linux branch (start_new_session / os.killpg SIGKILL; taskkill branch only on nt).
- taskkill only on nt (source_support.py:52-55 else-branch fine).
- GUI startup/display guards: display.py:98 and :122 skip Windows code when sys.platform != "win32".

================================================================
5) Does the GUI itself (gui.py) use anything Windows-only?
================================================================

Yes, but guarded:
- gui.py:57-59 — `if sys.platform=='win32:` ... `import ctypes` ... `ctypes.windll.user32.GetDoubleClickTime()` — the only direct Windows-only API in gui.py, behind a sys.platform == "win32" guard; on other platforms self.gesture_seconds stays 0.5 (gui.py:39).
- gui.py:494-503 (main) — calls initialize_display() from src/renderer/expedition/display.py, then tkinter.Tk, Workbench.build, root.mainloop(). The tkinter widget layer (buttons, labels, text, listbox, ttk, messagebox, webbrowser, after/schedule, bindings) is cross-platform.
- Indirectly, the GUI pulls in Windows-only code via display.py: WindowsDisplay (ctypes.WinDLL "user32"/"shcore", Win32 DPI APIs :6-91), initialize_display guard (:98), inspect_display guard (:122-123), named_fonts ("Segoe UI"/"Consolas", :133).

So: the GUI contains Windows-only usage (ctypes.windll in gui.py:57-59; Win32 display adapter in display.py), but both are behind platform guards / capability checks; the Tk widget code itself is not Windows-only. The setup/launch/runtime layers around the GUI are Windows-only (interpreter, venv Scripts path, taskkill, job objects, win32 probe, platform "win32" identity checks).

================================================================
END OF REPORT
================================================================
