"""Renderizador voxel com moderngl.

Tudo é desenhado como cubos instanciados. A cena é renderizada em um
framebuffer de baixa resolução e depois ampliada com filtro "nearest",
dando o visual 3D pixelado. Há sombra (shadow map), pós-processamento
com paleta reduzida + dithering, e uma camada de HUD (texto) por cima.
"""
from __future__ import annotations

import math

import moderngl
import numpy as np

from .camera import gl_bytes, look_at, ortho

# instância: pos(3) tamanho(3) cor(3) material(1)
#   material = 0 -> iluminado liso, 0<m<=1 -> iluminado com textura de ruído, 2 -> emissivo
INSTANCE_FLOATS = 10

CUBE_VS = """
#version 330
in vec3 in_pos;
in vec3 in_norm;
in vec3 i_pos;
in vec3 i_size;
in vec3 i_col;
in float i_mat;
uniform mat4 u_vp;
uniform mat4 u_light_vp;
out vec3 v_norm;
out vec3 v_col;
out float v_mat;
out vec3 v_world;
out vec3 v_local;
out vec4 v_lpos;
void main() {
    vec3 w = i_pos + in_pos * i_size;
    v_world = w;
    v_local = in_pos * i_size;
    v_norm = in_norm;
    v_col = i_col;
    v_mat = i_mat;
    v_lpos = u_light_vp * vec4(w + in_norm * 0.035, 1.0);
    gl_Position = u_vp * vec4(w, 1.0);
}
"""

CUBE_FS = """
#version 330
in vec3 v_norm;
in vec3 v_col;
in float v_mat;
in vec3 v_world;
in vec3 v_local;
in vec4 v_lpos;
uniform sampler2DShadow u_shadow;
uniform vec3 u_light_dir;
uniform vec3 u_eye;
uniform float u_texel;
out vec4 f_color;

float hash(vec3 p) {
    p = fract(p * 0.3183099 + vec3(0.1, 0.2, 0.3));
    p *= 17.0;
    return fract(p.x * p.y * p.z * (p.x + p.y + p.z));
}

void main() {
    vec3 col = v_col;
    if (v_mat > 1.5) {            // emissivo (marcadores, destaques)
        f_color = vec4(col, 1.0);
        return;
    }
    if (v_mat > 0.0) {            // textura "pixel" procedural (madeira, feltro...)
        vec3 cell = floor(v_world / u_texel + 0.001);
        float h = hash(cell);
        float grain = sin(cell.x * 0.9 + cell.z * 0.15 + h * 2.0) * 0.5 + 0.5;
        col *= 1.0 + (h - 0.5) * 0.18 * v_mat + (grain - 0.5) * 0.10 * v_mat;
    }
    vec3 n = normalize(v_norm);
    float diff = max(dot(n, u_light_dir), 0.0);
    // sombra
    vec3 p = v_lpos.xyz / v_lpos.w * 0.5 + 0.5;
    float shadow = 1.0;
    if (p.x > 0.0 && p.x < 1.0 && p.y > 0.0 && p.y < 1.0 && p.z < 1.0) {
        shadow = texture(u_shadow, vec3(p.xy, p.z - 0.0012 - 0.002 * (1.0 - diff)));
    }
    // sombreamento por face, estilo voxel
    float face = 0.86;
    if (n.y > 0.5) face = 1.0;
    else if (n.y < -0.5) face = 0.55;
    else if (abs(n.x) > 0.5) face = 0.80;
    vec3 ambient = vec3(0.42, 0.44, 0.55);
    vec3 sun = vec3(1.0, 0.93, 0.80);
    vec3 lit = col * (ambient * face + sun * diff * shadow * 0.75);
    // névoa suave de distância
    float dist = length(v_world - u_eye);
    float fog = clamp((dist - 28.0) / 40.0, 0.0, 0.6);
    lit = mix(lit, vec3(0.10, 0.09, 0.16), fog);
    f_color = vec4(lit, 1.0);
}
"""

DEPTH_VS = """
#version 330
in vec3 in_pos;
in vec3 i_pos;
in vec3 i_size;
in float i_mat;
uniform mat4 u_light_vp;
void main() {
    vec3 w = i_pos + in_pos * i_size;
    // marcadores emissivos não projetam sombra
    if (i_mat > 1.5) w = vec3(0.0, -1000.0, 0.0);
    gl_Position = u_light_vp * vec4(w, 1.0);
}
"""

DEPTH_FS = """
#version 330
void main() {}
"""

QUAD_VS = """
#version 330
in vec2 in_pos;
out vec2 v_uv;
void main() {
    v_uv = in_pos * 0.5 + 0.5;
    gl_Position = vec4(in_pos, 0.0, 1.0);
}
"""

POST_FS = """
#version 330
in vec2 v_uv;
uniform sampler2D u_tex;
uniform vec2 u_lowres;
uniform float u_levels;
out vec4 f_color;
const float bayer[16] = float[16](0.0, 8.0, 2.0, 10.0, 12.0, 4.0, 14.0, 6.0,
                                  3.0, 11.0, 1.0, 9.0, 15.0, 7.0, 13.0, 5.0);
void main() {
    vec3 c = texture(u_tex, v_uv).rgb;
    ivec2 px = ivec2(floor(v_uv * u_lowres));
    float d = bayer[(px.y % 4) * 4 + (px.x % 4)] / 16.0 - 0.5;
    c = floor(c * u_levels + 0.5 + d * 0.9) / u_levels;   // paleta reduzida com dithering
    vec2 q = v_uv - 0.5;
    c *= 1.0 - dot(q, q) * 0.55;                          // vinheta
    f_color = vec4(c, 1.0);
}
"""

HUD_FS = """
#version 330
in vec2 v_uv;
uniform sampler2D u_tex;
out vec4 f_color;
void main() {
    f_color = texture(u_tex, vec2(v_uv.x, v_uv.y));
}
"""

BG_FS = """
#version 330
in vec2 v_uv;
out vec4 f_color;
void main() {
    vec3 top = vec3(0.10, 0.09, 0.18);
    vec3 bot = vec3(0.20, 0.13, 0.20);
    f_color = vec4(mix(bot, top, v_uv.y), 1.0);
}
"""


def _cube_vertices():
    faces = [
        ((1, 0, 0), [(0.5, -0.5, -0.5), (0.5, 0.5, -0.5), (0.5, 0.5, 0.5), (0.5, -0.5, 0.5)]),
        ((-1, 0, 0), [(-0.5, -0.5, 0.5), (-0.5, 0.5, 0.5), (-0.5, 0.5, -0.5), (-0.5, -0.5, -0.5)]),
        ((0, 1, 0), [(-0.5, 0.5, -0.5), (-0.5, 0.5, 0.5), (0.5, 0.5, 0.5), (0.5, 0.5, -0.5)]),
        ((0, -1, 0), [(-0.5, -0.5, 0.5), (-0.5, -0.5, -0.5), (0.5, -0.5, -0.5), (0.5, -0.5, 0.5)]),
        ((0, 0, 1), [(0.5, -0.5, 0.5), (0.5, 0.5, 0.5), (-0.5, 0.5, 0.5), (-0.5, -0.5, 0.5)]),
        ((0, 0, -1), [(-0.5, -0.5, -0.5), (-0.5, 0.5, -0.5), (0.5, 0.5, -0.5), (0.5, -0.5, -0.5)]),
    ]
    data = []
    for n, (a, b, c, d) in faces:
        for v in (a, b, c, a, c, d):
            data.extend(v)
            data.extend(n)
    return np.array(data, dtype=np.float32)


class InstanceBatch:
    """Acumula cubos para um quadro."""

    def __init__(self):
        self.parts = []

    def add_array(self, arr):
        if len(arr):
            self.parts.append(np.asarray(arr, dtype=np.float32).reshape(-1, INSTANCE_FLOATS))

    def cube(self, pos, size, color, mat=0.0):
        self.parts.append(np.array([[*pos, *size, *color, mat]], dtype=np.float32))

    def model(self, pos, col, offset, scale=1.0, voxel=1.0, tint=None, mat=0.0):
        """Adiciona um modelo voxel (arrays de voxels.py) transladado."""
        n = len(pos)
        arr = np.empty((n, INSTANCE_FLOATS), dtype=np.float32)
        arr[:, 0:3] = pos * scale + np.asarray(offset, dtype=np.float32)
        arr[:, 3:6] = voxel * scale
        c = col if tint is None else col * 0.4 + np.asarray(tint, dtype=np.float32) * 0.6
        arr[:, 6:9] = c
        arr[:, 9] = mat
        self.parts.append(arr)

    def models_many(self, pos, col, offsets, voxel=1.0, mat=0.0):
        """Mesmo modelo repetido em vários lugares (ex.: pedras de Go)."""
        offsets = np.asarray(offsets, dtype=np.float32).reshape(-1, 3)
        if not len(offsets):
            return
        n, k = len(pos), len(offsets)
        arr = np.empty((k, n, INSTANCE_FLOATS), dtype=np.float32)
        arr[:, :, 0:3] = pos[None, :, :] + offsets[:, None, :]
        arr[:, :, 3:6] = voxel
        arr[:, :, 6:9] = col[None, :, :]
        arr[:, :, 9] = mat
        self.parts.append(arr.reshape(-1, INSTANCE_FLOATS))

    def array(self):
        if not self.parts:
            return np.zeros((0, INSTANCE_FLOATS), dtype=np.float32)
        return np.concatenate(self.parts)


class Renderer:
    SHADOW_SIZE = 2048

    def __init__(self, ctx: moderngl.Context, size, pixel_scale=3):
        self.ctx = ctx
        self.pixel_scale = pixel_scale
        self.levels = 20.0
        self.texel = 1.0 / 16.0
        self.prog = ctx.program(vertex_shader=CUBE_VS, fragment_shader=CUBE_FS)
        self.depth_prog = ctx.program(vertex_shader=DEPTH_VS, fragment_shader=DEPTH_FS)
        self.post_prog = ctx.program(vertex_shader=QUAD_VS, fragment_shader=POST_FS)
        self.hud_prog = ctx.program(vertex_shader=QUAD_VS, fragment_shader=HUD_FS)
        self.bg_prog = ctx.program(vertex_shader=QUAD_VS, fragment_shader=BG_FS)

        self.cube_vbo = ctx.buffer(_cube_vertices().tobytes())
        self.capacity = 0
        self.inst_vbo = None
        self._ensure_capacity(65536)

        quad = np.array([-1, -1, 1, -1, -1, 1, -1, 1, 1, -1, 1, 1], dtype=np.float32)
        self.quad_vbo = ctx.buffer(quad.tobytes())
        self.post_vao = ctx.vertex_array(self.post_prog, [(self.quad_vbo, "2f", "in_pos")])
        self.hud_vao = ctx.vertex_array(self.hud_prog, [(self.quad_vbo, "2f", "in_pos")])
        self.bg_vao = ctx.vertex_array(self.bg_prog, [(self.quad_vbo, "2f", "in_pos")])

        self.shadow_tex = ctx.depth_texture((self.SHADOW_SIZE, self.SHADOW_SIZE))
        self.shadow_tex.compare_func = "<="
        self.shadow_tex.filter = (moderngl.NEAREST, moderngl.NEAREST)
        self.shadow_tex.repeat_x = self.shadow_tex.repeat_y = False
        self.shadow_fbo = ctx.framebuffer(depth_attachment=self.shadow_tex)

        self.hud_tex = None
        self.lowres_fbo = None
        self.resize(size)

        light_dir = np.array([-0.45, 1.0, 0.55])
        self.light_dir = light_dir / np.linalg.norm(light_dir)
        light_view = look_at(self.light_dir * 30.0, (0, 0, 0), up=(0, 0, -1))
        self.light_vp = ortho(-17, 17, -17, 17, 1.0, 70.0) @ light_view

    def _ensure_capacity(self, n):
        if n <= self.capacity:
            return
        cap = max(n, int(self.capacity * 1.5), 1024)
        if self.inst_vbo:
            self.inst_vbo.release()
        self.inst_vbo = self.ctx.buffer(reserve=cap * INSTANCE_FLOATS * 4, dynamic=True)
        self.capacity = cap
        self.vao = self.ctx.vertex_array(self.prog, [
            (self.cube_vbo, "3f 3f", "in_pos", "in_norm"),
            (self.inst_vbo, "3f 3f 3f 1f/i", "i_pos", "i_size", "i_col", "i_mat"),
        ])
        self.depth_vao = self.ctx.vertex_array(self.depth_prog, [
            (self.cube_vbo, "3f 12x", "in_pos"),
            (self.inst_vbo, "3f 3f 12x 1f/i", "i_pos", "i_size", "i_mat"),
        ])

    def resize(self, size):
        self.size = (max(1, size[0]), max(1, size[1]))
        lw = max(64, self.size[0] // self.pixel_scale)
        lh = max(48, self.size[1] // self.pixel_scale)
        self.lowres = (lw, lh)
        if self.lowres_fbo:
            self.lowres_fbo.release()
            self.lowres_color.release()
            self.lowres_depth.release()
        self.lowres_color = self.ctx.texture(self.lowres, 3)
        self.lowres_color.filter = (moderngl.NEAREST, moderngl.NEAREST)
        self.lowres_depth = self.ctx.depth_renderbuffer(self.lowres)
        self.lowres_fbo = self.ctx.framebuffer([self.lowres_color], self.lowres_depth)

    def set_pixel_scale(self, s):
        self.pixel_scale = int(min(8, max(1, s)))
        self.resize(self.size)

    def upload_hud(self, rgba_bytes, size):
        if self.hud_tex is None or self.hud_tex.size != size:
            if self.hud_tex:
                self.hud_tex.release()
            self.hud_tex = self.ctx.texture(size, 4)
            self.hud_tex.filter = (moderngl.NEAREST, moderngl.NEAREST)
        self.hud_tex.write(rgba_bytes)

    def render(self, instances: np.ndarray, camera, screen_fbo=None, draw_hud=True):
        ctx = self.ctx
        n = len(instances)
        self._ensure_capacity(n)
        if n:
            self.inst_vbo.write(np.ascontiguousarray(instances, dtype=np.float32).tobytes())

        # 1) sombra
        self.shadow_fbo.use()
        self.shadow_fbo.clear(depth=1.0)
        ctx.enable(moderngl.DEPTH_TEST | moderngl.CULL_FACE)
        self.depth_prog["u_light_vp"].write(gl_bytes(self.light_vp))
        if n:
            self.depth_vao.render(moderngl.TRIANGLES, instances=n)

        # 2) cena em baixa resolução
        self.lowres_fbo.use()
        self.lowres_fbo.clear(0, 0, 0, 1, depth=1.0)
        ctx.disable(moderngl.DEPTH_TEST)
        self.bg_vao.render(moderngl.TRIANGLES)
        ctx.enable(moderngl.DEPTH_TEST | moderngl.CULL_FACE)
        aspect = self.size[0] / self.size[1]
        vp = camera.proj(aspect) @ camera.view()
        self.prog["u_vp"].write(gl_bytes(vp))
        self.prog["u_light_vp"].write(gl_bytes(self.light_vp))
        self.prog["u_light_dir"].value = tuple(float(v) for v in self.light_dir)
        self.prog["u_eye"].value = tuple(float(v) for v in camera.eye)
        self.prog["u_texel"].value = self.texel
        self.shadow_tex.use(location=0)
        self.prog["u_shadow"].value = 0
        if n:
            self.vao.render(moderngl.TRIANGLES, instances=n)

        # 3) amplia para a tela com pós-processamento
        target = screen_fbo or ctx.screen
        target.use()
        ctx.disable(moderngl.DEPTH_TEST | moderngl.CULL_FACE)
        self.lowres_color.use(location=0)
        self.post_prog["u_tex"].value = 0
        self.post_prog["u_lowres"].value = self.lowres
        self.post_prog["u_levels"].value = self.levels
        self.post_vao.render(moderngl.TRIANGLES)

        # 4) HUD
        if draw_hud and self.hud_tex is not None:
            ctx.enable(moderngl.BLEND)
            ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
            self.hud_tex.use(location=0)
            self.hud_prog["u_tex"].value = 0
            self.hud_vao.render(moderngl.TRIANGLES)
            ctx.disable(moderngl.BLEND)


def smoothstep(t):
    t = min(1.0, max(0.0, t))
    return t * t * (3 - 2 * t)


def arc(t, height):
    return math.sin(math.pi * min(1.0, max(0.0, t))) * height
