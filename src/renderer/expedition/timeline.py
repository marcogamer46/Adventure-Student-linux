"""Navigation and playback timing over a frozen recording, independent of Tk."""
import math
from .model import Recording


class Timeline:
    SPEEDS = (0.25, 0.5, 1.0, 2.0, 4.0)

    def __init__(self, recording):
        if type(recording) is not Recording: raise TypeError("PRESENTATION_RECORDING_REQUIRED")
        self.recording = recording
        self.index = 0
        self.playing = False
        self.speed = 1.0

    @property
    def current(self): return self.recording.frames[self.index]

    @property
    def at_end(self): return self.index == len(self.recording.frames) - 1

    @property
    def delay_ms(self): return round(700 / self.speed)

    def pause(self): self.playing = False

    def seek(self, index):
        if type(index) is not int or not 0 <= index < len(self.recording.frames):
            raise ValueError("PRESENTATION_FRAME_RANGE")
        self.pause()
        self.index = index
        return self.current

    def step(self, delta):
        if type(delta) is not int or delta not in (-1, 1): raise ValueError("PRESENTATION_STEP")
        return self.seek(max(0, min(self.index + delta, len(self.recording.frames) - 1)))

    def restart(self): return self.seek(0)

    def play(self):
        if self.at_end: self.index = 0
        self.playing = len(self.recording.frames) > 1

    def tick(self):
        if self.playing and not self.at_end: self.index += 1
        if self.at_end: self.pause()
        return self.current

    def set_speed(self, value):
        if type(value) not in (int, float) or not math.isfinite(value) or value not in self.SPEEDS:
            raise ValueError("PRESENTATION_SPEED")
        self.speed = float(value)
