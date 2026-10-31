"""Pure map-to-viewport transform. It has no replay, entity or simulation state."""
import math

CELL = 32
MAX_SCALE = 6.0


class Camera:
    def __init__(self, rows, columns, *, margin=20):
        if type(rows) is not int or type(columns) is not int or not 1 <= rows <= 128 or not 1 <= columns <= 128:
            raise ValueError("CAMERA_BOARD_RANGE")
        self.rows, self.columns = rows, columns
        self.width = self.height = 1.0
        self.margin = float(margin)
        self.scale = 1.0
        self.x = self.y = 0.0
        self.fit_mode = True
        self.fit()

    @property
    def padding(self): return min(self.margin, self.width / 10, self.height / 10)

    @property
    def fit_scale(self):
        p = self.padding
        return min(MAX_SCALE, (self.width - 2 * p) / (self.columns * CELL),
                   (self.height - 2 * p) / (self.rows * CELL))

    @property
    def state(self): return (self.width, self.height, self.scale, self.x, self.y, self.fit_mode)

    def world_at(self, x, y): return ((x - self.x) / self.scale, (y - self.y) / self.scale)

    def _clamp(self):
        def axis(offset, extent, size):
            if size <= extent - 2 * self.padding: return (extent - size) / 2
            return max(extent - self.padding - size, min(self.padding, offset))
        self.x = axis(self.x, self.width, self.columns * CELL * self.scale)
        self.y = axis(self.y, self.height, self.rows * CELL * self.scale)

    def fit(self):
        self.fit_mode = True
        self.scale = self.fit_scale
        self.x = (self.width - self.columns * CELL * self.scale) / 2
        self.y = (self.height - self.rows * CELL * self.scale) / 2

    def resize(self, width, height):
        if not all(type(v) in (int, float) and math.isfinite(v) and v > 0 for v in (width, height)):
            return
        if (width, height) == (self.width, self.height): return
        center = self.world_at(self.width / 2, self.height / 2)
        self.width, self.height = float(width), float(height)
        if self.fit_mode: self.fit()
        else:
            self.scale = max(self.fit_scale, min(MAX_SCALE, self.scale))
            self.x, self.y = self.width / 2 - center[0] * self.scale, self.height / 2 - center[1] * self.scale
            self._clamp()

    def zoom(self, factor, x=None, y=None):
        if type(factor) not in (int, float) or not math.isfinite(factor) or factor <= 0: return
        x = self.width / 2 if x is None else x
        y = self.height / 2 if y is None else y
        if not all(type(v) in (int, float) and math.isfinite(v) for v in (x, y)): return
        world = self.world_at(x, y)
        self.scale = max(self.fit_scale, min(MAX_SCALE, self.scale * factor))
        if math.isclose(self.scale, self.fit_scale, rel_tol=1e-10): self.fit()
        else:
            self.fit_mode = False
            self.x, self.y = x - world[0] * self.scale, y - world[1] * self.scale
            self._clamp()

    def pan(self, dx, dy):
        if not all(type(v) in (int, float) and math.isfinite(v) for v in (dx, dy)): return
        before = self.x, self.y
        self.x += dx; self.y += dy; self._clamp()
        if before != (self.x, self.y): self.fit_mode = False

    def box(self, row, column):
        # Adjacent cells share the exact same rounded edge, including below 1x.
        size = CELL * self.scale
        return (round(self.x + column * size), round(self.y + row * size),
                round(self.x + (column + 1) * size), round(self.y + (row + 1) * size))

    def visible(self):
        size = CELL * self.scale
        first_row = max(0, math.floor(-self.y / size))
        last_row = min(self.rows, math.ceil((self.height - self.y) / size))
        first_column = max(0, math.floor(-self.x / size))
        last_column = min(self.columns, math.ceil((self.width - self.x) / size))
        return range(first_row, last_row), range(first_column, last_column)
