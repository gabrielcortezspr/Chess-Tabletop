"""Loop principal: janela, entrada, "câmera" pseudo-3D do tabuleiro e HUD estilo cartas."""
from __future__ import annotations

import argparse
import math
import os
import random
import time

import moderngl
import pygame

from .chess_scene import ChessScene
from .fx import Bump, Particles, Popup, Shake, clamp, ease_in_out, ease_out_back, wobble_text
from .gfx import CardView, Gfx
from .go_scene import GoScene

PANEL_W = 178
PANEL_BG = (28, 36, 44)
PANEL_IN = (18, 24, 30)
PANEL_EDGE = (62, 78, 90)
INK = (20, 16, 30)
WHITE = (255, 255, 255)
GOLD = (255, 196, 64)

HELP = [
    ("Botão direito + arrastar", "inclinar o tabuleiro"),
    ("Meio / Shift+direito", "deslocar  ·  roda: zoom"),
    ("F  ·  Espaço", "virar o tabuleiro  ·  visão padrão"),
    ("Tab  ·  M", "trocar Xadrez/Go  ·  Modo Jogo/Livre"),
    ("Z  ·  Y", "voltar lance  ·  avançar lance"),
    ("R  ·  Shift+R", "recomeçar da posição montada  ·  do zero"),
    ("Ctrl+C", "copiar FEN (xadrez) / SGF (go)"),
    ("Ctrl+Shift+C", "copiar a partida em PGN (xadrez)"),
    ("Ctrl+V", "colar FEN, PGN ou SGF"),
    ("Ctrl+S  ·  Ctrl+L", "salvar posição  ·  carregar próxima salva"),
    ("Enter (modo livre)", "jogar desta posição (Shift: o outro lado)"),
    ("D  ·  K  ·  B (go)", "handicap  ·  komi  ·  tamanho"),
    ("F2  ·  F12", "efeito CRT  ·  screenshot"),
    ("H  ·  Ctrl+Q", "ajuda  ·  sair"),
]


class App:
    def __init__(self, size=(1280, 720), game="xadrez", hidden=False):
        pygame.init()
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION, 3)
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MINOR_VERSION, 3)
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_PROFILE_MASK, pygame.GL_CONTEXT_PROFILE_CORE)
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_FORWARD_COMPATIBLE_FLAG, True)
        flags = pygame.OPENGL | pygame.DOUBLEBUF | pygame.RESIZABLE
        if hidden:
            flags |= pygame.HIDDEN
        try:
            pygame.display.set_mode(size, flags, vsync=1)
        except pygame.error:
            pygame.display.set_mode(size, flags)
        pygame.display.set_caption("Tabletop - Xadrez & Go")
        self.ctx = moderngl.create_context()
        self.size = size
        self.gfx = Gfx(self.ctx, size)
        self.scenes = {"xadrez": ChessScene(), "go": GoScene()}
        self.scene_key = "go" if game == "go" else "xadrez"
        self.theme = [list(c) for c in self.scene.theme]
        self.view = CardView()
        self.base_pitch, self.base_yaw = 20.0, 0.0
        self.zoom = 1.0
        self.pan = [0.0, 0.0]
        self.hover_tilt = [0.0, 0.0]
        self.flip_anim = None         # (t0, ação no meio)
        self.shake = Shake()
        self.bump = Bump()
        self.popups: list[Popup] = []
        self.banner = None            # (texto, cor, t0)
        self.screen_particles = Particles()
        self.sheen_t0 = -10.0
        self.next_sheen = 4.0
        self.held_angle = 0.0
        self.mouse_canvas = (0.0, 0.0)
        self.last_mouse_canvas = (0.0, 0.0)
        self.show_help = False
        self.running = True
        self.drag = None
        self.t = 0.0
        self.board_scale = 2.0
        self.board_surf = None
        self.font_s = pygame.font.Font(None, 16)
        self.font = pygame.font.Font(None, 17)
        self.font_px = pygame.font.Font(None, 14)    # renderizada e ampliada 2x (pixel grosso)
        self.tabs = []

    @property
    def scene(self):
        return self.scenes[self.scene_key]

    # ----------------------------------------------------------- utilidades
    def big_text(self, text, color, scale=2):
        img = self.font_px.render(text, False, color)
        return pygame.transform.scale_by(img, scale)

    def start_flip(self, action):
        if self.flip_anim is None:
            self.flip_anim = [self.t, action]

    def board_area(self):
        cw, ch = self.gfx.canvas
        return PANEL_W + 14, 30, cw - PANEL_W - 24, ch - 52

    def layout_view(self, dt):
        cw, ch = self.gfx.canvas
        tw, th = self.scene.tex_size
        ax, ay, aw, ah = self.board_area()
        scale = min(aw / tw, ah / th) * 0.94 * self.zoom
        self.board_scale = scale
        sx, sy, sroll = self.shake.offset()
        v = self.view
        v.size = (tw * scale, th * scale)
        v.center = (ax + aw / 2 + self.pan[0] + sx, ay + ah / 2 + self.pan[1] + sy)
        v.focal = ch * 1.7
        # inclina na direção do mouse quando ele está sobre o tabuleiro (como uma carta)
        mx, my = self.mouse_canvas
        nx = (mx - v.center[0]) / (v.size[0] / 2)
        ny = (my - v.center[1]) / (v.size[1] / 2)
        inside = abs(nx) < 1.1 and abs(ny) < 1.1 and not self.drag
        tx, ty = (clamp(nx, -1, 1), clamp(ny, -1, 1)) if inside else (0.0, 0.0)
        k = 1 - math.exp(-dt * 6)
        self.hover_tilt[0] += (tx - self.hover_tilt[0]) * k
        self.hover_tilt[1] += (ty - self.hover_tilt[1]) * k
        idle_p = math.sin(self.t * 0.8) * 1.2
        idle_y = math.sin(self.t * 0.55) * 1.6
        flip = 0.0
        if self.flip_anim:
            t0, action = self.flip_anim
            f = (self.t - t0) / 0.5
            if f >= 0.5 and action:
                action()
                self.flip_anim[1] = None
            if f >= 1.0:
                self.flip_anim = None
            else:
                flip = 1 - abs(1 - 2 * ease_in_out(f))       # 0 -> 1 -> 0
                v.size = (v.size[0] * max(0.02, math.cos(flip * math.pi / 2)), v.size[1])
        v.pitch = math.radians(self.base_pitch + idle_p - self.hover_tilt[1] * 4.0)
        v.yaw = math.radians(self.base_yaw + idle_y + self.hover_tilt[0] * 5.0 + flip * 25.0)
        v.roll = sroll + math.sin(self.t * 0.4) * 0.006
        v.update()

    def hover_cell(self):
        uv = self.view.canvas_to_uv(*self.mouse_canvas)
        if uv is None:
            return None
        tw, th = self.scene.tex_size
        u, v = uv
        if not (0 <= u <= 1 and 0 <= v <= 1):
            return None
        return self.scene.pick_tex(u * tw, v * th)

    # ----------------------------------------------------------- entrada
    def handle_event(self, e):
        if e.type == pygame.QUIT:
            self.running = False
        elif e.type in (pygame.VIDEORESIZE, pygame.WINDOWSIZECHANGED):
            w, h = pygame.display.get_window_size()
            self.size = (w, h)
            self.ctx.screen.viewport = (0, 0, w, h)
            self.gfx.resize((w, h))
        elif e.type == pygame.MOUSEMOTION:
            self.mouse_canvas = self.gfx.window_to_canvas(*e.pos)
            if self.drag:
                btn, sx, sy, moved = self.drag
                if abs(e.pos[0] - sx) + abs(e.pos[1] - sy) > 5:
                    moved = True
                self.drag = (btn, sx, sy, moved)
                dx, dy = e.rel
                shift = pygame.key.get_mods() & pygame.KMOD_SHIFT
                if btn == 3 and not shift:
                    self.base_yaw = clamp(self.base_yaw + dx * 0.15, -35, 35)
                    self.base_pitch = clamp(self.base_pitch + dy * 0.15, 0, 45)
                elif btn == 2 or (btn == 3 and shift):
                    k = self.gfx.canvas[1] / self.size[1]
                    self.pan[0] = clamp(self.pan[0] + dx * k, -140, 140)
                    self.pan[1] = clamp(self.pan[1] + dy * k, -90, 90)
        elif e.type == pygame.MOUSEBUTTONDOWN and e.button in (1, 2, 3):
            self.mouse_canvas = self.gfx.window_to_canvas(*e.pos)
            self.drag = (e.button, e.pos[0], e.pos[1], False)
        elif e.type == pygame.MOUSEBUTTONUP:
            if self.drag and self.drag[0] == e.button == 1 and not self.drag[3]:
                self.on_click()
            self.drag = None
        elif e.type == pygame.MOUSEWHEEL:
            self.zoom = clamp(self.zoom * (1.08 ** e.y), 0.6, 1.6)
        elif e.type == pygame.KEYDOWN:
            self.handle_key(e.key, e.mod)

    def on_click(self):
        mx, my = self.mouse_canvas
        for rect, key in self.tabs:
            if rect.collidepoint(mx, my) and key != self.scene_key:
                self.switch_game()
                return
        shift = bool(pygame.key.get_mods() & pygame.KMOD_SHIFT)
        self.scene.click(self.hover_cell(), shift)

    def switch_game(self):
        def act():
            self.scene_key = "go" if self.scene_key == "xadrez" else "xadrez"
            self.banner = None
            self.popups.clear()
            self.scene.events.append(("sheen",))
        self.start_flip(act)

    def handle_key(self, key, mod):
        if key == pygame.K_q and mod & pygame.KMOD_CTRL:
            self.running = False
            return
        if self.scene.key(key, mod):
            return
        if key == pygame.K_TAB:
            self.switch_game()
        elif key == pygame.K_m:
            self.scene.toggle_mode()
            self.scene.events.append(("sheen",))
        elif key == pygame.K_r:
            self.scene.reset()
        elif key == pygame.K_z:
            self.scene.undo()
        elif key == pygame.K_h:
            self.show_help = not self.show_help
        elif key == pygame.K_f:
            self.start_flip(self.scene.flip)
        elif key == pygame.K_SPACE:
            self.base_pitch, self.base_yaw, self.zoom, self.pan = 20.0, 0.0, 1.0, [0.0, 0.0]
        elif key == pygame.K_F2:
            self.gfx.crt = 0.0 if self.gfx.crt else 1.0
        elif key == pygame.K_F12:
            os.makedirs("screenshots", exist_ok=True)
            path = time.strftime("screenshots/tabletop_%Y%m%d_%H%M%S.png")
            self.screenshot(path)
            self.scene.toast("Screenshot: " + path)

    # ----------------------------------------------------------- eventos de efeitos
    def process_events(self):
        for ev in self.scene.drain_events():
            kind = ev[0]
            if kind == "shake":
                self.shake.kick(ev[1])
            elif kind == "popup":
                _, text, color, (tx, ty) = ev
                tw, th = self.scene.tex_size
                x, y = self.view.uv_to_canvas(tx / tw, ty / th)
                self.popups.append(Popup(text, x, y, color))
            elif kind == "banner":
                self.banner = (ev[1], ev[2], self.t)
            elif kind == "sheen":
                self.sheen_t0 = self.t
            elif kind == "confetti":
                cw, _ = self.gfx.canvas
                self.screen_particles.confetti(PANEL_W, -4, cw - PANEL_W)

    # ----------------------------------------------------------- HUD
    def panel_box(self, surf, rect, color, radius=5, shadow=True):
        r = pygame.Rect(rect)
        if shadow:
            pygame.draw.rect(surf, (0, 0, 0, 110), r.move(0, 2), border_radius=radius)
        pygame.draw.rect(surf, color, r, border_radius=radius)

    def wrap(self, s, width):
        words, lines, cur = s.split(" "), [], ""
        for wd in words:
            cand = f"{cur} {wd}" if cur else wd
            if self.font_s.size(cand)[0] > width and cur:
                lines.append(cur)
                cur = "  " + wd
            else:
                cur = cand
        lines.append(cur)
        return lines

    def text(self, surf, s, color, x, y, font=None, center=False, shadow=True):
        font = font or self.font
        img = font.render(s, False, color)
        if center:
            x -= img.get_width() // 2
        if shadow:
            surf.blit(font.render(s, False, INK), (x + 1, y + 1))
        surf.blit(img, (x, y))
        return img.get_width()

    def draw_overlay(self, surf):
        cw, ch = surf.get_size()
        d = self.scene.hud()
        accent = d["accent"]
        t = self.t

        # ---- painel lateral
        self.panel_box(surf, (6, 6, PANEL_W - 6, ch - 12), PANEL_BG, 8)
        pygame.draw.rect(surf, PANEL_EDGE, (6, 6, PANEL_W - 6, ch - 12), 1, border_radius=8)
        x0, w = 12, PANEL_W - 18
        # título com letras ondulando
        self.panel_box(surf, (x0, 12, w, 44), accent, 6)
        pygame.draw.rect(surf, tuple(min(255, c + 40) for c in accent), (x0, 12, w, 44), 1, border_radius=6)
        title = d["title"]
        glyphs = [self.big_text(c, WHITE) for c in title]
        tot = sum(g.get_width() for g in glyphs)
        cx = x0 + w // 2 - tot // 2
        for i, g in enumerate(glyphs):
            dy = round(math.sin(t * 3 + i * 0.7) * 2)
            surf.blit(self.big_text(title[i], INK), (cx + 2, 16 + dy + 2))
            surf.blit(g, (cx, 16 + dy))
            cx += g.get_width()
        self.text(surf, d["mode"], WHITE, x0 + w // 2, 41, self.font_s, center=True)

        # ---- status
        y = 62
        self.panel_box(surf, (x0, y, w, 20), PANEL_IN, 5, shadow=False)
        st, sc = d["status"]
        while self.font_s.size(st)[0] > w - 8 and len(st) > 4:
            st = st[:-2]
        self.text(surf, st, sc, x0 + w // 2, y + 5, self.font_s, center=True)

        # ---- placar (duas caixas tipo fichas x multiplicador)
        y += 26
        bw = (w - 14) // 2
        for i, (label, value, color) in enumerate(d["scores"]):
            bx = x0 + i * (bw + 14)
            self.panel_box(surf, (bx, y, bw, 44), color, 6)
            light = sum(color) > 450
            fg = INK if light else WHITE
            self.text(surf, label, fg, bx + bw // 2, y + 4, self.font_s, center=True, shadow=not light)
            s = self.bump.scale(label, value, t)
            num = self.big_text(f"{value:g}" if isinstance(value, float) else str(value), fg)
            if s != 1.0:
                num = pygame.transform.scale_by(num, s)
            surf.blit(num, (bx + bw // 2 - num.get_width() // 2, y + 28 - num.get_height() // 2 + 4))
        vs = self.big_text("x", (255, 220, 120), 1)
        surf.blit(vs, (x0 + w // 2 - vs.get_width() // 2, y + 17))

        # ---- linhas de informação
        y += 52
        for s, c in d["lines"]:
            for part in self.wrap(s, w - 2):
                self.text(surf, part, c, x0 + 2, y, self.font_s)
                y += 12

        # ---- peças capturadas
        if d.get("icons"):
            sprites = self.scene.sprites
            for row, caps in enumerate(d["icons"]):
                if not caps:
                    continue
                y += 2
                xx = x0
                for p in caps:
                    surf.blit(sprites[p], (xx, y))
                    xx += 10
                y += 16

        # ---- placar de partidas (caixa dourada)
        lab, a, b = d["tally"]
        names = d.get("tally_names", ("B", "P"))
        y = max(y + 4, ch - 136)
        self.panel_box(surf, (x0, y, w, 26), (60, 46, 30), 5)
        pygame.draw.rect(surf, GOLD, (x0, y, w, 26), 1, border_radius=5)
        self.text(surf, lab, GOLD, x0 + 6, y + 8, self.font_s)
        sa = self.bump.scale("tally_a", a, t)
        sb = self.bump.scale("tally_b", b, t)
        txt = f"{names[0]} {a}  :  {b} {names[1]}"
        img = self.big_text(txt, WHITE, 1)
        img = pygame.transform.scale_by(img, max(sa, sb) * 1.2)
        surf.blit(img, (x0 + w - img.get_width() - 6, y + 13 - img.get_height() // 2))

        # ---- atalhos (fichas de teclas)
        y += 32
        xx = x0
        for k, lbl in d["hints"]:
            kw = self.font_s.size(k)[0] + 6
            lw = self.font_s.size(lbl)[0]
            if xx + kw + lw + 4 > x0 + w:
                xx = x0
                y += 14
            if y > ch - 36:
                break
            pygame.draw.rect(surf, (80, 96, 110), (xx, y, kw, 12), border_radius=3)
            pygame.draw.rect(surf, (230, 230, 240), (xx, y, kw, 11), border_radius=3)
            self.text(surf, k, INK, xx + 3, y + 1, self.font_s, shadow=False)
            self.text(surf, lbl, (200, 210, 225), xx + kw + 2, y + 1, self.font_s, shadow=False)
            xx += kw + lw + 8
        self.text(surf, "H ajuda  ·  Tab troca  ·  F vira", (140, 150, 170), x0 + w // 2, ch - 20,
                  self.font_s, center=True, shadow=False)

        # ---- abas no topo
        self.tabs = []
        xx = cw - 8
        for label, key in (("GO", "go"), ("XADREZ", "xadrez")):
            img = self.big_text(label, INK if key == self.scene_key else (200, 200, 215), 1)
            bw2 = img.get_width() + 14
            xx -= bw2
            r = pygame.Rect(xx, 8, bw2, 18)
            col = GOLD if key == self.scene_key else (40, 48, 60)
            self.panel_box(surf, r, col, 5)
            surf.blit(img, (xx + 7, 12))
            self.tabs.append((r, key))
            xx -= 4

        # ---- popups (+3 etc.)
        for p in self.popups:
            k = p.t / p.life
            sc = 1.0 + 1.2 * (1 - ease_out_back(min(1.0, p.t / 0.25), 3))
            img = self.big_text(p.text, p.color)
            sh = self.big_text(p.text, INK)
            if sc != 1.0:
                img = pygame.transform.scale_by(img, sc)
                sh = pygame.transform.scale_by(sh, sc)
            alpha = 255 if k < 0.7 else int(255 * (1 - (k - 0.7) / 0.3))
            img.set_alpha(alpha)
            sh.set_alpha(alpha)
            px = p.x - img.get_width() / 2 + math.sin(p.t * 9) * 1.5
            py = p.y - 14 - p.t * 26 - img.get_height() / 2
            surf.blit(sh, (px + 2, py + 2))
            surf.blit(img, (px, py))

        # ---- faixa central (XEQUE!, etc.)
        if self.banner:
            text, color, t0 = self.banner
            k = t - t0
            if k > 1.8:
                self.banner = None
            else:
                ax, ay, aw, ah = self.board_area()
                cy = ay + ah // 2
                grow = ease_out_back(min(1.0, k / 0.3), 2.0)
                fade = 1.0 if k < 1.4 else 1 - (k - 1.4) / 0.4
                band_h = int(46 * grow * fade)
                if band_h > 2:
                    band = pygame.Surface((aw + 20, band_h), pygame.SRCALPHA)
                    band.fill((14, 10, 24, 200))
                    pygame.draw.rect(band, color, (0, 0, aw + 20, 2))
                    pygame.draw.rect(band, color, (0, band_h - 2, aw + 20, 2))
                    surf.blit(band, (ax - 10, cy - band_h // 2))
                    font = self.font_px
                    scale = 3 * grow if fade > 0.5 else 3
                    glyphs = [pygame.transform.scale_by(font.render(c, False, color), scale) for c in text]
                    shads = [pygame.transform.scale_by(font.render(c, False, INK), scale) for c in text]
                    tot = sum(g.get_width() for g in glyphs)
                    xx = ax + aw // 2 - tot // 2
                    for i, (g, s) in enumerate(zip(glyphs, shads)):
                        dy = math.sin(t * 7 + i * 0.5) * 3
                        g.set_alpha(int(255 * fade))
                        yy = cy - g.get_height() // 2 + dy
                        surf.blit(s, (xx + 3, yy + 3))
                        surf.blit(g, (xx, yy))
                        xx += g.get_width()

        # ---- aviso (toast)
        msg, m0 = self.scene.message
        k = self.scene.time - m0
        if msg and k < 3.0:
            ax, ay, aw, ah = self.board_area()
            img = self.font.render(msg, False, WHITE)
            pop = ease_out_back(min(1.0, k / 0.2), 2.5)
            bw2, bh = img.get_width() + 16, img.get_height() + 8
            yy = ch - 26 + int((1 - pop) * 20) + (int((k - 2.6) * 60) if k > 2.6 else 0)
            xx = ax + aw // 2 - bw2 // 2
            self.panel_box(surf, (xx, yy, bw2, bh), (30, 30, 44), 6)
            pygame.draw.rect(surf, accent, (xx, yy, bw2, bh), 1, border_radius=6)
            surf.blit(img, (xx + 8, yy + 4))

        # ---- peça na mão (inclina com o movimento, como carta arrastada)
        spr = self.scene.held_sprite()
        if spr is not None:
            scale = max(1, round(self.board_scale))
            big = pygame.transform.scale_by(spr, scale)
            rot = pygame.transform.rotate(big, self.held_angle)
            mx, my = self.mouse_canvas
            shadow = rot.copy()
            shadow.fill((0, 0, 0, 120), special_flags=pygame.BLEND_RGBA_MIN)
            surf.blit(shadow, (mx - rot.get_width() / 2 + 5, my - rot.get_height() / 2 + 8))
            surf.blit(rot, (mx - rot.get_width() / 2, my - rot.get_height() / 2 - 4))

        self.screen_particles.draw(surf)

        # ---- ajuda
        if self.show_help:
            kw = max(self.font_s.size(a)[0] for a, _ in HELP) + 12
            dw = max(self.font_s.size(b)[0] for _, b in HELP)
            hw, hh = kw + dw + 24, 14 * len(HELP) + 34
            hx, hy = (cw - hw) // 2 + PANEL_W // 2, (ch - hh) // 2
            self.panel_box(surf, (hx, hy, hw, hh), (16, 20, 28), 8)
            pygame.draw.rect(surf, GOLD, (hx, hy, hw, hh), 1, border_radius=8)
            wobble_text(surf, self.font, "CONTROLES", hx + hw // 2, hy + 6, GOLD, t, 1.5, center=True)
            yy = hy + 24
            for a, b in HELP:
                self.text(surf, a, (150, 210, 255), hx + 12, yy, self.font_s)
                self.text(surf, b, (230, 230, 240), hx + 12 + kw, yy, self.font_s)
                yy += 14

    # ----------------------------------------------------------- quadro
    def frame(self, dt):
        self.t += dt
        self.shake.update(dt)
        self.scene.update(dt)
        self.screen_particles.update(dt)
        for p in self.popups:
            p.t += dt
        self.popups = [p for p in self.popups if p.alive]
        # cores do fundo mudam suavemente ao trocar de jogo
        k = 1 - math.exp(-dt * 3)
        for i, target in enumerate(self.scene.theme):
            for j in range(3):
                self.theme[i][j] += (target[j] - self.theme[i][j]) * k
        # peça na mão balança conforme a velocidade do mouse
        vx = (self.mouse_canvas[0] - self.last_mouse_canvas[0]) / max(dt, 1e-3)
        self.last_mouse_canvas = self.mouse_canvas
        target = clamp(-vx * 0.05, -28, 28) + math.sin(self.t * 3) * 3
        self.held_angle += (target - self.held_angle) * (1 - math.exp(-dt * 12))

        self.layout_view(dt)
        self.scene.hover = self.hover_cell() if not (self.drag and self.drag[0] != 1) else self.scene.hover
        self.process_events()

        if self.t > self.next_sheen:
            self.sheen_t0 = self.t
            self.next_sheen = self.t + random.uniform(6, 10)
        sk = (self.t - self.sheen_t0) / 0.9
        sheen = -0.5 + sk * 2.4 if sk < 1 else -5.0

        tw, th = self.scene.tex_size
        if self.board_surf is None or self.board_surf.get_size() != (tw, th):
            self.board_surf = pygame.Surface((tw, th), pygame.SRCALPHA)
        self.board_surf.fill((0, 0, 0, 0))
        self.scene.draw_board(self.board_surf)

        cw, ch = self.gfx.canvas
        overlay = pygame.Surface((cw, ch), pygame.SRCALPHA)
        self.draw_overlay(overlay)

        light = 1.0 + self.hover_tilt[1] * -0.04 + self.hover_tilt[0] * 0.03
        self.gfx.render(self.t, [tuple(c) for c in self.theme], self.view,
                        pygame.image.tobytes(self.board_surf, "RGBA"), (tw, th),
                        pygame.image.tobytes(overlay, "RGBA", True), sheen=sheen,
                        thickness=max(3.0, self.board_scale * 2.5), light=light)

    def screenshot(self, path):
        w, h = self.size
        data = self.ctx.screen.read(viewport=(0, 0, w, h), components=3)
        pygame.image.save(pygame.image.frombytes(data, (w, h), "RGB", True), path)

    def run(self):
        clock = pygame.time.Clock()
        while self.running:
            dt = min(clock.tick(120) / 1000.0, 0.05)
            for e in pygame.event.get():
                self.handle_event(e)
            self.frame(dt)
            pygame.display.flip()
        pygame.quit()


def main(argv=None):
    ap = argparse.ArgumentParser(description="Tabletop pixel art de Xadrez e Go")
    ap.add_argument("--jogo", choices=["xadrez", "go"], default="xadrez", help="mesa inicial")
    ap.add_argument("--largura", type=int, default=1280)
    ap.add_argument("--altura", type=int, default=720)
    args = ap.parse_args(argv)
    App((args.largura, args.altura), args.jogo).run()


if __name__ == "__main__":
    main()
