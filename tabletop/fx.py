"""Efeitos de "juice": partículas, textos que pulam, tremida de tela, easing."""
from __future__ import annotations

import math
import random

import pygame


def clamp(v, a, b):
    return a if v < a else b if v > b else v


def ease_out_back(t, s=1.7):
    t = clamp(t, 0.0, 1.0) - 1
    return t * t * ((s + 1) * t + s) + 1


def ease_out_cubic(t):
    t = clamp(t, 0.0, 1.0)
    return 1 - (1 - t) ** 3


def ease_out_elastic(t):
    t = clamp(t, 0.0, 1.0)
    if t in (0.0, 1.0):
        return t
    return 2 ** (-10 * t) * math.sin((t * 10 - 0.75) * (2 * math.pi / 3)) + 1


def ease_in_out(t):
    t = clamp(t, 0.0, 1.0)
    return t * t * (3 - 2 * t)


class Particle:
    __slots__ = ("x", "y", "vx", "vy", "life", "max_life", "color", "size", "gravity")

    def __init__(self, x, y, vx, vy, life, color, size=1, gravity=180.0):
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.life = self.max_life = life
        self.color, self.size, self.gravity = color, size, gravity


class Particles:
    def __init__(self):
        self.items: list[Particle] = []

    def burst_sprite(self, sprite, x, y, power=60.0):
        """Desmancha um sprite em partículas (um pixel = uma partícula)."""
        w, h = sprite.get_size()
        for py in range(h):
            for px in range(w):
                c = sprite.get_at((px, py))
                if c.a < 128:
                    continue
                ang = random.uniform(0, math.tau)
                sp = random.uniform(0.3, 1.0) * power
                self.items.append(Particle(x + px - w / 2, y + py - h / 2, math.cos(ang) * sp,
                                           math.sin(ang) * sp - power * 0.8, random.uniform(0.5, 1.1),
                                           (c.r, c.g, c.b)))

    def dust(self, x, y, color=(255, 240, 200), n=8):
        for _ in range(n):
            ang = random.uniform(math.pi * 0.9, math.pi * 2.1)
            sp = random.uniform(15, 40)
            self.items.append(Particle(x, y, math.cos(ang) * sp, math.sin(ang) * sp * 0.4, random.uniform(0.2, 0.45),
                                       color, 1, 40.0))

    def confetti(self, x, y, w, n=90):
        cols = [(254, 95, 85), (0, 157, 255), (255, 210, 70), (80, 220, 140), (255, 255, 255)]
        for _ in range(n):
            self.items.append(Particle(x + random.uniform(0, w), y + random.uniform(-10, 0), random.uniform(-30, 30),
                                       random.uniform(-40, 40), random.uniform(1.2, 2.4),
                                       random.choice(cols), random.choice((1, 2)), 60.0))

    def update(self, dt):
        alive = []
        for p in self.items:
            p.life -= dt
            if p.life <= 0:
                continue
            p.vy += p.gravity * dt
            p.x += p.vx * dt
            p.y += p.vy * dt
            alive.append(p)
        self.items = alive

    def draw(self, surf):
        for p in self.items:
            if p.life < p.max_life * 0.3 and int(p.life * 30) % 2:
                continue   # pisca antes de sumir
            if p.size == 1:
                if 0 <= p.x < surf.get_width() and 0 <= p.y < surf.get_height():
                    surf.set_at((int(p.x), int(p.y)), p.color)
            else:
                surf.fill(p.color, (int(p.x), int(p.y), p.size, p.size))


class Popup:
    """Texto que salta e sobe (estilo pontuação de cartas)."""

    def __init__(self, text, x, y, color, big=False):
        self.text, self.x, self.y, self.color, self.big = text, x, y, color, big
        self.t = 0.0
        self.life = 1.2

    @property
    def alive(self):
        return self.t < self.life


class Shake:
    def __init__(self):
        self.amount = 0.0

    def kick(self, amount):
        self.amount = max(self.amount, amount)

    def update(self, dt):
        self.amount *= math.exp(-dt * 9)
        if self.amount < 0.05:
            self.amount = 0.0

    def offset(self):
        if not self.amount:
            return 0.0, 0.0, 0.0
        a = self.amount
        return random.uniform(-a, a), random.uniform(-a, a), random.uniform(-a, a) * 0.004


class Bump:
    """Escala que 'pula' quando um valor muda (números do placar)."""

    def __init__(self):
        self.values = {}

    def scale(self, key, value, now):
        old = self.values.get(key)
        if old is None or old[0] != value:
            self.values[key] = (value, now if old is not None else -10.0)
            old = self.values[key]
        dt = now - old[1]
        if dt > 0.45:
            return 1.0
        return 1.0 + 0.45 * (1 - ease_out_cubic(dt / 0.45)) * abs(math.cos(dt * 18))


def wobble_text(surf, font, text, x, y, color, t, amp=2.0, shadow=(20, 16, 30), center=False, scale=1.0):
    """Texto com letras ondulando (cada letra com uma fase)."""
    glyphs = [font.render(ch, False, color) for ch in text]
    shadows = [font.render(ch, False, shadow) for ch in text]
    if scale != 1.0:
        glyphs = [pygame.transform.scale_by(g, scale) for g in glyphs]
        shadows = [pygame.transform.scale_by(g, scale) for g in shadows]
    total = sum(g.get_width() for g in glyphs)
    cx = x - total // 2 if center else x
    for i, (g, s) in enumerate(zip(glyphs, shadows)):
        dy = round(math.sin(t * 4 + i * 0.6) * amp)
        surf.blit(s, (cx + 1, y + dy + 2))
        surf.blit(g, (cx, y + dy))
        cx += g.get_width()
    return total
