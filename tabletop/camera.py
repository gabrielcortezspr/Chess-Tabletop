"""Câmera orbital: livre para girar/aproximar/deslocar, mas sempre focada no tabuleiro."""
from __future__ import annotations

import math

import numpy as np


def perspective(fovy_deg, aspect, near, far):
    f = 1.0 / math.tan(math.radians(fovy_deg) / 2)
    m = np.zeros((4, 4), dtype=np.float64)
    m[0, 0] = f / aspect
    m[1, 1] = f
    m[2, 2] = (far + near) / (near - far)
    m[2, 3] = 2 * far * near / (near - far)
    m[3, 2] = -1
    return m


def ortho(l, r, b, t, n, f):
    m = np.identity(4)
    m[0, 0] = 2 / (r - l)
    m[1, 1] = 2 / (t - b)
    m[2, 2] = -2 / (f - n)
    m[0, 3] = -(r + l) / (r - l)
    m[1, 3] = -(t + b) / (t - b)
    m[2, 3] = -(f + n) / (f - n)
    return m


def look_at(eye, target, up=(0, 1, 0)):
    eye, target, up = (np.asarray(v, dtype=np.float64) for v in (eye, target, up))
    fwd = target - eye
    fwd /= np.linalg.norm(fwd)
    side = np.cross(fwd, up)
    side /= np.linalg.norm(side)
    upv = np.cross(side, fwd)
    m = np.identity(4)
    m[0, :3], m[1, :3], m[2, :3] = side, upv, -fwd
    m[0, 3], m[1, 3], m[2, 3] = -side @ eye, -upv @ eye, fwd @ eye
    return m


def gl_bytes(m):
    """numpy usa linha-maior; OpenGL espera coluna-maior."""
    return np.ascontiguousarray(m.T, dtype=np.float32).tobytes()


def _lerp_angle(a, b, t):
    d = (b - a + 180) % 360 - 180
    return a + d * t


class OrbitCamera:
    MIN_PITCH, MAX_PITCH = 12.0, 88.0
    MIN_DIST, MAX_DIST = 5.0, 30.0

    def __init__(self, focus_radius=6.0):
        self.focus_radius = focus_radius
        self.fov = 40.0
        self.home()
        self.yaw, self.pitch, self.dist = self.t_yaw, self.t_pitch, self.t_dist
        self.target = self.t_target.copy()

    def home(self, yaw=0.0):
        self.t_yaw = yaw
        self.t_pitch = 52.0
        self.t_dist = 15.0
        self.t_target = np.array([0.0, 0.0, 0.5], dtype=np.float64)

    def orbit(self, dx, dy):
        self.t_yaw -= dx * 0.35
        self.t_pitch = min(self.MAX_PITCH, max(self.MIN_PITCH, self.t_pitch + dy * 0.3))

    def zoom(self, steps):
        self.t_dist = min(self.MAX_DIST, max(self.MIN_DIST, self.t_dist * (0.9 ** steps)))

    def pan(self, dx, dy):
        """Desloca o alvo no plano da mesa, preso perto do tabuleiro."""
        yaw = math.radians(self.yaw)
        right = np.array([math.cos(yaw), 0, -math.sin(yaw)])
        fwd = np.array([-math.sin(yaw), 0, -math.cos(yaw)])
        k = self.dist * 0.0018
        self.t_target += right * (-dx * k) + fwd * (dy * k)
        r = np.linalg.norm(self.t_target[[0, 2]])
        if r > self.focus_radius:
            self.t_target[[0, 2]] *= self.focus_radius / r

    def update(self, dt):
        t = 1 - math.exp(-dt * 12)
        self.yaw = _lerp_angle(self.yaw, self.t_yaw, t)
        self.pitch += (self.t_pitch - self.pitch) * t
        self.dist += (self.t_dist - self.dist) * t
        self.target += (self.t_target - self.target) * t

    @property
    def eye(self):
        yaw, pitch = math.radians(self.yaw), math.radians(self.pitch)
        off = np.array([math.sin(yaw) * math.cos(pitch), math.sin(pitch), math.cos(yaw) * math.cos(pitch)])
        return self.target + off * self.dist

    def view(self):
        return look_at(self.eye, self.target)

    def proj(self, aspect):
        return perspective(self.fov, aspect, 0.1, 120.0)

    def ray(self, mx, my, w, h):
        """Raio (origem, direção) saindo do pixel (mx, my) da janela."""
        x = 2 * mx / w - 1
        y = 1 - 2 * my / h
        inv = np.linalg.inv(self.proj(w / h) @ self.view())
        p0 = inv @ np.array([x, y, -1, 1])
        p1 = inv @ np.array([x, y, 1, 1])
        p0, p1 = p0[:3] / p0[3], p1[:3] / p1[3]
        d = p1 - p0
        return p0, d / np.linalg.norm(d)

    def pick_plane(self, mx, my, w, h, plane_y=0.0):
        o, d = self.ray(mx, my, w, h)
        if abs(d[1]) < 1e-6:
            return None
        t = (plane_y - o[1]) / d[1]
        if t < 0:
            return None
        return o + d * t
