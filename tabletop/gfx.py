"""Pipeline gráfico 2D com shaders (moderngl).

1. Fundo: tinta girando em espiral (shader procedural, pixelado).
2. Tabuleiro: uma "carta" 2D em pixel art com inclinação pseudo-3D
   (perspectiva), sombra projetada, espessura e brilho tipo foil.
3. Camada de HUD/efeitos desenhada com pygame.
4. Pós-processamento CRT: curvatura, aberração cromática, scanlines,
   vinheta, brilho e granulado.

Tudo é desenhado num "canvas" de baixa resolução (360 px de altura) e
ampliado sem suavização, para manter os pixels grossos.
"""
from __future__ import annotations

import math

import moderngl
import numpy as np

CANVAS_H = 360
CRT_CURVE = 0.10

QUAD_VS = """
#version 330
in vec2 in_pos;
out vec2 v_uv;
void main() {
    v_uv = in_pos * 0.5 + 0.5;
    gl_Position = vec4(in_pos, 0.0, 1.0);
}
"""

BG_FS = """
#version 330
uniform float u_time;
uniform vec2 u_res;
uniform vec3 u_c1;
uniform vec3 u_c2;
uniform vec3 u_c3;
out vec4 f_color;

void main() {
    // pixelado em blocos de 2 px do canvas
    vec2 px = floor(gl_FragCoord.xy / 2.0) * 2.0;
    vec2 uv = (px - 0.5 * u_res) / length(u_res);
    float r = length(uv);
    // redemoinho: o ângulo gira mais perto do centro
    float ang = atan(uv.y, uv.x) + u_time * 0.12 - 5.0 * (0.25 * r + 0.75);
    vec2 p = vec2(cos(ang), sin(ang)) * r * 28.0;
    float t = u_time * 0.9;
    vec2 q = vec2(p.x + p.y);
    for (int i = 0; i < 5; i++) {
        q += sin(max(p.x, p.y)) + p;
        p += 0.5 * vec2(cos(5.11 + 0.353 * q.y + t * 0.131), sin(q.x - 0.113 * t));
        p -= cos(p.x + p.y) - sin(p.x * 0.711 - p.y);
    }
    float contrast = 2.2;
    float paint = clamp(length(p) * 0.035 * contrast, 0.0, 2.0);
    float a = max(0.0, 1.0 - contrast * abs(1.0 - paint));
    float b = max(0.0, 1.0 - contrast * abs(paint));
    float c = 1.0 - min(1.0, a + b);
    vec3 col = u_c1 * a + u_c2 * b + u_c3 * c;
    col += 0.25 * max(a * 5.0 - 4.0, 0.0) + 0.35 * max(b * 5.0 - 4.0, 0.0);
    col = mix(col, u_c3, 0.12);
    f_color = vec4(col, 1.0);
}
"""

CARD_VS = """
#version 330
in vec4 in_clip;
in vec2 in_uv;
out vec2 v_uv;
void main() {
    v_uv = in_uv;
    gl_Position = in_clip;
}
"""

CARD_FS = """
#version 330
in vec2 v_uv;
uniform sampler2D u_tex;
uniform vec2 u_texsize;
uniform int u_mode;          // 0 = textura, 1 = cor sólida na forma da textura
uniform vec4 u_color;
uniform float u_sheen;       // posição da faixa de brilho
uniform float u_light;       // leve variação de luz pela inclinação
out vec4 f_color;
void main() {
    vec4 t = texture(u_tex, v_uv);
    if (t.a < 0.5) discard;
    if (u_mode == 1) {
        f_color = vec4(u_color.rgb, u_color.a);
        return;
    }
    vec2 puv = (floor(v_uv * u_texsize) + 0.5) / u_texsize;   // alinhado aos pixels
    float d = puv.x * 0.8 + puv.y * 0.5 - u_sheen;
    float band = step(abs(d), 0.035) * 0.22 + step(abs(d - 0.07), 0.012) * 0.14;
    vec3 col = t.rgb * u_light + band;
    f_color = vec4(col, 1.0);
}
"""

OVERLAY_FS = """
#version 330
in vec2 v_uv;
uniform sampler2D u_tex;
out vec4 f_color;
void main() {
    f_color = texture(u_tex, v_uv);
}
"""

POST_FS = """
#version 330
in vec2 v_uv;
uniform sampler2D u_tex;
uniform vec2 u_canvas;
uniform float u_time;
uniform float u_curve;
uniform float u_crt;
out vec4 f_color;

float rand(vec2 co) { return fract(sin(dot(co, vec2(12.9898, 78.233))) * 43758.5453); }

void main() {
    vec2 cc = v_uv - 0.5;
    float d = dot(cc, cc);
    vec2 uv = 0.5 + cc * (1.0 + u_curve * d);
    if (uv.x < 0.0 || uv.x > 1.0 || uv.y < 0.0 || uv.y > 1.0) {
        f_color = vec4(0.0, 0.0, 0.0, 1.0);
        return;
    }
    vec2 off = cc * d * 0.022 * u_crt;   // aberração cresce nas bordas
    vec3 col;
    col.r = texture(u_tex, uv + off).r;
    col.g = texture(u_tex, uv).g;
    col.b = texture(u_tex, uv - off).b;
    // brilho suave (bloom barato)
    vec2 px = 1.0 / u_canvas;
    vec3 glow = texture(u_tex, uv + vec2(px.x, 0)).rgb + texture(u_tex, uv - vec2(px.x, 0)).rgb
              + texture(u_tex, uv + vec2(0, px.y)).rgb + texture(u_tex, uv - vec2(0, px.y)).rgb;
    glow *= 0.25;
    col += max(glow - 0.6, 0.0) * 0.5 * u_crt;
    // scanlines na grade do canvas
    float line = 0.5 + 0.5 * cos(uv.y * u_canvas.y * 6.28318);
    col *= mix(1.0, 0.82 + 0.18 * line, u_crt);
    // vinheta e granulado
    col *= 1.0 - d * 1.1 * u_crt;
    col += (rand(uv * u_canvas + u_time) - 0.5) * 0.035 * u_crt;
    f_color = vec4(col, 1.0);
}
"""


def homography(src, dst):
    """Matriz 3x3 que leva os 4 pontos `src` para `dst`."""
    a, b = [], []
    for (x, y), (u, v) in zip(src, dst):
        a.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        b.append(u)
        a.append([0, 0, 0, x, y, 1, -v * x, -v * y])
        b.append(v)
    h = np.linalg.solve(np.array(a, dtype=np.float64), np.array(b, dtype=np.float64))
    return np.append(h, 1.0).reshape(3, 3)


def apply_h(h, x, y):
    p = h @ np.array([x, y, 1.0])
    return p[0] / p[2], p[1] / p[2]


class CardView:
    """Projeta o tabuleiro (um retângulo) com inclinação pseudo-3D no canvas."""

    def __init__(self):
        self.center = (0.0, 0.0)
        self.size = (1.0, 1.0)
        self.pitch = 0.0
        self.yaw = 0.0
        self.roll = 0.0
        self.focal = 600.0
        self._h = None
        self._hinv = None
        self.corners = []

    def project_local(self, x, y):
        cr, sr = math.cos(self.roll), math.sin(self.roll)
        x, y = x * cr - y * sr, x * sr + y * cr
        cp, sp = math.cos(self.pitch), math.sin(self.pitch)
        z = -y * sp
        y = y * cp
        cy, sy = math.cos(self.yaw), math.sin(self.yaw)
        z += x * sy
        x = x * cy
        s = self.focal / (self.focal + z)
        return self.center[0] + x * s, self.center[1] + y * s, s

    def update(self):
        w, h = self.size
        uvs = [(0, 0), (1, 0), (1, 1), (0, 1)]
        self.corners = [self.project_local((u - 0.5) * w, (v - 0.5) * h) for u, v in uvs]
        pts = [(c[0], c[1]) for c in self.corners]
        try:
            self._h = homography(uvs, pts)
            self._hinv = np.linalg.inv(self._h)
        except np.linalg.LinAlgError:
            self._h = self._hinv = None

    def uv_to_canvas(self, u, v):
        if self._h is None:
            return self.center
        return apply_h(self._h, u, v)

    def canvas_to_uv(self, x, y):
        if self._hinv is None:
            return None
        u, v = apply_h(self._hinv, x, y)
        return u, v

    def vertices(self, canvas_size, dx=0.0, dy=0.0):
        """Dados de vértice (clip xyzw + uv) para dois triângulos."""
        cw, ch = canvas_size
        uvs = [(0, 0), (1, 0), (1, 1), (0, 1)]
        verts = []
        for (x, y, s), (u, v) in zip(self.corners, uvs):
            w = 1.0 / s
            nx = (2 * (x + dx) / cw - 1) * w
            ny = (1 - 2 * (y + dy) / ch) * w
            verts.append((nx, ny, 0.0, w, u, v))
        order = [0, 1, 2, 0, 2, 3]
        return np.array([verts[i] for i in order], dtype=np.float32)


class Gfx:
    def __init__(self, ctx: moderngl.Context, window_size):
        self.ctx = ctx
        self.bg_prog = ctx.program(vertex_shader=QUAD_VS, fragment_shader=BG_FS)
        self.card_prog = ctx.program(vertex_shader=CARD_VS, fragment_shader=CARD_FS)
        self.overlay_prog = ctx.program(vertex_shader=QUAD_VS, fragment_shader=OVERLAY_FS)
        self.post_prog = ctx.program(vertex_shader=QUAD_VS, fragment_shader=POST_FS)
        quad = np.array([-1, -1, 1, -1, -1, 1, -1, 1, 1, -1, 1, 1], dtype=np.float32)
        self.quad_vbo = ctx.buffer(quad.tobytes())
        self.bg_vao = ctx.vertex_array(self.bg_prog, [(self.quad_vbo, "2f", "in_pos")])
        self.overlay_vao = ctx.vertex_array(self.overlay_prog, [(self.quad_vbo, "2f", "in_pos")])
        self.post_vao = ctx.vertex_array(self.post_prog, [(self.quad_vbo, "2f", "in_pos")])
        self.card_vbo = ctx.buffer(reserve=6 * 6 * 4, dynamic=True)
        self.card_vao = ctx.vertex_array(self.card_prog, [(self.card_vbo, "4f 2f", "in_clip", "in_uv")])
        self.board_tex = None
        self.overlay_tex = None
        self.canvas_fbo = None
        self.crt = 1.0
        self.resize(window_size)

    def resize(self, window_size):
        self.window = (max(1, window_size[0]), max(1, window_size[1]))
        aspect = self.window[0] / self.window[1]
        self.canvas = (max(320, int(round(CANVAS_H * aspect))), CANVAS_H)
        if self.canvas_fbo:
            self.canvas_fbo.release()
            self.canvas_tex.release()
        self.canvas_tex = self.ctx.texture(self.canvas, 3)
        self.canvas_tex.filter = (moderngl.NEAREST, moderngl.NEAREST)
        self.canvas_tex.repeat_x = self.canvas_tex.repeat_y = False
        self.canvas_fbo = self.ctx.framebuffer([self.canvas_tex])

    def window_to_canvas(self, mx, my):
        """Converte o mouse da janela para o canvas, desfazendo a curvatura CRT."""
        u = mx / self.window[0]
        v = 1.0 - my / self.window[1]
        cx, cy = u - 0.5, v - 0.5
        d = cx * cx + cy * cy
        k = 1.0 + CRT_CURVE * self.crt * d
        u, v = 0.5 + cx * k, 0.5 + cy * k
        return u * self.canvas[0], (1.0 - v) * self.canvas[1]

    def _upload(self, attr, surf_bytes, size):
        tex = getattr(self, attr)
        if tex is None or tex.size != size:
            if tex:
                tex.release()
            tex = self.ctx.texture(size, 4)
            tex.filter = (moderngl.NEAREST, moderngl.NEAREST)
            tex.repeat_x = tex.repeat_y = False
            setattr(self, attr, tex)
        tex.write(surf_bytes)
        return tex

    def render(self, time_s, theme, view: CardView, board_bytes, board_size, overlay_bytes,
               sheen=-1.0, thickness=5.0, light=1.0):
        ctx = self.ctx
        board = self._upload("board_tex", board_bytes, board_size)
        overlay = self._upload("overlay_tex", overlay_bytes, self.canvas)

        self.canvas_fbo.use()
        ctx.disable(moderngl.DEPTH_TEST | moderngl.CULL_FACE)
        self.bg_prog["u_time"].value = time_s
        self.bg_prog["u_res"].value = self.canvas
        for i, c in enumerate(theme, 1):
            self.bg_prog[f"u_c{i}"].value = c
        self.bg_vao.render(moderngl.TRIANGLES)

        ctx.enable(moderngl.BLEND)
        ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        board.use(location=0)
        self.card_prog["u_tex"].value = 0
        self.card_prog["u_texsize"].value = board_size
        self.card_prog["u_sheen"].value = sheen
        self.card_prog["u_light"].value = light
        passes = [
            (1, (0.0, 0.0, 0.0, 0.45), 7.0, thickness + 9.0),     # sombra projetada
            (1, (0.10, 0.06, 0.10, 1.0), 0.0, thickness),         # espessura
            (1, (0.22, 0.14, 0.16, 1.0), 0.0, thickness * 0.5),
            (0, (1, 1, 1, 1), 0.0, 0.0),                          # face
        ]
        for mode, color, dx, dy in passes:
            self.card_vbo.write(view.vertices(self.canvas, dx, dy).tobytes())
            self.card_prog["u_mode"].value = mode
            self.card_prog["u_color"].value = color
            self.card_vao.render(moderngl.TRIANGLES)

        overlay.use(location=0)
        self.overlay_prog["u_tex"].value = 0
        self.overlay_vao.render(moderngl.TRIANGLES)
        ctx.disable(moderngl.BLEND)

        ctx.screen.use()
        self.canvas_tex.use(location=0)
        self.post_prog["u_tex"].value = 0
        self.post_prog["u_canvas"].value = self.canvas
        self.post_prog["u_time"].value = time_s % 100.0
        self.post_prog["u_curve"].value = CRT_CURVE * self.crt
        self.post_prog["u_crt"].value = self.crt
        self.post_vao.render(moderngl.TRIANGLES)
