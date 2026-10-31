"""Current-frame cards and separately labeled, immutable final-run values."""
from .formatting import compact_value, current_cards, current_status, final_cards, friendly_action, metric


class ReplaySummary:
    def __init__(self, app, parent):
        tk = app.tk
        self.app = app
        self.frame = tk.Frame(parent, bg=app.PANEL, padx=app.dp(14), pady=app.dp(7), width=app.dp(328))
        self.frame.grid_columnconfigure(0, weight=1)
        self.frame.grid_propagate(False)
        self.wrapped = []
        self.cards = {}
        def label(text, font="body", color=None, **kwargs):
            widget = tk.Label(self.frame, text=text, font=app.fonts[font], bg=app.PANEL, fg=color or app.INK,
                              anchor="w", justify="left", padx=0, pady=0, **kwargs)
            self.wrapped.append(widget)
            return widget
        label("Replay Summary", "heading").grid(row=0, column=0, sticky="ew", pady=(0, app.dp(4)))
        label("Current frame", "small", app.MUTED).grid(row=1, column=0, sticky="ew")
        self.action = label("", "strong"); self.action.grid(row=2, column=0, sticky="ew", pady=(app.dp(3), 0))
        self.position = label("", "small", app.MUTED); self.position.grid(row=3, column=0, sticky="ew")
        self.status = label("", "body"); self.status.grid(row=4, column=0, sticky="ew", pady=(app.dp(3), app.dp(5)))
        self.current_grid = tk.Frame(self.frame, bg=app.PANEL)
        self.current_grid.grid(row=5, column=0, sticky="ew")
        for index, name in enumerate(("Turn", "Artifacts remaining", "Enemies present", "Tiles visited")):
            self._card(self.current_grid, name, index)
        label("Final run result — entire recording", "small", app.MUTED).grid(
            row=6, column=0, sticky="ew", pady=(app.dp(5), app.dp(3)))
        self.score = label("", "strong", app.ACCENT); self.score.grid(row=7, column=0, sticky="ew", pady=(0, app.dp(4)))
        self.final_grid = tk.Frame(self.frame, bg=app.PANEL); self.final_grid.grid(row=8, column=0, sticky="ew")
        for index, name in enumerate(("Total cost", "Artifact points")): self._card(self.final_grid, name, index)
        launches = tk.Frame(self.frame, bg=app.PANEL)
        launches.grid(row=9, column=0, sticky="ew", pady=(app.dp(5), 0))
        launches.grid_columnconfigure(0, weight=1)
        self.events_button = app.button(launches, "Show Recorded Events", lambda: app.dialogs.events(self.events_button))
        self.events_button.grid(row=0, column=0, sticky="ew", padx=(0, app.dp(4)))
        self.scoring_button = app.button(launches, "Scoring details", lambda: app.dialogs.scoring(self.scoring_button))
        self.scoring_button.grid(row=0, column=1, sticky="ew")
        self.events_button.configure(pady=app.dp(2))
        self.scoring_button.configure(pady=app.dp(2))
        self.frame.grid_rowconfigure(10, weight=1)
        self.note = label("Demonstration replay — not a course grade", "small", app.MUTED)
        self.note.grid(row=11, column=0, sticky="ew", pady=(app.dp(6), 0))
        self.frame.bind("<Configure>", self._wrap)

    def _card(self, parent, name, index):
        app, tk = self.app, self.app.tk
        parent.grid_columnconfigure(0, weight=1, uniform="cards")
        parent.grid_columnconfigure(1, weight=1, uniform="cards")
        tile = tk.Frame(parent, bg="#eeeade", padx=app.dp(9), pady=app.dp(1))
        tile.grid(row=index // 2, column=index % 2, sticky="nsew", padx=(0, app.dp(4)) if index % 2 == 0 else (app.dp(4), 0),
                  pady=(0, app.dp(2)))
        tile.grid_columnconfigure(0, weight=1)
        title = tk.Label(tile, text=name, bg="#eeeade", fg=app.MUTED, font=app.fonts["small"], anchor="w", justify="left", padx=0, pady=0)
        title.grid(row=0, column=0, sticky="ew")
        value = tk.Label(tile, bg="#eeeade", fg=app.INK, font=app.fonts["value"], anchor="w", justify="left", padx=0, pady=0)
        value.grid(row=1, column=0, sticky="ew")
        tile.bind("<Configure>", lambda event: title.configure(wraplength=max(20, event.width - app.dp(18))))
        self.cards[name] = value

    def _wrap(self, event):
        width = max(80, event.width - self.app.dp(28))
        for label in self.wrapped: label.configure(wraplength=width)

    def refresh(self, recording, frame):
        self.action.configure(text=friendly_action(frame))
        self.position.configure(text=f"Row {frame.position[0]}, column {frame.position[1]}")
        self.status.configure(text=current_status(frame, recording),
            fg="#9c4136" if frame.status not in ("RUNNING", "COMPLETED") else self.app.ACCENT)
        for name, value in (*current_cards(frame), *final_cards(recording)):
            # Large numbers are identified, never silently cropped or replaced by zero.
            display = compact_value(value)
            self.cards[name].configure(text=display,
                font=self.app.fonts["body"] if display.startswith("Not ") else self.app.fonts["value"])
        self.score.configure(text="Final score: " + compact_value(metric(recording, "score")))
