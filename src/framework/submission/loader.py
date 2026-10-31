"""Dynamic import boundary for cooperative development submissions, not an OS sandbox.

Student imports may name src.api, Python's standard library, or pinned helpers
under src.student. Host src/src.api package identity stays instructor-owned.
Introspection, direct filesystem/network access and native process capabilities
are not claimed to be contained. Untrusted hostile code needs a deployment sandbox.
"""
import builtins
import importlib
import importlib.abc
import importlib.util
import runpy
import sys
import types
from pathlib import Path
from .identity import ENTRIES, SubmissionError, source_bytes, verify_sources


class ImportBoundaryError(ImportError):
    pass


class ExecutionPolicyError(RuntimeError):
    pass


class StudentLoader(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def __init__(self, root, manifest):
        self.root, self.manifest = Path(root).resolve(), manifest
        self.files = {p["path"] for p in manifest["sources"]}
        self.loaded_sources = []
        self.original_import = builtins.__import__
        self.original_import_module = importlib.import_module
        self.original_run_module = runpy.run_module
        self.original_run_path = runpy.run_path
        self.filenames = {str(self.root / p) for p in self.files}
        self.policy_violations = []
        self.public_root = types.ModuleType("src")
        self.public_root.api = sys.modules["src.api"]
        self.public_root.__path__ = []

    def _student_call(self):
        frame = sys._getframe(1)
        while frame is not None:
            if frame.f_code.co_filename in self.filenames: return True
            frame = frame.f_back
        return False

    def _allowed(self, name):
        if (name in ("src", "src.api", "src.student") or name.startswith(("src.api.", "src.student."))
                or name.split(".")[0] in sys.stdlib_module_names or name.split(".")[0] in sys.builtin_module_names):
            return
        raise ImportBoundaryError("FORBIDDEN_IMPORT")

    def guarded_import(self, name, globals=None, locals=None, fromlist=(), level=0):
        student = self._student_call()
        # A real instructor dependency callback may perform its own lazy import.
        # Standard-library trampolines still inherit the student boundary. This
        # exception requires the actual loaded host module dictionary, not its name.
        caller = (globals or {}).get("__name__", "")
        host_module = sys.modules.get(caller)
        if (caller.startswith("src.framework.") and host_module is not None
                and globals is vars(host_module)
                and sys._getframe(1).f_code.co_filename == getattr(host_module, "__file__", None)):
            student = False
        if student:
            absolute = importlib.util.resolve_name("." * level + name, (globals or {}).get("__package__")) if level else name
            self._allowed(absolute)
            if absolute == "src":
                for member in fromlist or ():
                    if member not in ("api", "student"): raise ImportBoundaryError("FORBIDDEN_IMPORT")
        result = self.original_import(name, globals, locals, fromlist, level)
        if student and result is sys.modules.get("src"):
            if "src.student" in sys.modules: self.public_root.student = sys.modules["src.student"]
            return self.public_root
        return result

    def guarded_import_module(self, name, package=None):
        absolute = importlib.util.resolve_name(name, package) if name.startswith(".") else name
        self._allowed(absolute)
        result = self.original_import_module(name, package)
        if absolute == "src":
            if "src.student" in sys.modules: self.public_root.student = sys.modules["src.student"]
            return self.public_root
        return result

    def guarded_run_module(self, mod_name, *args, **kwargs):
        self._allowed(mod_name)
        return self.original_run_module(mod_name, *args, **kwargs)

    def guarded_run_path(self, path_name, *args, **kwargs):
        path = Path(path_name).resolve()
        if str(path) not in self.filenames: raise ImportBoundaryError("UNSELECTED_SOURCE")
        return self.original_run_path(path_name, *args, **kwargs)

    def audit(self, event, args):
        if event in {"subprocess.Popen", "os.system", "os.posix_spawn", "os.fork", "os.forkpty",
                     "os.exec", "os.spawn", "os.startfile", "os.startfile/2", "pty.spawn",
                     "_winapi.CreateProcess"}:
            self.policy_violations.append("CHILD_PROCESS_FORBIDDEN")
            raise ExecutionPolicyError("CHILD_PROCESS_FORBIDDEN")

    def install(self):
        for module in list(sys.modules):
            if module == "src.student" or module.startswith("src.student."):
                del sys.modules[module]
        import src
        if hasattr(src, "student"): del src.student
        sys.meta_path.insert(0, self)
        builtins.__import__ = self.guarded_import
        importlib.__import__ = self.guarded_import
        importlib.import_module = self.guarded_import_module
        runpy.run_module = self.guarded_run_module
        runpy.run_path = self.guarded_run_path
        sys.addaudithook(self.audit)

    def find_spec(self, fullname, path=None, target=None):
        if self._student_call(): self._allowed(fullname)
        if fullname == "src.student" or fullname.startswith("src.student."):
            base = fullname.replace(".", "/")
            package = base + "/__init__.py"
            module = base + ".py"
            if module in ENTRIES.values():
                if module not in self.files: raise ImportBoundaryError("REQUIRED_MODULE_ABSENT")
                return importlib.util.spec_from_loader(fullname, self, is_package=False)
            if package in self.files or any(p.startswith(base + "/") for p in self.files):
                return importlib.util.spec_from_loader(fullname, self, is_package=True)
            if module in self.files:
                return importlib.util.spec_from_loader(fullname, self, is_package=False)
            raise ImportBoundaryError("UNSELECTED_HELPER")
        return None

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        package = module.__spec__.submodule_search_locations is not None
        relative = module.__name__.replace(".", "/") + ("/__init__.py" if package else ".py")
        if relative not in self.files:
            if package: return
            raise ImportBoundaryError("UNSELECTED_HELPER")
        source = source_bytes(self.root, self.manifest, relative)
        module.__file__ = str(self.root / relative)
        self.loaded_sources.append(relative)
        exec(compile(source, module.__file__, "exec"), module.__dict__)

    def component(self, component):
        if component not in ENTRIES: raise SubmissionError("UNKNOWN_COMPONENT")
        module = self.original_import_module(ENTRIES[component][:-3].replace("/", "."))
        factory = getattr(module, component, None)
        if not isinstance(factory, type): raise SubmissionError("CLASS_MISSING_OR_NOT_CLASS")
        return factory


_ACTIVE = None


def load_component(descriptor, root):
    """Optional instructor worker hook; only exact intake-selected entry points."""
    global _ACTIVE
    manifest = descriptor["submission"]
    component = descriptor["symbol"]
    if component not in ENTRIES or descriptor["path"] != ENTRIES[component]:
        raise SubmissionError("REPLACEMENT_ENTRY_POINT")
    verify_sources(root, manifest)
    raw = source_bytes(root, manifest, descriptor["path"])
    import hashlib
    if hashlib.sha256(raw).hexdigest() != descriptor["sha256"]:
        raise SubmissionError("SOURCE_DRIFT")
    if _ACTIVE is None:
        _ACTIVE = StudentLoader(root, manifest)
        _ACTIVE.install()
    elif _ACTIVE.root != Path(root).resolve() or _ACTIVE.manifest != manifest:
        raise SubmissionError("MIXED_SUBMISSION")
    return _ACTIVE.component(component)
