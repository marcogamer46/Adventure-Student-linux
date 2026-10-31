"""One reusable events window and one scoring window, using detached values only."""
from .formatting import event_groups, scoring_text, technical_text


class ReplayDialogs:
    def __init__(self, app):
        self.app = app
        self.windows = {}
        self.texts = {}
        self.launchers = {}
        self.technical_visible = False

    @property
    def active(self):
        return any(window.state() != "withdrawn" for window in self.windows.values())

    def _window(self, kind, heading, launcher):
        app, tk = self.app, self.app.tk
        self.launchers[kind] = launcher
        if kind in self.windows:
            window = self.windows[kind]
            window.deiconify(); window.lift()
            return window, self.texts[kind]
        from tkinter import ttk
        window = tk.Toplevel(app.root)
        window.withdraw(); window.title(heading); window.transient(app.root)
        window.geometry("820x600"); window.minsize(480, 350)
        window.configure(bg=app.PANEL)
        window.grid_columnconfigure(0, weight=1); window.grid_rowconfigure(2, weight=1)
        tk.Label(window, text=heading, bg=app.PANEL, fg=app.INK, font=app.fonts["heading"], anchor="w").grid(
            row=0, column=0, sticky="ew", padx=20, pady=(16, 4))
        scope = "Recorded events through the selected frame" if kind == "events" else "Final run result — entire recording"
        tk.Label(window, text=scope, bg=app.PANEL, fg=app.MUTED, font=app.fonts["body"], anchor="w").grid(
            row=1, column=0, sticky="ew", padx=20, pady=(0, 12))
        content = tk.Frame(window, bg=app.PANEL)
        content.grid(row=2, column=0, sticky="nsew", padx=20)
        content.grid_columnconfigure(0, weight=1); content.grid_rowconfigure(0, weight=1)
        text = tk.Text(content, wrap="word", state="disabled", bg=app.PANEL, fg=app.INK,
            font=app.fonts["body"], padx=10, pady=8, relief="solid", bd=1, highlightthickness=1,
            highlightcolor=app.ACCENT, selectbackground="#c9ded2", spacing3=5, takefocus=True)
        text.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(content, orient="vertical", command=text.yview)
        scroll.grid(row=0, column=1, sticky="ns"); text.configure(yscrollcommand=scroll.set)
        text.tag_configure("selected", background="#dbece3", foreground=app.INK)
        text.tag_configure("heading", font=app.fonts["strong"])
        text.tag_configure("technical", font=app.fonts["technical"])
        footer = tk.Frame(window, bg=app.PANEL)
        footer.grid(row=3, column=0, sticky="ew", padx=20, pady=12); footer.grid_columnconfigure(0, weight=1)
        if kind == "events":
            self.technical_button = app.button(footer, "Show Technical details", self._technical)
            self.technical_button.grid(row=0, column=0, sticky="w")
        close = app.button(footer, "Close", lambda: self.close(kind)); close.grid(row=0, column=1, sticky="e")
        # Toplevel is its own bindtag boundary: no root or bind_all shortcuts.
        window.bind("<Escape>", lambda _event: self.close(kind) or "break")
        window.protocol("WM_DELETE_WINDOW", lambda: self.close(kind))
        self.windows[kind] = window; self.texts[kind] = text
        window.deiconify()
        return window, text

    def _pause(self):
        self.app.timeline.pause(); self.app._cancel(); self.app.refresh()

    def events(self, launcher):
        self._pause()
        window, text = self._window("events", "Recorded Events", launcher)
        self._event_text()
        window.lift(); window.grab_set(); text.focus_set(); self.app.refresh()

    def _event_text(self):
        app, text = self.app, self.texts["events"]
        text.configure(state="normal"); text.delete("1.0", "end")
        selected = "1.0"
        for index, (heading, lines) in enumerate(event_groups(app.timeline.recording, app.timeline.index)):
            start = text.index("end-1c")
            text.insert("end", heading + "\n", "heading")
            text.insert("end", "\n".join(lines) + "\n\n")
            if index == app.timeline.index:
                selected = start; text.tag_add("selected", start, "end-1c")
        if self.technical_visible:
            text.insert("end", "Technical details — selected frame\n", "heading")
            text.insert("end", technical_text(app.timeline.recording, app.timeline.current) + "\n", "technical")
            text.insert("end", f"\nAsset source contract: {app.bank.source_version or 'unavailable'}; viewport adapter: {app.bank.adapter}\n")
            text.insert("end", "\n".join(app.bank.warnings + ([app.bank.display_notice] if app.bank.display_notice else [])))
        text.configure(state="disabled"); text.see(selected)
        self.selected_event_start = selected
        self.technical_button.configure(text="Hide Technical details" if self.technical_visible else "Show Technical details")

    def _technical(self):
        self.technical_visible = not self.technical_visible
        self._event_text()
        if self.technical_visible: self.texts["events"].see("end")

    def scoring(self, launcher):
        self._pause()
        window, text = self._window("scoring", "Scoring details", launcher)
        text.configure(state="normal"); text.delete("1.0", "end")
        text.insert("1.0", scoring_text(self.app.timeline.recording)); text.configure(state="disabled")
        text.yview_moveto(0); window.lift(); window.grab_set(); text.focus_set(); self.app.refresh()

    def close(self, kind):
        self.windows[kind].grab_release()
        self.windows[kind].withdraw()
        self.launchers[kind].focus_set()
        # Closing does not schedule playback or change the selected frame/camera.
        self.app.refresh()

    def destroy(self):
        for window in self.windows.values(): window.destroy()
        self.windows.clear(); self.texts.clear()
