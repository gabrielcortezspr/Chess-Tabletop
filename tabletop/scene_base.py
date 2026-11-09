"""Base comum das mesas (xadrez e Go)."""
from __future__ import annotations

from .fx import Particles


class SceneBase:
    name = ""
    theme = ((0.87, 0.27, 0.23), (0.0, 0.42, 0.71), (0.09, 0.14, 0.15))

    def __init__(self):
        self.time = 0.0
        self.mode = "jogo"
        self.hover = None
        self.particles = Particles()
        self.events: list = []        # consumidos pelo App: shake, popup, banner, sheen
        self.message = ("", -10.0)

    def toast(self, text):
        self.message = (text, self.time)

    def emit(self, *event):
        self.events.append(event)

    def drain_events(self):
        ev, self.events = self.events, []
        return ev

    def update(self, dt):
        self.time += dt
        self.particles.update(dt)

    def held_sprite(self):
        return None
