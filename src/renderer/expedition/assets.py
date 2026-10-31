"""Versioned optional PNG sheets; every error has a visible geometric fallback."""
from dataclasses import dataclass
from collections import OrderedDict
import json
from pathlib import Path
import struct

CELL = 32
DIRECTIONS = ("north", "east", "south", "west")
LAYOUT = {
    "floor": (("idle",), ("none",), False, 10),
    "wall": (("idle",), ("none",), False, 20),
    "start": (("idle",), ("none",), True, 30),
    "exit": (("available", "accepted"), ("none",), True, 31),
    "artifact": (("available",), ("none",), True, 40),
    "enemy": (("idle",), DIRECTIONS, True, 50),
    "explorer": (("idle", "move", "collect", "engage", "exit", "failed"), DIRECTIONS, True, 60),
}
MAX_IMAGE_BYTES = 1024 * 1024
MAX_MANIFEST_BYTES = 65536
VIEWPORT_POLICY = {"name": "camera-v2", "maximum_scale": 6, "overview": "box-from-source",
                   "enlargement": "nearest-from-source", "cache_entries": 128, "cache_pixels": 1048576}
V1_VIEWPORT_ADAPTER = "v1-source-to-camera-v2"


@dataclass(frozen=True, slots=True)
class Sprite:
    semantic_id: str
    path: Path
    states: tuple[str, ...]
    directions: tuple[str, ...]
    transparency: bool
    layer: int

    @property
    def dimensions(self): return (len(self.directions) * CELL, len(self.states) * CELL)


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result: raise ValueError("DUPLICATE_ASSET_FIELD")
        result[key] = value
    return result


def _manifest(path):
    """Strict metadata-only check; no Tk, Pillow or image decoding is imported."""
    path = Path(path).resolve()
    with path.open("rb") as stream: raw = stream.read(MAX_MANIFEST_BYTES + 1)
    if len(raw) > MAX_MANIFEST_BYTES: raise ValueError("ASSET_MANIFEST_LIMIT")
    data = json.loads(raw, object_pairs_hook=_pairs)
    expected = {"format", "version", "cell", "projection", "anchor", "padding", "scaling", "animation",
                "overlay_layers", "provenance", "assets"}
    if type(data) is dict and type(data.get("version")) is int and data["version"] == 2:
        expected.add("viewport")
    if type(data) is not dict or set(data) != expected: raise ValueError("ASSET_SCHEMA")
    if (data["format"] != "ultra-expedition-assets" or type(data["version"]) is not int or data["version"] not in (1, 2)
            or data["cell"] != [32, 32] or data["projection"] != "top-down-orthogonal"
            or data["anchor"] != [16, 16] or type(data["padding"]) is not int or data["padding"] != 2
            or data["scaling"] != ("integer-nearest-1-through-6" if data["version"] == 1 else "camera-v2-source-resampling")
            or data["animation"] != "one-pose-per-recorded-state-no-interpolation"
            or data["overlay_layers"] != {"visited": 25, "patrol_indicator": 55, "event": 70, "grid_labels": 80}):
        raise ValueError("UNSUPPORTED_ASSET_CONTRACT")
    if data["version"] == 2 and (data["viewport"] != VIEWPORT_POLICY or
            any(type(data["viewport"][key]) is not type(value) for key, value in VIEWPORT_POLICY.items())):
        raise ValueError("UNSUPPORTED_VIEWPORT_POLICY")
    if any(type(data[k]) is not list or any(type(v) is not int for v in data[k]) for k in ("cell", "anchor")):
        raise ValueError("UNSUPPORTED_ASSET_CONTRACT")
    if any(type(v) is not int for v in data["overlay_layers"].values()):
        raise ValueError("UNSUPPORTED_ASSET_CONTRACT")
    if type(data["provenance"]) is not dict or set(data["provenance"]) != {
            "creator", "source", "source_url", "license", "redistribution_approved", "production_art"}:
        raise ValueError("ASSET_PROVENANCE_REQUIRED")
    provenance = data["provenance"]
    if (any(type(provenance[k]) is not str for k in ("creator", "source", "source_url", "license"))
            or any(type(provenance[k]) is not bool for k in ("redistribution_approved", "production_art"))):
        raise ValueError("ASSET_PROVENANCE_REQUIRED")
    if type(data["assets"]) is not dict or set(data["assets"]) != set(LAYOUT): raise ValueError("ASSET_IDS")
    sprites = []
    for name, (states, directions, transparency, layer) in LAYOUT.items():
        item = data["assets"][name]
        if type(item) is not dict or set(item) != {"file", "sheet", "states", "directions", "transparent", "layer", "frames_per_pose"}:
            raise ValueError("ASSET_SCHEMA")
        if (item["states"] != list(states) or item["directions"] != list(directions)
                or item["transparent"] is not transparency or type(item["layer"]) is not int or item["layer"] != layer
                or type(item["frames_per_pose"]) is not int or item["frames_per_pose"] != 1
                or item["sheet"] != [len(directions) * CELL, len(states) * CELL]):
            raise ValueError("UNSUPPORTED_ASSET_LAYOUT")
        if type(item["sheet"]) is not list or any(type(v) is not int for v in item["sheet"]):
            raise ValueError("UNSUPPORTED_ASSET_LAYOUT")
        relative = item["file"]
        if (type(relative) is not str or "\\" in relative or Path(relative).is_absolute()
                or ".." in Path(relative).parts or Path(relative).suffix != ".png"):
            raise ValueError("ASSET_PATH_ESCAPE")
        target = (path.parent / relative).resolve()
        if not target.is_relative_to(path.parent): raise ValueError("ASSET_PATH_ESCAPE")
        sprites.append(Sprite(name, target, states, directions, transparency, layer))
    return tuple(sprites), data["version"]


def read_manifest(path):
    """Both strict versions retain exactly the original source-sheet layout."""
    return _manifest(path)[0]


def png_bytes(sprite):
    with sprite.path.open("rb") as stream: raw = stream.read(MAX_IMAGE_BYTES + 1)
    if len(raw) > MAX_IMAGE_BYTES: raise ValueError("IMAGE_LIMIT")
    if (len(raw) < 33 or raw[:8] != b"\x89PNG\r\n\x1a\n" or raw[8:12] != b"\x00\x00\x00\x0d"
            or raw[12:16] != b"IHDR"): raise ValueError("PNG_REQUIRED")
    width, height, depth, color, compression, filtering, interlace = struct.unpack(">IIBBBBB", raw[16:29])
    if (width, height) != sprite.dimensions: raise ValueError("SHEET_DIMENSIONS")
    if depth != 8 or color not in (2, 6) or compression != 0 or filtering != 0 or interlace != 0:
        raise ValueError("UNSUPPORTED_PNG")
    if sprite.transparency and color != 6: raise ValueError("RGBA_REQUIRED")
    return raw


class SpriteBank:
    """Optional Tk images. Failed/missing sheets never prevent replay."""
    def __init__(self, tk, root, manifest_path):
        self.tk, self.root = tk, root
        self.sheets, self.specs, self.cache, self.warnings = {}, {}, OrderedDict(), []
        self.raw_sheets, self.originals = {}, {}
        self.source_version = None
        self.adapter = "camera-v2"
        self._pillow_checked = False
        self._pillow = None
        self.display_notice = ""
        try:
            specifications, self.source_version = _manifest(manifest_path)
            if self.source_version == 1: self.adapter = V1_VIEWPORT_ADAPTER
        except Exception:
            self.warnings.append("Asset manifest unavailable or unsupported; all placeholders active.")
            specifications = ()
        for sprite in specifications:
            self.specs[sprite.semantic_id] = sprite
            try:
                raw = png_bytes(sprite)
                # Decode bounded bytes, not a second unvalidated file read.
                image = tk.PhotoImage(master=root, data=raw, format="png")
                if (image.width(), image.height()) != sprite.dimensions: raise ValueError("IMAGE_DIMENSIONS")
                if sprite.transparency:
                    for y in range(0, image.height(), CELL):
                        for x in range(0, image.width(), CELL):
                            for i in range(CELL):
                                for p in (0, 1):
                                    edges = ((x+i,y+p),(x+i,y+31-p),(x+p,y+i),(x+31-p,y+i))
                                    if not all(image.transparency_get(a, b) for a, b in edges):
                                        raise ValueError("TRANSPARENT_ENTITY_PADDING_REQUIRED")
                self.sheets[sprite.semantic_id] = image
                self.raw_sheets[sprite.semantic_id] = raw
            except Exception:
                self.warnings.append(sprite.semantic_id + ": placeholder (missing or invalid sheet).")

    @property
    def fallback_count(self): return len(LAYOUT) - len(self.sheets)

    @property
    def cache_pixels(self): return sum(photo.width() * photo.height() for photo in self.cache.values())

    def _remember(self, key, image):
        self.cache[key] = image
        self.cache.move_to_end(key)
        while len(self.cache) > VIEWPORT_POLICY["cache_entries"] or self.cache_pixels > VIEWPORT_POLICY["cache_pixels"]:
            self.cache.popitem(last=False)
        return image

    def photo(self, semantic_id, state, direction, scale):
        # Preserve the v1 integer crop path, now with a finite cache.
        if type(scale) is not int or not 1 <= scale <= 6: return None
        if semantic_id not in self.sheets: return None
        spec = self.specs[semantic_id]
        direction = direction if direction in spec.directions else spec.directions[0]
        state = state if state in spec.states else spec.states[0]
        key = ("integer", semantic_id, state, direction, scale)
        if key not in self.cache:
            x, y = spec.directions.index(direction) * CELL, spec.states.index(state) * CELL
            cropped = self.tk.PhotoImage(master=self.root, width=CELL, height=CELL)
            cropped.tk.call(cropped, "copy", self.sheets[semantic_id], "-from", x, y, x + CELL, y + CELL)
            self._remember(key, cropped.zoom(scale, scale))
        self.cache.move_to_end(key)
        return self.cache[key]

    def at_size(self, semantic_id, state, direction, width, height):
        """v1-source-to-camera-v2 or native v2: resample original bounded crops."""
        if semantic_id not in self.sheets: return None
        if any(type(v) is not int or not 1 <= v <= CELL * 6 + 1 for v in (width, height)): return None
        if width == height and width % CELL == 0:
            return self.photo(semantic_id, state, direction, width // CELL)
        if not self._pillow_checked:
            self._pillow_checked = True
            try:
                from PIL import Image, ImageTk
                self._pillow = Image, ImageTk
            except ImportError:
                self.display_notice = "Fractional sprite display needs Pillow; geometric placeholders are active."
        if self._pillow is None: return None
        spec = self.specs[semantic_id]
        state = state if state in spec.states else spec.states[0]
        direction = direction if direction in spec.directions else spec.directions[0]
        key = ("target", semantic_id, state, direction, width, height)
        if key in self.cache:
            self.cache.move_to_end(key); return self.cache[key]
        Image, ImageTk = self._pillow
        try:
            if semantic_id not in self.originals:
                from io import BytesIO
                with Image.open(BytesIO(self.raw_sheets[semantic_id])) as original:
                    original.load()
                    self.originals[semantic_id] = original.convert("RGBA")
            x, y = spec.directions.index(direction) * CELL, spec.states.index(state) * CELL
            crop = self.originals[semantic_id].crop((x, y, x + CELL, y + CELL))
            filter_kind = Image.Resampling.BOX if min(width, height) < CELL else Image.Resampling.NEAREST
            resized = crop.resize((width, height), resample=filter_kind)
            return self._remember(key, ImageTk.PhotoImage(resized, master=self.root))
        except Exception:
            self.display_notice = "Sprite resampling unavailable; geometric placeholders are active."
            return None


def placeholder(canvas, name, x, y, size, *, state="idle", direction="south"):
    """Geometric temporary art shared by the viewer and contact-sheet capture."""
    cx, cy = x + size / 2, y + size / 2
    unit = size / 32
    text_font = ("Segoe UI", max(8, round(size * .13)), "bold")
    if name == "floor":
        canvas.create_rectangle(x, y, x + size, y + size, fill="#e9e2d2", outline="#ddd4c1")
        canvas.create_line(x + 7 * unit, y + 25 * unit, x + 12 * unit, y + 25 * unit, fill="#d5cbb7")
    elif name == "wall":
        canvas.create_rectangle(x, y, x + size, y + size, fill="#344d50", outline="#294346")
        canvas.create_line(x + 3 * unit, y + 4 * unit, x + 29 * unit, y + 4 * unit, fill="#526b6d", width=max(1, unit))
        canvas.create_line(x + 16 * unit, y + 5 * unit, x + 16 * unit, y + 28 * unit, fill="#2e4649")
    elif name == "start":
        canvas.create_oval(x + 6 * unit, y + 6 * unit, x + 26 * unit, y + 26 * unit, outline="#54789c", width=2 * unit)
        canvas.create_text(cx, cy, text="S", fill="#355e85", font=text_font)
    elif name == "exit":
        fill = "#58ae82" if state == "accepted" else "#b1cbb5"
        canvas.create_rectangle(x + 5 * unit, y + 5 * unit, x + 27 * unit, y + 27 * unit, fill=fill, outline="#37815f", width=2 * unit)
        canvas.create_text(cx, cy, text="OK" if state == "accepted" else "EXIT", fill="#164a34", font=text_font)
    elif name == "artifact":
        canvas.create_polygon(cx, y + 5 * unit, x + 26 * unit, cy, cx, y + 27 * unit, x + 6 * unit, cy,
                              fill="#e9bb55", outline="#9e7023", width=1.5 * unit)
        canvas.create_text(cx, cy, text="A", fill="#6a4616", font=text_font)
    elif name == "enemy":
        dx, dy = {"north": (0, -1), "east": (1, 0), "south": (0, 1), "west": (-1, 0)}[direction]
        canvas.create_polygon(cx + dx * 12 * unit, cy + dy * 12 * unit,
                              cx - dx * 9 * unit - dy * 11 * unit, cy - dy * 9 * unit + dx * 11 * unit,
                              cx - dx * 9 * unit + dy * 11 * unit, cy - dy * 9 * unit - dx * 11 * unit,
                              fill="#bf6c57", outline="#833e31", width=1.5 * unit)
        canvas.create_text(cx - dx * 3 * unit, cy - dy * 3 * unit, text="!", fill="#fff6e9", font=text_font)
    elif name == "explorer":
        fill = "#318c86" if state != "failed" else "#a95042"
        canvas.create_oval(x + 6 * unit, y + 6 * unit, x + 26 * unit, y + 26 * unit, fill=fill, outline="#154f51", width=2 * unit)
        dx, dy = {"north": (0, -1), "east": (1, 0), "south": (0, 1), "west": (-1, 0)}[direction]
        if state == "move":
            for behind in (12, 14):
                px, py = cx - dx * behind * unit, cy - dy * behind * unit
                canvas.create_line(px - dy * 3 * unit, py + dx * 3 * unit, px + dy * 3 * unit, py - dx * 3 * unit,
                                   fill="#318c86", width=max(1,unit))
        canvas.create_line(cx, cy, cx + dx * 8 * unit, cy + dy * 8 * unit, fill="#fff9e9", width=2 * unit, arrow="last")
        if state in ("collect", "engage", "exit", "failed"):
            marker = {"collect": "+", "engage": "!", "exit": "OK", "failed": "X"}[state]
            canvas.create_text(x + 25 * unit, y + 6 * unit, text=marker, fill="#7c401e", font=text_font)
