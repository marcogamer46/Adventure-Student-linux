"""Immutable public inputs and one owned asynchronous workbench attempt.

Tk callers consume finite queue messages; this module never touches widgets.
Worker execution, generation certification and source capture are lazy imports.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import queue
import threading
from types import SimpleNamespace
import uuid

from src.framework.static_records import encode, read_json
from src.framework.public_project.recording import read_level, validate_record

MAX_INPUT = 16 * 1024 * 1024


class ServiceError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def digest(raw): return hashlib.sha256(raw).hexdigest()


def read_member(root, relative, *, limit=MAX_INPUT):
    """Read a named bundle/practice member without following linked paths."""
    root = Path(root).resolve()
    if type(relative) is not str or '\\' in relative or ':' in relative:
        raise ServiceError('INPUT_PATH_ESCAPE')
    path = PurePosixPath(relative)
    if path.is_absolute() or '..' in path.parts or str(path) != relative:
        raise ServiceError('INPUT_PATH_ESCAPE')
    current = root
    for part in path.parts:
        current /= part
        if current.is_symlink() or getattr(current, 'is_junction', lambda: False)():
            raise ServiceError('INPUT_PATH_ESCAPE')
    if not current.resolve().is_relative_to(root):
        raise ServiceError('INPUT_PATH_ESCAPE')
    with current.open('rb') as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ServiceError('INPUT_LIMIT')
    return raw


@dataclass(frozen=True, slots=True)
class SelectedInput:
    slug: str
    name: str
    guide_anchor: str | None
    raw: bytes
    kind: str = 'public_scenario'
    generation: bytes | None = None
    context_source_sha256: str | None = None

    @property
    def identity(self): return digest(self.raw)

    @property
    def configuration(self):
        return read_json(self.raw)['configuration']

    def level(self):
        if self.kind == 'terrain_only': raise ServiceError('TERRAIN_IS_NOT_A_LEVEL')
        return read_level(read_json(self.raw))[0]


@dataclass(frozen=True, slots=True)
class SavedPlayback:
    selected: SelectedInput
    raw: bytes
    folder: str
    example: bool = False

    @property
    def source_identity(self): return read_json(self.raw)['source_identity']['sha256']

    def presentation(self):
        from src.renderer.expedition.practice import load_public
        return load_public(self.raw, title=self.selected.name)


def content(root):
    data = read_json(read_member(root, 'WORKBENCH_CONTENT.json', limit=1048576))
    if type(data) is not dict or data.get('format') != 'ultra-workbench-content' or data.get('version') != 1:
        raise ServiceError('CONTENT_MANIFEST')
    rows = data.get('scenarios')
    if type(rows) is not list or not 1 <= len(rows) <= 256:
        raise ServiceError('CONTENT_MANIFEST')
    if len({r.get('slug') for r in rows}) != len(rows): raise ServiceError('CONTENT_MANIFEST')
    return data


def select_scenario(root, row):
    raw = read_member(root, row['path'])
    if digest(raw) != row['sha256']: raise ServiceError('PUBLIC_INPUT_CHANGED')
    read_level(read_json(raw))
    return SelectedInput(row['slug'], row['name'], row['guide_anchor'], raw, context_source_sha256=row['sha256'])


def scenario_variants(rows):
    """Explicit registered endpoint alternatives, never edit an admitted input."""
    for row in rows:
        yield row
        if row.get('alternate') is not None:
            yield row['alternate']


def input_context(selected, raw, kind):
    return encode(dict(format='ultra-workbench-input-context', version=1,
        input_sha256=digest(encode(read_json(raw))), input_kind=kind, slug=selected.slug,
        name=selected.name, guide_anchor=selected.guide_anchor,
        source_input_sha256=selected.context_source_sha256 or selected.identity))


def restore_context(root, relative, raw, kind):
    """Restore a bundle alias only when bound to this exact saved input."""
    context_raw=read_member(root, relative+'/input-context.json', limit=65536)
    value=read_json(context_raw)
    attempt=read_json(read_member(root, relative+'/attempt.json', limit=65536))
    keys={'format','version','input_sha256','input_kind','slug','name','guide_anchor','source_input_sha256'}
    if (type(value) is not dict or set(value)!=keys or value['format']!='ultra-workbench-input-context'
            or type(value['version']) is not int or value['version']!=1
            or value['input_kind']!=kind or value['input_sha256']!=digest(encode(read_json(raw)))
            or attempt.get('input_context_sha256')!=digest(context_raw)):
        raise ServiceError('INPUT_CONTEXT_MISMATCH')
    row=next((r for r in scenario_variants(content(root)['scenarios']) if r['slug']==value['slug']),None)
    if (row is None or row['name']!=value['name'] or row['guide_anchor']!=value['guide_anchor']
            or row['sha256']!=value['source_input_sha256']):
        raise ServiceError('INPUT_CONTEXT_MISMATCH')
    source=select_scenario(root,row)
    saved=read_json(raw)
    if source.configuration!=saved['configuration']:
        raise ServiceError('INPUT_CONTEXT_MISMATCH')
    if kind=='public_scenario' and read_json(source.raw)!=saved:
        raise ServiceError('INPUT_CONTEXT_MISMATCH')
    return row


def load_saved(root, relative, *, name='Saved Adventure run', slug='saved', guide_anchor=None, example=False):
    """Validate both the run companions and its exact original input."""
    if not relative.startswith('demos/' if example else 'practice/'):
        raise ServiceError('RUN_PATH_ESCAPE')
    from .project import _replay
    for filename in ('run.json', 'manifest.json', 'resources.json', 'level.json'):
        read_member(root, relative + '/' + filename)
    folder = Path(root).resolve() / relative
    def bounded(path):
        return read_member(root, Path(path).relative_to(Path(root).resolve()).as_posix())
    if _replay(SimpleNamespace(run=folder, headless=True), bounded) is None:
        raise ServiceError('UNSUPPORTED_RECORDING')
    attempt = read_json(read_member(root, relative + '/attempt.json', limit=65536))
    if type(attempt) is not dict or attempt.get('status') != 'SAVED':
        raise ServiceError('RUN_NOT_COMMITTED')
    raw = read_member(root, relative + '/run.json')
    view, data = validate_record(raw), read_json(raw)
    level_raw = read_member(root, relative + '/level.json')
    level, config, admission = read_level(read_json(level_raw))
    if (level != view.snapshots[0].level or config != data['admission']['configuration']
            or admission['baseline_cost'] != view.summary['L']):
        raise ServiceError('RUN_INPUT_MISMATCH')
    generation = data.get('generation_identity')
    provenance = None
    if generation is not None:
        provenance = read_member(root, relative + '/generation.json', limit=262144)
        checked_generation(provenance, level_raw)
        if read_json(provenance)['source_identity'] != generation:
            raise ServiceError('GENERATION_PROVENANCE_MISMATCH')
    kind='generated_level' if generation is not None else 'public_scenario'
    row=None if example else restore_context(root,relative,level_raw,kind)
    selected = SelectedInput(slug if row is None else row['slug'], name if row is None else row['name'],
        guide_anchor if row is None else row['guide_anchor'], level_raw, kind, provenance,
        None if row is None else row['sha256'])
    return SavedPlayback(selected, raw, relative, example)


def checked_generation(raw, level_raw):
    from src.framework.public_practice.records import validate_identity
    value = read_json(raw)
    keys = {'format', 'version', 'level_sha256', 'source_identity', 'runtime_identity', 'authority'}
    if (type(value) is not dict or set(value) != keys or value['format'] != 'ultra-workbench-generation-provenance'
            or type(value['version']) is not int or value['version'] != 2
            or value['authority'] != 'LOCAL_PUBLIC_CONTENT_BINDING_ONLY'
            or value['level_sha256'] != digest(encode(read_json(level_raw)))):
        raise ServiceError('GENERATION_PROVENANCE_MISMATCH')
    validate_identity(value['source_identity']); validate_identity(value['runtime_identity'])
    return value


def load_generated(root, relative, *, name='Generated input', slug='generated', guide_anchor=None):
    if not relative.startswith('practice/'): raise ServiceError('INPUT_PATH_ESCAPE')
    raw = read_member(root, relative + '/generated.json')
    provenance = read_member(root, relative + '/generated.json.manifest.json', limit=262144)
    checked_generation(provenance, raw)
    data = read_json(raw)
    terrain = data.get('format') == 'ultra-public-project-terrain'
    if terrain:
        from src.framework.generation.canonical import read_terrain
        from src.framework.public_project.catalog import validate_configuration
        read_terrain(data['terrain']); validate_configuration(data['configuration'])
    else:
        read_level(data)
    attempt=read_json(read_member(root, relative+'/attempt.json', limit=65536))
    if attempt.get('status')!='GENERATED':raise ServiceError('GENERATION_NOT_COMMITTED')
    kind='terrain_only' if terrain else 'generated_level'
    row=restore_context(root,relative,raw,kind)
    return SelectedInput(row['slug'],row['name'],row['guide_anchor'],raw,kind,provenance,row['sha256'])


def prepared_example(root, row):
    example = row.get('prepared_example')
    if not example: raise ServiceError('NO_PREPARED_EXAMPLE')
    result = load_saved(root, example['path'], name=row['name'], slug=row['slug'],
                        guide_anchor=row['guide_anchor'], example=True)
    if digest(result.raw) != example['sha256']: raise ServiceError('PUBLIC_EXAMPLE_CHANGED')
    if result.selected.identity != select_scenario(root, row).identity:
        # Original files may differ only in whitespace; compare the admitted data.
        if read_json(result.selected.raw) != read_json(select_scenario(root, row).raw):
            raise ServiceError('EXAMPLE_INPUT_MISMATCH')
    return SavedPlayback(select_scenario(root,row),result.raw,result.folder,True)


def saved_runs(root):
    """Bounded history labels from the same passive validator used to reopen."""
    base = Path(root).resolve() / 'practice'
    if not base.exists(): return ()
    if base.is_symlink() or getattr(base, 'is_junction', lambda: False)():
        raise ServiceError('RUN_PATH_ESCAPE')
    result = []
    for folder in sorted(base.glob('gui-*'), reverse=True)[:256]:
        if folder.is_dir() and (folder / 'manifest.json').is_file():
            try:
                tracking = read_json(read_member(root, 'practice/' + folder.name + '/manifest.json', limit=65536))
                attempt = read_json(read_member(root, 'practice/' + folder.name + '/attempt.json', limit=65536))
                if type(tracking) is not dict or type(attempt) is not dict:
                    continue
                if tracking.get('status') == 'SAVED' and attempt.get('status') == 'SAVED':
                    relative = folder.relative_to(root).as_posix()
                    playback = load_saved(root, relative)
                    summary = validate_record(playback.raw).summary
                    name = ' '.join(playback.selected.name.split())[:72] or 'Saved scenario'
                    when = tracking.get('recorded_utc')
                    readable = 'Time unavailable'
                    if type(when) is str and len(when) <= 40:
                        try:
                            date = datetime.fromisoformat(when.replace('Z', '+00:00'))
                            if date.tzinfo is not None:
                                readable = date.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
                        except (ValueError, OverflowError):
                            pass
                    outcome = 'completed' if summary['completed'] else 'failed'
                    result.append((relative, name + ' — ' + outcome + ' — ' + readable))
            except (OSError, ValueError, TypeError):
                continue
    return tuple(result)


class AttemptService:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.events = queue.Queue(maxsize=64)
        self._lock = threading.Lock()
        self._active = None
        self._serial = 0
        self._published_token = None

    @property
    def busy(self):
        with self._lock: return self._active is not None

    def cancel(self):
        with self._lock:
            if self._active is not None and self._active[0] != self._published_token:
                self._active[1].set()
                return True
            return False

    def _send(self, value):
        try: self.events.put_nowait(value)
        except queue.Full:
            # Progress is replaceable; the single terminal result is retained.
            if value['event'] == 'phase': return
            self.events.get_nowait(); self.events.put_nowait(value)

    def start(self, selected, *, operation='solve', provider='reference'):
        if operation not in {'solve', 'terrain', 'level'} or provider not in {'reference', 'student'}:
            raise ServiceError('UNKNOWN_OPERATION')
        if operation == 'solve' and selected.kind == 'terrain_only':
            raise ServiceError('TERRAIN_IS_NOT_A_LEVEL')
        with self._lock:
            if self._active is not None: raise ServiceError('ATTEMPT_BUSY')
            self._serial += 1
            token, stop = self._serial, threading.Event()
            self._active = (token, stop)
            self._published_token = None
        thread = threading.Thread(target=self._run, args=(token, stop, selected, operation, provider), daemon=True)
        try: thread.start()
        except BaseException:
            with self._lock: self._active = None
            raise
        return token

    def _run(self, token, stop, selected, operation, provider):
        folder = None
        def phase(value): self._send(dict(token=token, input_identity=selected.identity, event='phase', phase=value))
        try:
            from .process import execute, runtime_identity, source_identity, WorkbenchError
            from .__main__ import destination, reserve, atomic
            from .project import save_run
            from src.framework.submission.identity import capture_sources, verify_sources
            from src.framework.public_practice.records import validate_identity
            phase('checking_sources')
            manifest = capture_sources(self.root)
            runtime = runtime_identity(project=True,gui=True)
            folder = destination('practice/gui-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex,
                                 self.root, directory=True)
            reserve(folder, directory=True)
            generation = None
            if selected.generation is not None:
                provenance = checked_generation(selected.generation, selected.raw)
                generation = provenance['source_identity']
            payload = (dict(level=read_json(selected.raw), generation_identity=generation) if operation == 'solve'
                       else dict(configuration=selected.configuration, dependency=provider))
            outcome = execute({'solve':'solve_v2', 'terrain':'terrain_v2', 'level':'generate_v2'}[operation],
                self.root, payload, manifest=manifest, runtime=runtime, cancel_event=stop, on_progress=phase)
            verify_sources(self.root, manifest)
            if stop.is_set(): raise WorkbenchError('CANCELLED', 'CANCELLED')
            if operation == 'solve':
                view, tracking = save_run(folder, read_json(selected.raw), outcome, generation, atomic, publish=False)
                if selected.generation is not None:
                    atomic(folder / 'generation.json', selected.generation)
                run_raw = read_member(self.root, folder.relative_to(self.root).as_posix() + '/run.json')
                if digest(run_raw) != tracking['run_sha256']:
                    raise ServiceError('RUN_WRITE_MISMATCH')
                validate_record(run_raw)
                result = SavedPlayback(selected, run_raw, folder.relative_to(self.root).as_posix())
                marker = dict(status='SAVED', outcome=outcome['outcome'], code=outcome['code'])
                context_raw=input_context(selected,selected.raw,selected.kind)
            else:
                if operation == 'terrain':
                    record = dict(format='ultra-public-project-terrain', version=2,
                        configuration=selected.configuration, terrain=outcome['terrain'])
                else:
                    from src.framework.public_project.preparation import prepare_level
                    from src.framework.generation.canonical import read_level as read_candidate
                    phase('validating_result')
                    record = prepare_level(read_candidate(outcome['level']), selected.configuration)
                verify_sources(self.root, manifest)
                if stop.is_set(): raise WorkbenchError('CANCELLED', 'CANCELLED')
                raw = encode(record)
                provenance = dict(format='ultra-workbench-generation-provenance', version=2,
                    level_sha256=digest(raw), source_identity=source_identity(manifest), runtime_identity=runtime,
                    authority='LOCAL_PUBLIC_CONTENT_BINDING_ONLY')
                atomic(folder / 'generated.json', raw)
                atomic(folder / 'generated.json.manifest.json', encode(provenance))
                atomic(folder / 'resources.json', encode(outcome['worker']))
                marker = dict(status='GENERATED', kind=operation)
                result = SelectedInput(selected.slug, selected.name, selected.guide_anchor, raw,
                    'terrain_only' if operation == 'terrain' else 'generated_level', encode(provenance),
                    selected.context_source_sha256)
                context_raw=input_context(result,raw,result.kind)
            atomic(folder/'input-context.json',context_raw)
            marker['input_context_sha256']=digest(context_raw)
            event = dict(token=token, input_identity=selected.identity, event='result', operation=operation, result=result,
                source_identity=source_identity(manifest)['sha256'], diagnostic=outcome.get('diagnostic'))
            # One commit point. Cancellation wins before this lock; after the
            # final marker is written publication wins and cancel is a no-op.
            with self._lock:
                if stop.is_set(): raise WorkbenchError('CANCELLED', 'CANCELLED')
                atomic(folder / 'attempt.json', encode(marker))
                if operation == 'solve':
                    atomic(folder / 'manifest.json', encode(tracking))
                self._published_token = token
        except BaseException as exc:
            # Only known finite categories and validated worker context are public.
            from .process import WorkbenchError
            trusted = isinstance(exc, WorkbenchError)
            event = dict(token=token, input_identity=selected.identity, event='error', operation=operation,
                status=exc.status if trusted else 'HOST_ERROR', code=exc.code if trusted else 'INPUT_OR_HOST_ERROR',
                diagnostic=exc.diagnostic if trusted else None, resources=exc.resources if trusted else None)
            if folder is not None:
                try:
                    from .__main__ import atomic
                    atomic(folder / 'attempt.json', encode({k:event[k] for k in ('status','code','diagnostic','resources')}))
                except OSError: pass
        finally:
            with self._lock:
                if self._active is not None and self._active[0] == token:
                    self._active = None
        self._send(event)
