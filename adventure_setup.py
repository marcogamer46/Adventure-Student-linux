"""Trusted project-local environment setup and launch; never imports student code."""
from __future__ import annotations
import contextlib
import ctypes
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time
import urllib.request
import uuid

PYTHON_VERSION = "3.12.14"
PILLOW_VERSION = "12.3.0"
OWNER = {"format": "ultra-project-setup-owned", "version": 1}
ENV_OWNER = {"format": "ultra-project-environment-owned", "version": 1}
HANDOFF = "ULTRA_MANAGED_INTERPRETER_HANDOFF"
EXPECTED = {
    "runtime": ("cpython-3.12.14+20260814-x86_64-pc-windows-msvc-install_only.tar.gz", 46097715,
        "7330282b47cd43a66b702d39078d2e5a88e580cee351d82f95045f21f5ee042a",
        "https://github.com/astral-sh/python-build-standalone/releases/download/20260814/cpython-3.12.14%2B20260814-x86_64-pc-windows-msvc-install_only.tar.gz"),
    "pillow": ("pillow-12.3.0-cp312-cp312-win_amd64.whl", 7227137,
        "a2b55dd6b2a4c4b7d87ffa56bdb33fdc5fdb9a462173861a7bc097f17d91cb09",
        "https://files.pythonhosted.org/packages/45/89/da2f7971a317f83d807fdd4065c0af40208e59e692cc43d315a71a0e96d1/pillow-12.3.0-cp312-cp312-win_amd64.whl"),
}
PROBE = r"""import json,sys,platform,struct,ctypes,importlib.util
r=dict(version=platform.python_version(),implementation=platform.python_implementation(),bits=struct.calcsize('P')*8,platform=sys.platform,executable=sys.executable,base_prefix=sys.base_prefix,elevated=bool(ctypes.windll.shell32.IsUserAnAdmin()) if sys.platform=='win32' else False)
import tkinter
r['tk_import']=tkinter.TkVersion
r['pillow']=None
if importlib.util.find_spec('PIL') is not None:
 import PIL
 r['pillow']=PIL.__version__
print(json.dumps(r))
"""
TK_PROBE = r"""import json, tkinter as tk
w=tk.Tk()
w.title('Adventure setup check')
w.geometry('420x120')
tk.Label(w,text='Adventure can open its workbench.',padx=20,pady=28).pack()
w.update_idletasks()
w.update()
result=dict(window_created=True,tk=w.tk.call('package','provide','Tk'),tcl=w.tk.call('info','patchlevel'))
w.after(350,w.destroy)
w.mainloop()
print(json.dumps(result))
"""

class SetupError(RuntimeError):
    def __init__(self, code, message):
        self.code, self.message = code, message
        super().__init__(message)

def elevated():
    return sys.platform == "win32" and bool(ctypes.windll.shell32.IsUserAnAdmin())

def checked_path(root, path, *, allow_root=False):
    root = Path(root).absolute()
    path = Path(path).absolute()
    if root.is_symlink() or getattr(root, "is_junction", lambda: False)():
        raise SetupError("LINKED_PROJECT", "Extract Adventure into an ordinary folder, then retry.")
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        raise SetupError("PATH_ESCAPE", "Setup refused a location outside this project.") from None
    if not parts and not allow_root:
        raise SetupError("PATH_ESCAPE", "Setup refused to replace the project folder.")
    current = root
    for part in parts:
        if part in {".", ".."}:
            raise SetupError("PATH_ESCAPE", "Setup refused an unsafe project location.")
        current /= part
        if current.is_symlink() or getattr(current, "is_junction", lambda: False)():
            raise SetupError("LINKED_PROJECT", "Setup found a linked environment folder. Use an ordinary extracted project folder.")
    resolved = path.resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise SetupError("PATH_ESCAPE", "Setup refused a location outside this project.")
    return path

def read_json(path, *, limit=262144):
    with Path(path).open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise SetupError("METADATA_LIMIT", "A setup record is too large. Extract a fresh copy of the provided setup files.")
    try:
        return json.loads(raw)
    except (ValueError, UnicodeError):
        raise SetupError("METADATA_INVALID", "A setup record is damaged. Extract a fresh copy of the provided setup files.") from None

def atomic_json(root, path, value):
    path = checked_path(root, path)
    pending = checked_path(root, path.with_name(path.name + ".partial-" + uuid.uuid4().hex))
    try:
        with pending.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(pending, path)
    finally:
        if pending.exists():
            pending.unlink()

def owned_folder(root, name):
    path = checked_path(root, Path(root) / name)
    marker = path / "owner.json"
    if path.exists():
        if not path.is_dir() or not marker.is_file() or read_json(marker) != OWNER:
            raise SetupError("UNOWNED_SETUP_FOLDER", "Setup found an existing folder it does not own. Ask your instructor to check the project before retrying.")
    else:
        path.mkdir()
        atomic_json(root, marker, OWNER)
    return path

def load_lock(root):
    path = checked_path(root, Path(root) / "runtime-lock.json")
    lock = read_json(path)
    if not isinstance(lock, dict) or lock.get("format") != "ultra-project-runtime-lock" or lock.get("version") != 1:
        raise SetupError("UNVERIFIED_ARTIFACT", "The supplied download verification file is missing or unsupported. Extract the original setup files.")
    if lock.get("python") != PYTHON_VERSION or lock.get("pillow_version") != PILLOW_VERSION or lock.get("platform") != "win_amd64":
        raise SetupError("UNVERIFIED_ARTIFACT", "Setup refuses an unapproved runtime version or platform.")
    for kind, (name, size, digest, url) in EXPECTED.items():
        item = lock.get(kind)
        if not isinstance(item, dict) or any(item.get(k) != v for k, v in zip(("filename", "bytes", "sha256", "url"), (name, size, digest, url))):
            raise SetupError("UNVERIFIED_ARTIFACT", "Setup refuses an unknown download or missing integrity information.")
    return lock, hashlib.sha256(path.read_bytes()).hexdigest()

@contextlib.contextmanager
def project_lock(root, name):
    path = checked_path(root, Path(root) / ".setup" / name)
    stream = path.open("a+b")
    acquired = False
    try:
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except (OSError, PermissionError):
            raise SetupError("PROJECT_BUSY", "Adventure or setup is already using this project. Close the other window, then retry.") from None
        yield
    finally:
        if acquired:
            stream.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        stream.close()

def check_idle(root, *names):
    for name in names:
        with project_lock(root, name):
            pass

class _SetupJob:
    """Own trusted setup descendants; this is process cleanup, not a sandbox."""
    def __init__(self, process):
        from ctypes import wintypes as wt
        class Basic(ctypes.Structure):
            _fields_ = [("process_time", ctypes.c_longlong), ("job_time", ctypes.c_longlong),
                ("flags", wt.DWORD), ("minimum_working_set", ctypes.c_size_t), ("maximum_working_set", ctypes.c_size_t),
                ("active_limit", wt.DWORD), ("affinity", ctypes.c_size_t), ("priority", wt.DWORD), ("scheduling", wt.DWORD)]
        class Counters(ctypes.Structure):
            _fields_ = [(name, ctypes.c_ulonglong) for name in ("read_ops", "write_ops", "other_ops", "read_bytes", "write_bytes", "other_bytes")]
        class Extended(ctypes.Structure):
            _fields_ = [("basic", Basic), ("io", Counters), ("process_memory", ctypes.c_size_t),
                ("job_memory", ctypes.c_size_t), ("peak_process_memory", ctypes.c_size_t), ("peak_job_memory", ctypes.c_size_t)]
        class Accounting(ctypes.Structure):
            _fields_ = [("user", ctypes.c_longlong), ("kernel", ctypes.c_longlong),
                ("period_user", ctypes.c_longlong), ("period_kernel", ctypes.c_longlong),
                ("page_faults", wt.DWORD), ("total", wt.DWORD), ("active", wt.DWORD), ("terminated", wt.DWORD)]
        self.accounting = Accounting
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        declarations = {
            "CreateJobObjectW": ([ctypes.c_void_p, wt.LPCWSTR], wt.HANDLE),
            "SetInformationJobObject": ([wt.HANDLE, ctypes.c_int, ctypes.c_void_p, wt.DWORD], wt.BOOL),
            "AssignProcessToJobObject": ([wt.HANDLE, wt.HANDLE], wt.BOOL),
            "TerminateJobObject": ([wt.HANDLE, wt.UINT], wt.BOOL),
            "QueryInformationJobObject": ([wt.HANDLE, ctypes.c_int, ctypes.c_void_p, wt.DWORD, ctypes.c_void_p], wt.BOOL),
            "CloseHandle": ([wt.HANDLE], wt.BOOL),
        }
        for name, (arguments, returns) in declarations.items():
            function = getattr(self.kernel, name)
            function.argtypes, function.restype = arguments, returns
        self.handle = self.kernel.CreateJobObjectW(None, None)
        limits = Extended()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE; no breakaway flags.
        if (not self.handle or not self.kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits))
                or not self.kernel.AssignProcessToJobObject(self.handle, wt.HANDLE(int(process._handle)))):
            if self.handle:
                self.kernel.CloseHandle(self.handle)
            self.handle = None
            raise SetupError("SETUP_PROCESS_OWNERSHIP", "Setup could not establish safe process cleanup. Close other setup processes and retry normally.")

    def close(self):
        if not self.handle:
            return
        try:
            self.kernel.TerminateJobObject(self.handle, 2)
            deadline = time.monotonic() + 5
            while True:
                count = self.accounting()
                if not self.kernel.QueryInformationJobObject(self.handle, 1, ctypes.byref(count), ctypes.sizeof(count), None):
                    raise SetupError("SETUP_CLEANUP", "Setup could not verify that its processes stopped. Close setup before retrying.")
                if count.active == 0:
                    break
                if time.monotonic() >= deadline:
                    raise SetupError("SETUP_CLEANUP", "Setup processes have not finished stopping. Wait before retrying setup.")
                time.sleep(0.01)
        finally:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def run_trusted(arguments, *, cwd, timeout=180):
    options = ({"creationflags": subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP}
               if os.name == "nt" else {"start_new_session": True})
    process = job = None
    try:
        # Pip's ordinary user/site/global settings must not redirect this
        # project-local install. These changes apply only to owned children.
        child_environment = {key: value for key, value in os.environ.items() if not key.upper().startswith("PIP_")}
        child_environment.update(PIP_CONFIG_FILE=os.devnull, PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1")
        process = subprocess.Popen([str(value) for value in arguments], cwd=cwd, shell=False,
            env=child_environment,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", **options)
        if os.name == "nt":
            job = _SetupJob(process)
        stdout, stderr = process.communicate(timeout=timeout)
        if process.returncode != 0 or len(stdout) + len(stderr) > 262144:
            raise SetupError("ENVIRONMENT_COMMAND_FAILED", "An environment step could not finish. Run SETUP.cmd again; your student files and saved runs are unchanged.")
        return stdout
    except subprocess.TimeoutExpired:
        raise SetupError("SETUP_TIMEOUT", "An environment check took too long. Its setup processes have been stopped; retry SETUP.cmd.") from None
    except OSError:
        raise SetupError("RUNTIME_UNAVAILABLE", "The project interpreter could not start. Retry SETUP.cmd. If Windows blocks execution, ask your institution's IT team to approve it; keep its security policy in place.") from None
    finally:
        if job is not None:
            job.close()
        elif process is not None and process.poll() is None:
            if os.name == "nt":
                subprocess.run([str(Path(os.environ["SystemRoot"]) / "System32/taskkill.exe"), "/PID", str(process.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                import signal
                os.killpg(process.pid, signal.SIGKILL)
        if process is not None:
            process.wait(timeout=5)
            if process.stdout:
                process.stdout.close()
            if process.stderr:
                process.stderr.close()

def inspect_python(executable, root, *, require_pillow=False):
    try:
        observed = json.loads(run_trusted([executable, "-I", "-B", "-c", PROBE], cwd=root, timeout=20))
    except (ValueError, TypeError):
        raise SetupError("RUNTIME_IDENTITY", "The selected interpreter did not return a valid environment identity.") from None
    if not isinstance(observed, dict):
        raise SetupError("RUNTIME_IDENTITY", "The selected interpreter returned malformed environment information.")
    if (observed.get("version") != PYTHON_VERSION or observed.get("implementation") != "CPython"
            or observed.get("bits") != 64 or observed.get("platform") != "win32" or observed.get("tk_import") != 8.6):
        raise SetupError("WRONG_RUNTIME", "Adventure needs CPython 3.12.14 for Windows x64 with Tk. Run SETUP.cmd to prepare the supported environment.")
    if require_pillow and observed.get("pillow") != PILLOW_VERSION:
        raise SetupError("GUI_DEPENDENCY", "Adventure needs Pillow 12.3.0 in its project environment. Run SETUP.cmd to repair it.")
    return observed

def artifact_matches(path, spec):
    path = Path(path)
    if not path.is_file() or path.stat().st_size != spec["bytes"]:
        return False
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest() == spec["sha256"]

def acquire_artifact(root, spec, *, offline=False, artifact_dir=None, opener=None):
    downloads = checked_path(root, Path(root) / ".setup" / "downloads")
    downloads.mkdir(exist_ok=True)
    target = checked_path(root, downloads / spec["filename"])
    if target.exists():
        if artifact_matches(target, spec):
            return target
        rejected = checked_path(root, target.with_name(target.name + ".rejected-" + uuid.uuid4().hex))
        target.rename(rejected)
        raise SetupError("ARTIFACT_INTEGRITY", "A cached download failed its integrity check. Setup kept it aside; retry to obtain a fresh verified copy.")
    supplied = None if artifact_dir is None else Path(artifact_dir) / spec["filename"]
    if supplied is not None and supplied.exists() and not artifact_matches(supplied, spec):
        raise SetupError("ARTIFACT_INTEGRITY", "The supplied setup file does not match the approved download. Ask your instructor for the correct file.")
    if (supplied is None or not supplied.is_file()) and offline:
        raise SetupError("OFFLINE_SETUP", "The required setup file is not available offline. Connect to the internet and retry, or ask your instructor for a recovery option.")
    partial = checked_path(root, target.with_name(target.name + ".partial-" + uuid.uuid4().hex))
    try:
        source = supplied.open("rb") if supplied is not None and supplied.is_file() else (opener or urllib.request.urlopen)(
            urllib.request.Request(spec["url"], headers={"User-Agent": "Adventure-project-setup/037"}), timeout=60)
        size = 0
        with source, partial.open("xb") as stream:
            while chunk := source.read(1024 * 1024):
                size += len(chunk)
                if size > spec["bytes"]:
                    raise SetupError("ARTIFACT_INTEGRITY", "A download exceeded its verified size. Setup did not install it.")
                stream.write(chunk)
            stream.flush()
            os.fsync(stream.fileno())
        if not artifact_matches(partial, spec):
            raise SetupError("ARTIFACT_INTEGRITY", "A download failed its integrity check. Setup did not install it; retry when the connection is stable.")
        os.replace(partial, target)
        return target
    except SetupError:
        raise
    except OSError:
        raise SetupError("DOWNLOAD_FAILED", "Setup could not obtain the required file. Check your connection and folder permissions, then retry.") from None
    finally:
        if partial.exists():
            partial.unlink()

def managed_python(root):
    return checked_path(root, Path(root) / ".venv" / "Scripts" / "python.exe")

def payload_name(name):
    """Canonical Windows-safe relative payload name; no shell interpretation."""
    devices = {"con", "prn", "aux", "nul"} | {f"{p}{n}" for p in ("com", "lpt") for n in "123456789\u00b9\u00b2\u00b3"}
    if not isinstance(name, str) or not name or "\\" in name:
        raise SetupError("PAYLOAD_INTEGRITY", "A supplied setup filename is invalid. Extract the complete original ZIP again.")
    parts = name.split("/")
    if any(not p or p in {".", ".."} or p.endswith((".", " ")) or
           p.split(".")[0].rstrip(" ").casefold() in devices or any(ord(c) < 32 or c in ':<>"|?*' for c in p) for p in parts):
        raise SetupError("PAYLOAD_INTEGRITY", "A supplied setup filename is invalid. Extract the complete original ZIP again.")
    return name

def validate_payload(root, lock=None, lock_hash=None):
    """Check every supplied runtime/wheel byte, including on an existing installation.

    These hashes check local consistency. Publisher provenance is checked by the
    instructor builder against runtime-lock.json, not asserted by this manifest.
    """
    if lock is None:
        lock, lock_hash = load_lock(root)
    payload = checked_path(root, Path(root) / ".setup-payload")
    manifest_path = checked_path(root, payload / "manifest.json")
    message = "The bundled setup files are missing or damaged. Extract the complete original ZIP again; keep your student files and saved runs."
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate payload metadata")
            result[key] = value
        return result
    try:
        with manifest_path.open("rb") as stream:
            raw = stream.read(4 * 1024 * 1024 + 1)
        if len(raw) > 4 * 1024 * 1024:
            raise ValueError("payload metadata limit")
        data = json.loads(raw, object_pairs_hook=unique)
        if (not isinstance(data, dict) or set(data) != {"format", "version", "runtime_lock_sha256", "runtime", "pillow", "files"}
                or data["format"] != "ultra-offline-payload" or type(data["version"]) is not int or data["version"] != 1
                or data["runtime_lock_sha256"] != lock_hash or data["runtime"] != lock["runtime"] or data["pillow"] != lock["pillow"]):
            raise ValueError("payload identity")
        files = data["files"]
        if not isinstance(files, dict) or not 10 <= len(files) <= 6000:
            raise ValueError("payload inventory")
        required = {"python/python.exe", "python/python312.dll", "python/Lib/venv/__init__.py",
                    "python/Lib/ensurepip/__init__.py", "python/DLLs/_tkinter.pyd", "python/tcl/tk8.6/license.terms",
                    "python/LICENSE.txt", "wheels/" + lock["pillow"]["filename"]}
        required.update("python/" + name for name in BUNDLED_LAUNCHER_FILES)
        if not required <= files.keys() or len(files) != len({name.casefold() for name in files}):
            raise ValueError("incomplete payload")
        directories = set()
        for name, row in files.items():
            payload_name(name)
            if (not name.startswith(("python/", "wheels/")) or not isinstance(row, dict)
                    or set(row) != {"bytes", "sha256", "source"} or type(row["bytes"]) is not int or row["bytes"] < 0
                    or not isinstance(row["sha256"], str) or len(row["sha256"]) != 64
                    or any(c not in "0123456789abcdef" for c in row["sha256"])
                    or row["source"] != (name if name.startswith("python/") else lock["pillow"]["filename"])):
                raise ValueError("invalid file record")
            directories.update(p.as_posix() for p in Path(name).parents if p.as_posix() != ".")
            path = checked_path(root, payload / name)
            if not artifact_matches(path, row):
                raise ValueError("changed payload file")
        if files["wheels/" + lock["pillow"]["filename"]] != {
                "bytes": lock["pillow"]["bytes"], "sha256": lock["pillow"]["sha256"], "source": lock["pillow"]["filename"]}:
            raise ValueError("wheel identity")
        actual = set()
        for folder, dirs, names in os.walk(payload):
            for name in dirs:
                path = checked_path(root, Path(folder) / name)
                if path.relative_to(payload).as_posix() not in directories:
                    raise ValueError("unknown payload directory")
            for name in names:
                path = checked_path(root, Path(folder) / name)
                actual.add(path.relative_to(payload).as_posix())
        if actual != set(files) | {"manifest.json"}:
            raise ValueError("unknown or missing payload file")
    except (OSError, ValueError, TypeError, KeyError, UnicodeError):
        raise SetupError("PAYLOAD_INTEGRITY", message) from None
    return hashlib.sha256(raw).hexdigest()

def ensure_environment(root, source_python, *, inspect=inspect_python, runner=run_trusted):
    root = Path(root).resolve()
    environment = checked_path(root, root / ".venv")
    marker = checked_path(root, environment / ".ultra-environment-owner.json")
    recreate = not environment.exists()
    if environment.exists():
        prior = read_json(marker) if marker.is_file() else None
        if not isinstance(prior, dict) or prior.get("owner") != ENV_OWNER:
            raise SetupError("UNOWNED_ENVIRONMENT", "Setup will not replace an environment it did not create. Ask your instructor to check the existing .venv folder.")
        recreate = prior.get("project_root") != str(root)
        if not recreate:
            try:
                inspect(managed_python(root), root)
            except SetupError:
                recreate = True
        if recreate:
            backup = checked_path(root, root / (".venv.previous-" + uuid.uuid4().hex))
            environment.rename(backup)
    if recreate:
        environment.mkdir()
        atomic_json(root, marker, {"owner": ENV_OWNER, "project_root": str(root)})
        runner([source_python, "-I", "-B", "-m", "venv", "--copies", str(environment)], cwd=root)
    return managed_python(root)

BUNDLED_LAUNCHER_FILES = ("python.exe", "pythonw.exe", "python3.dll", "python312.dll",
                         "vcruntime140.dll", "vcruntime140_1.dll")


def direct_bundled_launchers(root, executable, manifest_hash, *, verify_only=False):
    """Keep worker PID identity by replacing only an owned venv's redirectors.

    Windows venv redirectors start another process. The existing controller
    protocol binds replies to Popen.pid, so use exact verified native binaries.
    The venv configuration/site-packages and entire upstream payload stay intact.
    """
    root = Path(root).resolve()
    environment = checked_path(root, root / ".venv")
    marker = checked_path(root, environment / ".ultra-environment-owner.json")
    if (not marker.is_file() or read_json(marker) !=
            {"owner": ENV_OWNER, "project_root": str(root)}):
        raise SetupError("UNOWNED_ENVIRONMENT", "Setup will not replace an environment it did not create. Ask your instructor to check the existing .venv folder.")
    if Path(executable).resolve() != managed_python(root).resolve():
        raise SetupError("PATH_ESCAPE", "Setup refused an interpreter outside its owned environment.")
    source = checked_path(root, root / ".setup-payload/python")
    manifest_path = checked_path(root, root / ".setup-payload/manifest.json")
    with manifest_path.open("rb") as stream:
        raw_manifest = stream.read(4 * 1024 * 1024 + 1)
    if len(raw_manifest) > 4 * 1024 * 1024 or hashlib.sha256(raw_manifest).hexdigest() != manifest_hash:
        raise SetupError("PAYLOAD_INTEGRITY", "The supplied setup manifest changed. Extract the complete original ZIP and retry.")
    files = json.loads(raw_manifest)["files"]
    result = {}
    for name in BUNDLED_LAUNCHER_FILES:
        original = checked_path(root, source / name)
        row = files["python/" + name]
        raw = original.read_bytes()
        if len(raw) != row["bytes"] or hashlib.sha256(raw).hexdigest() != row["sha256"]:
            raise SetupError("PAYLOAD_INTEGRITY", "The supplied interpreter changed. Extract the complete original ZIP and retry.")
        target = checked_path(root, environment / "Scripts" / name)
        if verify_only:
            if not artifact_matches(target, row):
                raise SetupError("SETUP_REQUIRED", "Adventure's local interpreter changed. Run SETUP.cmd to repair it; your student files and saved runs stay in place.")
        else:
            target.parent.mkdir(exist_ok=True)
        if not verify_only and not artifact_matches(target, row):
            pending = checked_path(root, target.with_name(name + ".partial-" + uuid.uuid4().hex))
            try:
                with pending.open("xb") as stream:
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(pending, target)
            finally:
                if pending.exists():
                    pending.unlink()
        if not artifact_matches(checked_path(root, target), row):
            raise SetupError("PAYLOAD_INTEGRITY", "The local interpreter copy could not be verified. Retry SETUP.cmd in a writable folder.")
        result[name] = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    return result


def prepare_environment(root, *, source_python=None, offline=False, artifact_dir=None, prepare_only=False,
                        inspect=inspect_python, runner=run_trusted, gui_probe=None, bundled=False, progress=None):
    root = checked_path(Path(root).absolute(), Path(root).absolute(), allow_root=True).resolve()
    setup = owned_folder(root, ".setup")
    with project_lock(root, "setup.lock"):
        check_idle(root, "bootstrap.lock", "workbench.lock")
        ready = checked_path(root, setup / "environment-ready.json")
        if ready.exists():
            ready.unlink()
        if progress:
            progress("Checking supplied Adventure files")
        lock, lock_hash = load_lock(root)
        bundled = bundled or (root / ".setup-payload").exists()
        payload_hash = None
        if bundled:
            payload_hash = validate_payload(root, lock, lock_hash)
            supplied_python = checked_path(root, root / ".setup-payload/python/python.exe").resolve()
            source_python = Path(source_python or sys.executable).resolve()
            if os.path.normcase(str(source_python)) != os.path.normcase(str(supplied_python)):
                raise SetupError("BUNDLED_RUNTIME_REQUIRED", "Start SETUP.cmd to use Adventure's supplied interpreter. A system Python cannot install this package.")
            offline = True
            artifact_dir = root / ".setup-payload/wheels"
        source_python = Path(source_python or sys.executable).resolve()
        source = inspect(source_python, root)
        if progress:
            progress("Preparing Adventure's local Python environment")
        executable = ensure_environment(root, source_python, inspect=inspect, runner=runner)
        launcher_files = direct_bundled_launchers(root, executable, payload_hash) if bundled else None
        observed = inspect(executable, root)
        if observed.get("pillow") != PILLOW_VERSION:
            wheel = acquire_artifact(root, lock["pillow"], offline=offline, artifact_dir=artifact_dir)
            runner([executable, "-I", "-B", "-m", "pip", "--isolated", "--disable-pip-version-check", "install", "--no-index", "--no-deps", "--force-reinstall", str(wheel)], cwd=root)
        observed = inspect(executable, root, require_pillow=True)
        result = {"format": "ultra-project-environment", "version": 1, "project_root": str(root),
            "lock_sha256": lock_hash, "interpreter": ".venv/Scripts/python.exe", "python": observed,
            "base_interpreter": str(source_python), "ready": False, "student_code_executed": False}
        if payload_hash:
            result["bundled_payload_manifest_sha256"] = payload_hash
            result["direct_bundled_launcher_files"] = launcher_files
        if prepare_only:
            result["status"] = "PREPARED_NEEDS_WINDOW_CHECK"
        else:
            if progress:
                progress("Checking the workbench window")
            if gui_probe is None:
                result["window_check"] = json.loads(runner([executable, "-I", "-B", "-c", TK_PROBE], cwd=root, timeout=20))
            else:
                result["window_check"] = gui_probe(executable, root)
            if result["window_check"].get("window_created") is not True:
                raise SetupError("TK_WINDOW_FAILED", "The graphical window check did not complete. Ask your instructor to check Tk before launching Adventure.")
            result.update(status="READY", ready=True)
            atomic_json(root, ready, result)
        atomic_json(root, setup / "environment-prepared.json", result)
        return result

def check_ready(root, *, inspect=inspect_python):
    root = checked_path(Path(root).absolute(), Path(root).absolute(), allow_root=True).resolve()
    lock, lock_hash = load_lock(root)
    setup = checked_path(root, root / ".setup")
    if not setup.is_dir() or not (setup / "owner.json").is_file() or read_json(setup / "owner.json") != OWNER:
        raise SetupError("SETUP_REQUIRED", "Run SETUP.cmd once, then open main.py or START.cmd.")
    marker = setup / "environment-ready.json"
    if not marker.is_file():
        raise SetupError("SETUP_REQUIRED", "Setup has not completed its graphical check. Run SETUP.cmd, then reopen Adventure.")
    data = read_json(marker)
    if not isinstance(data, dict):
        raise SetupError("SETUP_REQUIRED", "The environment record is damaged. Run SETUP.cmd to repair it.")
    if data.get("project_root") != str(root):
        raise SetupError("PROJECT_MOVED", "This project has moved. Run SETUP.cmd here to repair its environment; your code and saved runs will stay in place.")
    if (data.get("format") != "ultra-project-environment" or data.get("version") != 1
            or data.get("ready") is not True or data.get("status") != "READY" or data.get("lock_sha256") != lock_hash
            or data.get("interpreter") != ".venv/Scripts/python.exe"):
        raise SetupError("SETUP_REQUIRED", "The environment needs a setup check. Run SETUP.cmd and retry.")
    if "bundled_payload_manifest_sha256" in data or (root / ".setup-payload").exists():
        payload_hash = validate_payload(root, lock, lock_hash)
        if payload_hash != data.get("bundled_payload_manifest_sha256"):
            raise SetupError("PAYLOAD_INTEGRITY", "The bundled setup files changed. Extract the original ZIP and rerun SETUP.cmd.")
        launcher_files = direct_bundled_launchers(root, managed_python(root), payload_hash, verify_only=True)
        if data.get("direct_bundled_launcher_files") != launcher_files:
            raise SetupError("SETUP_REQUIRED", "Adventure's bundled interpreter needs a setup check. Run SETUP.cmd and reopen the project.")
    executable = managed_python(root)
    inspect(executable, root, require_pillow=True)
    return executable

def launch(root, *, application=None, inspect=inspect_python, current_executable=None, handoff_runner=None):
    root = Path(root).resolve()
    executable = check_ready(root, inspect=inspect)
    current = Path(current_executable or sys.executable).resolve()
    if os.path.normcase(str(current)) != os.path.normcase(str(executable.resolve())):
        if HANDOFF in os.environ:
            raise SetupError("INTERPRETER_HANDOFF", "Adventure could not switch to its project interpreter. Run SETUP.cmd, then choose .venv in your IDE once.")
        runner = handoff_runner or subprocess.run
        result = runner([str(executable), "-X", "utf8", "-B", str(root / "main.py")], cwd=root,
            env={**os.environ, HANDOFF: "1", "PYTHONDONTWRITEBYTECODE": "1"}, shell=False)
        return result.returncode
    with project_lock(root, "workbench.lock"):
        check_idle(root, "bootstrap.lock", "setup.lock")
        if application is None:
            # The interface is integrated only after the approved design is received.
            if str(root) not in sys.path:
                sys.path.insert(0, str(root))
            from src.workbench.gui import main as application
        return application(root)
