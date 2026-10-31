"""Native optional Tk replay UI with an independent, bounded map camera."""
from pathlib import Path
from .assets import CELL, SpriteBank, placeholder
from .camera import Camera, MAX_SCALE
from .dialogs import ReplayDialogs
from .display import initialize_display, inspect_display, named_fonts
from .formatting import current_status
from .inspector import ReplaySummary
from .timeline import Timeline

ROOT = Path(__file__).resolve().parents[3]
BG, PANEL, INK, MUTED, ACCENT = "#f1eee5", "#fffdf8", "#263f42", "#566c6b", "#277d78"


class ViewerUnavailableError(RuntimeError): pass


class ExpeditionViewer:
    BG, PANEL, INK, MUTED, ACCENT = BG, PANEL, INK, MUTED, ACCENT

    def __init__(self, recordings, *, selected=None, asset_manifest=None, public_showcase=False):
        if not recordings: raise ValueError("RECORDING_REQUIRED")
        self.recordings = dict(recordings)
        self.selected = selected or next(iter(self.recordings))
        self.timeline = Timeline(self.recordings[self.selected])
        self.asset_manifest = asset_manifest or ROOT / "assets/presentation/asset-manifest-v2.json"
        self.public_showcase = public_showcase
        self.root = self.tk = self.canvas = self.bank = None
        self.after_id = self.draw_after_id = None
        self.closed = False
        self.buttons = {}
        self.startup = None
        self.dialogs = None
        self._drag_point = None
        self.frame_photos = []
        self.draw_count = 0
        self.ui_scale = 1.0
        self.camera = Camera(self.timeline.recording.rows, self.timeline.recording.columns)

    def dp(self, value): return max(1, round(value * self.ui_scale))

    def run(self):
        self.startup = initialize_display()  # Before importing Tk or creating any window.
        try:
            import tkinter as tk
            root = tk.Tk()
        except Exception as exc:
            raise ViewerUnavailableError("TKINTER_OR_DISPLAY_UNAVAILABLE") from exc
        try:
            self.build(root, tk); root.mainloop()
        finally: self.close()

    def button(self, parent, text, command, *, primary=False, width=None):
        kw = {} if width is None else {"width": width}
        return self.tk.Button(parent, text=text, command=command, font=self.fonts["body"],
            bg=ACCENT if primary else PANEL, fg="white" if primary else INK, relief="flat",
            activebackground="#c9ded2", activeforeground=INK, padx=self.dp(9), pady=self.dp(5),
            bd=1, highlightthickness=2, highlightcolor=ACCENT, highlightbackground="#d6ddd4",
            takefocus=True, **kw)

    def build(self, root, tk):
        from tkinter import ttk
        self.root, self.tk = root, tk
        root.title("Algorithmic Expedition — development replay")
        root.configure(bg=BG)
        self.ui_scale = max(.75, min(3, float(root.winfo_fpixels("1i")) / 96))
        self.fonts = named_fonts(root)
        root.option_add("*Font", self.fonts["body"])
        self.display_info = inspect_display(root, self.fonts, startup=self.startup)
        work = next((m["work_area"] for m in self.display_info.get("monitors", []) if m["active"]), None)
        width, height = (work[2] - work[0], work[3] - work[1]) if work else (root.winfo_screenwidth(), root.winfo_screenheight())
        root.geometry(f"{min(1240, width - self.dp(30))}x{min(800, height - self.dp(50))}")
        root.minsize(min(1100, width - self.dp(30)), min(700, height - self.dp(50)))
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.grid_columnconfigure(0, weight=1); root.grid_rowconfigure(1, weight=1)
        self.bank = SpriteBank(tk, root, self.asset_manifest)
        self.camera.margin = self.dp(24)
        self.dialogs = ReplayDialogs(self)

        header = tk.Frame(root, bg=PANEL, padx=self.dp(18), pady=self.dp(10))
        header.grid(row=0, column=0, sticky="ew"); header.grid_columnconfigure(0, weight=1)
        self.title_label = tk.Label(header, text="Algorithmic Expedition", font=self.fonts["title"], bg=PANEL, fg=INK, anchor="w")
        self.title_label.grid(row=0, column=0, sticky="w")
        chooser = tk.Frame(header, bg=PANEL)
        tk.Label(chooser, text="Public demo" if self.public_showcase else "Recording", font=self.fonts["small"], bg=PANEL, fg=MUTED).pack(side="left", padx=(0, self.dp(7)))
        self.demo_var = tk.StringVar(root, value=self.timeline.recording.title)
        self.selector = ttk.Combobox(chooser, textvariable=self.demo_var, state="readonly", width=25,
            font=self.fonts["body"], values=[r.title for r in self.recordings.values()])
        self.selector.pack(side="left"); self.selector.bind("<<ComboboxSelected>>", self._select)
        chooser.grid(row=0, column=1, sticky="e")
        def header_layout(event):
            if event.widget is header:
                stacked = self.title_label.winfo_reqwidth() + chooser.winfo_reqwidth() + self.dp(50) > event.width
                chooser.grid(row=1 if stacked else 0, column=0 if stacked else 1, sticky="w" if stacked else "e",
                             pady=(self.dp(6), 0) if stacked else 0)
        header.bind("<Configure>", header_layout)

        body = tk.Frame(root, bg=BG, padx=self.dp(16), pady=self.dp(10))
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_columnconfigure(0, weight=1); body.grid_rowconfigure(0, weight=1)
        board = tk.Frame(body, bg=BG)
        board.grid(row=0, column=0, sticky="nsew", padx=(0, self.dp(14)))
        board.grid_columnconfigure(0, weight=1); board.grid_rowconfigure(2, weight=1)
        self.board_caption = tk.Label(board, bg=BG, fg=INK, font=self.fonts["strong"], anchor="w")
        self.board_caption.grid(row=0, column=0, sticky="ew", pady=(0, self.dp(5)))
        self.map_controls = tk.Frame(board, bg=BG)
        self.map_controls.grid(row=1, column=0, sticky="ew", pady=(0, self.dp(6)))
        self.map_controls.grid_columnconfigure(4, weight=1)
        self.zoom_out = self.button(self.map_controls, "−", lambda: self.zoom(1 / 1.25), width=2)
        self.zoom_in = self.button(self.map_controls, "+", lambda: self.zoom(1.25), width=2)
        self.fit_button = self.button(self.map_controls, "Fit map", self.fit_map)
        for col, widget in enumerate((self.zoom_out, self.zoom_in, self.fit_button)):
            widget.grid(row=0, column=col, padx=(0, self.dp(5)))
        self.zoom_label = tk.Label(self.map_controls, bg=BG, fg=MUTED, font=self.fonts["small"])
        self.zoom_label.grid(row=0, column=3, padx=self.dp(6))
        self.camera_hint = tk.Label(self.map_controls, text="Drag to pan · Scroll to zoom", bg=BG, fg=MUTED, font=self.fonts["small"])
        self.camera_hint.grid(row=0, column=4, sticky="e")
        self.canvas = tk.Canvas(board, bg=BG, width=1, height=1, highlightthickness=2,
            highlightbackground=BG, highlightcolor=ACCENT, takefocus=True, cursor="hand2")
        self.canvas.grid(row=2, column=0, sticky="nsew")
        self.canvas.bind("<Configure>", self._resize)
        self.canvas.bind("<MouseWheel>", self._wheel)
        self.canvas.bind("<Button-4>", lambda e: self._wheel(e, 1))
        self.canvas.bind("<Button-5>", lambda e: self._wheel(e, -1))
        self.canvas.bind("<ButtonPress-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<ButtonRelease-1>", self._release)
        self.canvas.bind("<KeyPress>", self._map_key)
        self.inspector = ReplaySummary(self, body)
        self.inspector.frame.grid(row=0, column=1, sticky="nsew")

        self.controls = tk.Frame(root, bg=BG, padx=self.dp(16), pady=self.dp(10))
        self.controls.grid(row=2, column=0, sticky="ew")
        self.controls.grid_columnconfigure(0, weight=1)
        self.play_controls = tk.Frame(self.controls, bg=BG)
        self.play_controls.grid(row=0, column=0, sticky="w")
        for column, (name, label, callback) in enumerate((
            ("play", "Play", self.toggle), ("back", "Back", lambda: self.step(-1)),
            ("next", "Next", lambda: self.step(1)), ("restart", "Restart", self.restart), ("end", "End", self.end))):
            button = self.button(self.play_controls, label, callback, primary=name == "play", width=6)
            button.grid(row=0, column=column, padx=(0, self.dp(5))); self.buttons[name] = button
        tk.Label(self.play_controls, text="Speed", bg=BG, fg=MUTED, font=self.fonts["small"]).grid(row=0, column=5, padx=(self.dp(8), self.dp(5)))
        self.speed_var = tk.StringVar(root, value="1x")
        self.speed_selector = ttk.Combobox(self.play_controls, textvariable=self.speed_var, state="readonly", width=5,
            font=self.fonts["body"], values=[str(v).removesuffix(".0") + "x" for v in Timeline.SPEEDS])
        self.speed_selector.grid(row=0, column=6)
        self.speed_selector.bind("<<ComboboxSelected>>", lambda _event: self.set_speed(float(self.speed_var.get()[:-1])))
        self.overlay_controls = tk.Frame(self.controls, bg=BG)
        self.overlay_controls.grid(row=0, column=1, sticky="e")
        self.visited_var, self.coordinates_var = tk.BooleanVar(root, True), tk.BooleanVar(root, True)
        for col, (label, var) in enumerate((("Visited tiles", self.visited_var), ("Grid labels", self.coordinates_var))):
            tk.Checkbutton(self.overlay_controls, text=label, variable=var, command=self.request_draw, bg=BG, fg=INK,
                font=self.fonts["body"], activebackground=BG, highlightcolor=ACCENT, takefocus=True).grid(row=0, column=col)
        self.controls.bind("<Configure>", self._controls_layout)
        for key, callback in (("<space>", self.toggle), ("<Left>", lambda: self.step(-1)),
                              ("<Right>", lambda: self.step(1)), ("<Home>", self.restart), ("<End>", self.end)):
            root.bind(key, lambda event, fn=callback: self._key(event, fn))
        root.update_idletasks()
        self.camera.resize(max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height()))
        self.camera.fit(); self.refresh(); self.draw()

    def _controls_layout(self, event):
        if event.widget is not self.controls: return
        stacked = self.play_controls.winfo_reqwidth() + self.overlay_controls.winfo_reqwidth() + self.dp(45) > event.width
        self.overlay_controls.grid(row=1 if stacked else 0, column=0 if stacked else 1, sticky="w" if stacked else "e",
            pady=(self.dp(7), 0) if stacked else 0)
        self.controls_stacked = stacked

    def _key(self, event, callback):
        # Text, buttons, selectors and every Toplevel keep their native bindings.
        if event.widget is not self.root or self.dialogs.active: return None
        callback(); return "break"

    def _map_key(self, event):
        if self.dialogs.active: return "break"
        keys = {"Left": (-self.dp(40), 0), "Right": (self.dp(40), 0),
                "Up": (0, -self.dp(40)), "Down": (0, self.dp(40))}
        if event.keysym in keys:
            self.camera.pan(*keys[event.keysym]); self.request_draw()
        elif event.keysym in ("plus", "equal", "KP_Add"): self.zoom(1.25)
        elif event.keysym in ("minus", "KP_Subtract"): self.zoom(1 / 1.25)
        elif event.keysym in ("f", "F", "Home"): self.fit_map()
        elif event.keysym == "space": self.toggle()
        else: return None
        return "break"

    def _resize(self, event):
        self.camera.resize(max(1, event.width), max(1, event.height))
        self.board_caption.configure(width=1, wraplength=max(60, event.width - self.dp(6)))
        needed = sum(w.winfo_reqwidth() for w in (self.zoom_out, self.zoom_in, self.fit_button, self.zoom_label, self.camera_hint)) + self.dp(35)
        if needed > event.width: self.camera_hint.grid_remove()
        else: self.camera_hint.grid()
        self.request_draw()

    def _wheel(self, event, direction=None):
        if self.dialogs.active: return "break"
        turns = direction if direction is not None else max(-3, min(3, event.delta / 120))
        if turns: self.zoom(1.25 ** turns, event.x, event.y)
        return "break"

    def _press(self, event):
        if self.dialogs.active: return "break"
        self.canvas.focus_set(); self._drag_point = (event.x, event.y)
        self.canvas.configure(cursor="fleur")
        return "break"

    def _drag(self, event):
        if self._drag_point is not None and not self.dialogs.active:
            x, y = self._drag_point; self.camera.pan(event.x - x, event.y - y)
            self._drag_point = (event.x, event.y); self.request_draw()
        return "break"

    def _release(self, _event=None):
        self._drag_point = None; self.canvas.configure(cursor="hand2")
        return "break"

    def zoom(self, factor, x=None, y=None):
        self.camera.zoom(factor, x, y); self.request_draw()

    def fit_map(self): self.camera.fit(); self.request_draw()

    def request_draw(self):
        if not self.closed and self.root is not None and self.draw_after_id is None:
            self.draw_after_id = self.root.after(16, self._redraw)

    def _redraw(self): self.draw_after_id = None; self.draw()

    def _cancel(self):
        if self.after_id is not None and self.root is not None:
            self.root.after_cancel(self.after_id); self.after_id = None

    def _schedule(self):
        self._cancel()
        if self.timeline.playing and not self.closed and not self.dialogs.active:
            self.after_id = self.root.after(self.timeline.delay_ms, self._tick)

    def _tick(self):
        self.after_id = None
        if self.closed or not self.timeline.playing or self.dialogs.active: return
        self.timeline.tick(); self.refresh(); self._schedule()

    def toggle(self):
        if self.dialogs.active: return
        if self.timeline.playing: self.timeline.pause()
        else: self.timeline.play()
        self.refresh(); self._schedule()

    def step(self, delta):
        self._cancel(); self.timeline.step(delta); self.refresh()

    def seek(self, index):
        self._cancel(); self.timeline.seek(index); self.refresh()

    def restart(self): self.seek(0)

    def end(self): self.seek(len(self.timeline.recording.frames) - 1)

    def set_speed(self, speed):
        self.timeline.set_speed(speed); self._schedule()

    def select(self, name):
        if name == self.selected: return
        self._cancel(); self.timeline.pause()
        self.selected = name; self.timeline = Timeline(self.recordings[name])
        self.timeline.set_speed(float(self.speed_var.get()[:-1]))
        self.demo_var.set(self.timeline.recording.title)
        self.camera = Camera(self.timeline.recording.rows, self.timeline.recording.columns, margin=self.dp(24))
        self.camera.resize(max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height()))
        self.refresh()

    def _select(self, _event):
        names = list(self.recordings)
        self.select(names[self.selector.current()])

    def refresh(self):
        if self.root is None or self.closed: return
        r, f = self.timeline.recording, self.timeline.current
        self.board_caption.configure(text=r.title + f"   ·   Frame {f.index + 1} of {len(r.frames)}")
        self.inspector.refresh(r, f)
        self.buttons["play"].configure(text="Pause" if self.timeline.playing else "Play",
            state="disabled" if self.dialogs.active else "normal")
        self.buttons["back"].configure(state="disabled" if f.index == 0 else "normal")
        self.buttons["next"].configure(state="disabled" if self.timeline.at_end else "normal")
        self.request_draw()

    def _sprite(self, name, position, state="idle", direction="south"):
        x, y, x2, y2 = self.camera.box(*position)
        width, height = x2 - x, y2 - y
        if width <= 0 or height <= 0 or x2 < 0 or y2 < 0 or x > self.camera.width or y > self.camera.height: return
        photo = self.bank.at_size(name, state, direction, width, height)
        if photo is not None:
            self.frame_photos.append(photo); self.canvas.create_image(x, y, image=photo, anchor="nw"); return
        colors = {"floor": "#e9e2d2", "wall": "#344d50", "start": "#54789c", "exit": "#58ae82",
                  "artifact": "#e9bb55", "enemy": "#bf6c57", "explorer": "#318c86"}
        if name in ("floor", "wall"):
            self.canvas.create_rectangle(x, y, x2, y2, fill=colors[name], outline="")
            if width >= 24:
                self.canvas.create_line(x, y, x2, y, fill="#294346" if name == "wall" else "#d6cbb5")
            return
        size = min(width, height)
        if size < 24:
            inset = min(2, size / 8)
            color = "#a95042" if name == "explorer" and state == "failed" else colors[name]
            self.canvas.create_oval(x + inset, y + inset, x2 - inset, y2 - inset, fill=color, outline="")
        else:
            placeholder(self.canvas, name, x + (width - size) / 2, y + (height - size) / 2,
                        size, state=state, direction=direction)

    def draw(self):
        if self.canvas is None or self.closed or self.bank is None: return
        if self.draw_after_id is not None:
            self.root.after_cancel(self.draw_after_id); self.draw_after_id = None
        r, f, c, camera = self.timeline.recording, self.timeline.current, self.canvas, self.camera
        self.draw_count += 1
        c.delete("all"); self.frame_photos = []
        rows, columns = camera.visible()
        self.rendered_cells = len(rows) * len(columns)
        for row in rows:
            for column in columns: self._sprite("floor" if r.terrain[row][column] == "." else "wall", (row, column))
        size = CELL * camera.scale
        self.display_cell_size = size
        if self.visited_var.get():
            for position in f.visited:
                row, column = position
                if row not in rows or column not in columns: continue
                x, y, x2, y2 = camera.box(row, column)
                pad = min(2, (x2 - x) / 8, (y2 - y) / 8)
                c.create_rectangle(x + pad, y + pad, x2 - pad, y2 - pad, fill="#c9ded2", outline="")
                if size >= 24: c.create_oval(x + size * .46, y + size * .46, x + size * .54, y + size * .54, fill="#88b4a6", outline="")
        self._sprite("start", r.start)
        self._sprite("exit", r.exit, "accepted" if f.completed else "available")
        for artifact in f.artifacts: self._sprite("artifact", artifact.position, "available")
        for enemy in f.enemies:
            self._sprite("enemy", enemy.position, direction=enemy.direction)
            if enemy.patrol:
                x, y, x2, y2 = camera.box(*enemy.position)
                if size >= 12:
                    c.create_oval(x + 2, y + 2, x2 - 2, y2 - 2, outline="#7c5e88", width=2, dash=(4, 3))
                if size >= 28: c.create_text(x2 - 5, y + 5, text="P", anchor="ne", fill="#684577", font=self.fonts["small"])
        self._sprite("explorer", f.position, f.pose, f.direction)
        x, y, x2, y2 = camera.box(*f.position)
        if size >= 28 and f.position[0] in rows and f.position[1] in columns:
            # Occupied endpoint captions sit outside the sprite, including at
            # 32px source size. Keep the overlay readable against either terrain.
            def endpoint_caption(text, color):
                item = c.create_text((x + x2) / 2, y2 + self.dp(3), text=text,
                    anchor="n", fill=color, font=self.fonts["small"], tags=("occupied-endpoint",))
                bounds = c.bbox(item)
                if bounds[3] + 2 > camera.height:
                    c.itemconfigure(item, anchor="s")
                    c.coords(item, (x + x2) / 2, y - self.dp(3))
                    bounds = c.bbox(item)
                shift = max(3 - bounds[0], min(0, camera.width - 3 - bounds[2]))
                if shift: c.move(item, shift, 0); bounds = c.bbox(item)
                if bounds[1] < 2 or bounds[3] > camera.height - 2 or bounds[2] > camera.width - 2:
                    c.delete(item); return
                background = c.create_rectangle(bounds[0] - 2, bounds[1] - 1,
                    bounds[2] + 2, bounds[3] + 1, fill=PANEL, outline="",
                    tags=("occupied-endpoint-background",))
                c.tag_lower(background, item)
            if f.position == r.start: endpoint_caption("Start", "#355e85")
            if f.position == r.exit: endpoint_caption("Exit accepted" if f.completed else "Exit", "#164a34")
            if any(a.position == f.position for a in f.artifacts):
                c.create_rectangle(x2 - self.dp(15), y + 1, x2 - 1, y + self.dp(16), fill="#f0ce78", outline="")
                c.create_text(x2 - 3, y + 2, text="A", anchor="ne", fill="#80531c", font=self.fonts["small"])
        if f.status not in ("RUNNING", "COMPLETED"):
            c.create_rectangle(x + 1, y + 1, x2 - 1, y2 - 1, outline="#a94d3e", width=2)
        if self.coordinates_var.get() and size >= 28:
            font = self.fonts["small"]
            left = max(font.measure(str(r.rows - 1)) + self.dp(4), camera.x - self.dp(5))
            top = max(font.metrics("linespace") + self.dp(4), camera.y - self.dp(6))
            def coordinate(x, y, text, anchor):
                item = c.create_text(x, y, text=text, anchor=anchor, fill=MUTED, font=font)
                bounds = c.bbox(item)
                # Partial edge cells remain visible, but their labels must not be clipped.
                if bounds and (bounds[0] < 0 or bounds[1] < 0 or bounds[2] > camera.width or bounds[3] > camera.height):
                    c.delete(item)
            for row in rows:
                coordinate(left, camera.y + (row + .5) * size, str(row), "e")
            for column in columns:
                coordinate(camera.x + (column + .5) * size, top, str(column), "s")
        c.create_rectangle(round(camera.x), round(camera.y), round(camera.x + r.columns * size),
                           round(camera.y + r.rows * size), outline="#294346", width=1)
        self.zoom_label.configure(text=f"{camera.scale * 100:.1f}% source")
        self.zoom_out.configure(state="disabled" if camera.scale <= camera.fit_scale * (1 + 1e-8) else "normal")
        self.zoom_in.configure(state="disabled" if camera.scale >= MAX_SCALE else "normal")

    def close(self):
        if self.closed: return
        self.timeline.pause(); self._cancel(); self.closed = True
        if self.root is not None:
            if self.draw_after_id is not None: self.root.after_cancel(self.draw_after_id); self.draw_after_id = None
            if self.dialogs is not None: self.dialogs.destroy()
            self.root.destroy()
