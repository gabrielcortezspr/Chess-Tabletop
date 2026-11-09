"""Loop principal: janela pygame + OpenGL, entrada, câmera e HUD."""
from __future__ import annotations

import argparse
import os
import time

import moderngl
import pygame

from .camera import OrbitCamera
from .chess_scene import ChessScene
from .go_scene import GoScene
from .renderer import InstanceBatch, Renderer

HELP_TEXT = [
    ("CÂMERA", None),
    ("Direito + arrastar / Q E / setas", "girar ao redor do tabuleiro"),
    ("Meio + arrastar / Shift+direito / WASD", "deslocar (sempre perto do tabuleiro)"),
    ("Roda do mouse / PgUp PgDn", "zoom"),
    ("F  ·  Espaço", "ver do outro lado  ·  visão padrão"),
    ("GERAL", None),
    ("Tab", "alternar Xadrez / Go"),
    ("M", "alternar Modo Jogo / Modo Livre"),
    ("Z  ·  R", "desfazer  ·  nova partida / reiniciar"),
    ("[ ]  ·  F12", "tamanho do pixel  ·  screenshot"),
    ("H  ·  Ctrl+Q", "ajuda  ·  sair"),
    ("XADREZ", None),
    ("Jogo", "clique na peça e no destino"),
    ("", "G desiste  ·  promoção: 1-4"),
    ("Livre", "clique pega/solta a peça (bandejas também)"),
    ("", "1-6 nova peça (Shift = preta)  ·  C troca cor"),
    ("", "Del descarta  ·  X esvazia  ·  Enter joga daqui"),
    ("GO", None),
    ("Jogo", "clique joga  ·  P passa  ·  G desiste"),
    ("", "K komi  ·  B tamanho 9/13/19  ·  T território"),
    ("Contagem", "2 passes: clique nos grupos mortos, Enter"),
    ("Livre", "clique coloca/remove  ·  C cor  ·  Enter joga"),
]


class App:
    def __init__(self, size=(1280, 760), game="xadrez", pixel_scale=3, hidden=False):
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
        pygame.display.set_caption("Tabletop Voxel - Xadrez & Go")
        self.ctx = moderngl.create_context()
        self.size = size
        self.renderer = Renderer(self.ctx, size, pixel_scale)
        self.camera = OrbitCamera()
        self.scenes = {"xadrez": ChessScene(), "go": GoScene()}
        self.scene_key = "go" if game == "go" else "xadrez"
        self.show_help = False
        self.running = True
        self.mouse = (0, 0)
        self.drag = None          # (botão, x, y, moveu?)
        self.hud_key = None
        self.hud_scale = 2
        self.font_title = pygame.font.Font(None, 26)
        self.font = pygame.font.Font(None, 18)
        self.font_small = pygame.font.Font(None, 16)
        self.fps = 0.0
        self.global_msg = ("", -10.0)

    @property
    def scene(self):
        return self.scenes[self.scene_key]

    # ----------------------------------------------------------- entrada
    def handle_event(self, e):
        if e.type == pygame.QUIT:
            self.running = False
        elif e.type in (pygame.VIDEORESIZE,) or (e.type == pygame.WINDOWSIZECHANGED):
            w, h = pygame.display.get_window_size()
            self.size = (w, h)
            self.ctx.screen.viewport = (0, 0, w, h)
            self.renderer.resize((w, h))
            self.hud_key = None
        elif e.type == pygame.MOUSEMOTION:
            self.mouse = e.pos
            if self.drag:
                btn, sx, sy, moved = self.drag
                dx, dy = e.rel
                if abs(e.pos[0] - sx) + abs(e.pos[1] - sy) > 5:
                    moved = True
                self.drag = (btn, sx, sy, moved)
                shift = pygame.key.get_mods() & pygame.KMOD_SHIFT
                if btn == 3 and not shift:
                    self.camera.orbit(dx, dy)
                elif btn == 2 or (btn == 3 and shift):
                    self.camera.pan(dx, dy)
        elif e.type == pygame.MOUSEBUTTONDOWN:
            if e.button in (1, 2, 3):
                self.drag = (e.button, e.pos[0], e.pos[1], False)
        elif e.type == pygame.MOUSEBUTTONUP:
            if self.drag and self.drag[0] == e.button == 1 and not self.drag[3]:
                shift = bool(pygame.key.get_mods() & pygame.KMOD_SHIFT)
                cell = self.scene.pick(self.camera, *e.pos, *self.size)
                self.scene.click(cell, shift)
            self.drag = None
        elif e.type == pygame.MOUSEWHEEL:
            self.camera.zoom(e.y)
        elif e.type == pygame.KEYDOWN:
            self.handle_key(e.key, e.mod)

    def handle_key(self, key, mod):
        if key == pygame.K_q and mod & pygame.KMOD_CTRL:
            self.running = False
            return
        if self.scene.key(key, mod):
            return
        if key == pygame.K_TAB:
            self.scene_key = "go" if self.scene_key == "xadrez" else "xadrez"
            self.camera.focus_radius = self.scene.focus_radius
            self.flash(f"Mesa: {self.scene.name}")
        elif key == pygame.K_m:
            self.scene.toggle_mode()
        elif key == pygame.K_r:
            self.scene.reset()
        elif key == pygame.K_z:
            self.scene.undo()
        elif key == pygame.K_h:
            self.show_help = not self.show_help
        elif key == pygame.K_f:
            self.camera.t_yaw += 180
        elif key == pygame.K_SPACE:
            yaw = round(self.camera.t_yaw / 180.0) * 180.0
            self.camera.home(yaw)
        elif key == pygame.K_LEFTBRACKET:
            self.renderer.set_pixel_scale(self.renderer.pixel_scale - 1)
            self.flash(f"Pixel: {self.renderer.pixel_scale}x")
        elif key == pygame.K_RIGHTBRACKET:
            self.renderer.set_pixel_scale(self.renderer.pixel_scale + 1)
            self.flash(f"Pixel: {self.renderer.pixel_scale}x")
        elif key == pygame.K_F12:
            os.makedirs("screenshots", exist_ok=True)
            path = time.strftime("screenshots/tabletop_%Y%m%d_%H%M%S.png")
            self.screenshot(path)
            self.flash("Screenshot salvo: " + path)

    def flash(self, text):
        self.global_msg = (text, time.time())

    def poll_keys(self, dt):
        k = pygame.key.get_pressed()
        mods = pygame.key.get_mods()
        if mods & pygame.KMOD_CTRL:
            return
        sp = 600 * dt
        if k[pygame.K_LEFT] or k[pygame.K_q]:
            self.camera.orbit(-sp * 0.6, 0)
        if k[pygame.K_RIGHT] or k[pygame.K_e]:
            self.camera.orbit(sp * 0.6, 0)
        if k[pygame.K_UP]:
            self.camera.orbit(0, sp * 0.4)
        if k[pygame.K_DOWN]:
            self.camera.orbit(0, -sp * 0.4)
        if k[pygame.K_w]:
            self.camera.pan(0, sp)
        if k[pygame.K_s]:
            self.camera.pan(0, -sp)
        if k[pygame.K_a]:
            self.camera.pan(sp, 0)
        if k[pygame.K_d]:
            self.camera.pan(-sp, 0)
        if k[pygame.K_PAGEUP]:
            self.camera.zoom(3 * dt)
        if k[pygame.K_PAGEDOWN]:
            self.camera.zoom(-3 * dt)

    # ----------------------------------------------------------- HUD
    def draw_hud(self):
        title, lines, hints = self.scene.hud()
        msg, t0 = self.scene.message
        smsg_alpha = max(0.0, 1.0 - max(0.0, self.scene.time - t0 - 2.5) / 0.6) if msg else 0.0
        gmsg, g0 = self.global_msg
        gmsg_alpha = max(0.0, 1.0 - max(0.0, time.time() - g0 - 1.5) / 0.5) if gmsg else 0.0
        key = (title, tuple(lines), tuple(hints), msg, round(smsg_alpha, 1), gmsg, round(gmsg_alpha, 1),
               self.show_help, self.size, self.scene_key)
        if key == self.hud_key:
            return
        self.hud_key = key
        w, h = self.size[0] // self.hud_scale, self.size[1] // self.hud_scale
        surf = pygame.Surface((w, h), pygame.SRCALPHA)

        def text(font, s, color, x, y, shadow=True):
            if shadow:
                surf.blit(font.render(s, False, (0, 0, 0)), (x + 1, y + 1))
            img = font.render(s, False, color)
            surf.blit(img, (x, y))
            return img.get_width(), img.get_height()

        # painel de status
        rendered = [self.font.render(s, False, c) for s, c in lines]
        tw = max([self.font_title.size(title)[0]] + [r.get_width() for r in rendered]) + 16
        th = 26 + sum(r.get_height() + 2 for r in rendered) + 6
        panel = pygame.Surface((tw, th), pygame.SRCALPHA)
        panel.fill((14, 10, 26, 190))
        pygame.draw.rect(panel, (255, 210, 120, 220), panel.get_rect(), 1)
        surf.blit(panel, (6, 6))
        text(self.font_title, title, (255, 214, 120), 14, 11)
        y = 32
        for (s, c) in lines:
            _, hh = text(self.font, s, c, 14, y)
            y += hh + 2

        # abas de jogo no canto superior direito
        tabs = [("XADREZ", "xadrez"), ("GO", "go")]
        x = w - 8
        for label, k in reversed(tabs):
            img = self.font.render(label, False, (20, 14, 30) if k == self.scene_key else (220, 220, 230))
            bw = img.get_width() + 12
            x -= bw
            rect = pygame.Rect(x, 8, bw, 16)
            pygame.draw.rect(surf, (255, 210, 120, 230) if k == self.scene_key else (30, 24, 50, 200), rect)
            surf.blit(img, (x + 6, 10))
            x -= 4
        text(self.font_small, "Tab troca  ·  H ajuda", (200, 200, 220), w - 120, 28)

        # dicas na parte de baixo (quebra em várias linhas se preciso)
        rows, cur = [], ""
        for hnt in hints:
            cand = (cur + "   ·   " + hnt) if cur else hnt
            if self.font_small.size(cand)[0] > w - 20 and cur:
                rows.append(cur)
                cur = hnt
            else:
                cur = cand
        rows.append(cur + "   ·   Botão direito: girar  ·  Roda: zoom")
        bar_h = 6 + 13 * len(rows)
        bar = pygame.Surface((w, bar_h), pygame.SRCALPHA)
        bar.fill((14, 10, 26, 170))
        surf.blit(bar, (0, h - bar_h))
        for i, r in enumerate(rows):
            text(self.font_small, r, (220, 220, 235), 8, h - bar_h + 3 + i * 13)

        # avisos
        for m, a, yy in ((msg, smsg_alpha, 70), (gmsg, gmsg_alpha, 90)):
            if m and a > 0:
                img = self.font_title.render(m, False, (255, 240, 170))
                bx = (w - img.get_width()) // 2
                box = pygame.Surface((img.get_width() + 16, img.get_height() + 8), pygame.SRCALPHA)
                box.fill((14, 10, 26, int(200 * a)))
                surf.blit(box, (bx - 8, h - bar_h - yy - 4))
                img.set_alpha(int(255 * a))
                sh = self.font_title.render(m, False, (0, 0, 0))
                sh.set_alpha(int(255 * a))
                surf.blit(sh, (bx + 1, h - bar_h - yy + 1))
                surf.blit(img, (bx, h - bar_h - yy))

        if self.show_help:
            kw = max(self.font_small.size(a)[0] for a, b in HELP_TEXT if b is not None) + 14
            dw = max(self.font_small.size(b)[0] for a, b in HELP_TEXT if b is not None)
            hw, hh = min(w - 20, kw + dw + 36), 14 * len(HELP_TEXT) + 20
            hx, hy = (w - hw) // 2, max(40, (h - hh) // 2)
            box = pygame.Surface((hw, hh), pygame.SRCALPHA)
            box.fill((10, 8, 20, 235))
            pygame.draw.rect(box, (255, 210, 120), box.get_rect(), 1)
            surf.blit(box, (hx, hy))
            yy = hy + 10
            for a, b in HELP_TEXT:
                if b is None:
                    text(self.font, a, (255, 214, 120), hx + 10, yy)
                else:
                    text(self.font_small, a, (180, 220, 255), hx + 14, yy + 1)
                    text(self.font_small, b, (230, 230, 240), hx + 14 + kw, yy + 1)
                yy += 14

        self.renderer.upload_hud(pygame.image.tobytes(surf, "RGBA", True), (w, h))

    # ----------------------------------------------------------- quadro
    def frame(self, dt):
        self.poll_keys(dt)
        self.camera.focus_radius = self.scene.focus_radius
        self.camera.update(dt)
        self.scene.update(dt)
        if not self.drag or self.drag[0] == 1:
            self.scene.set_hover(self.scene.pick(self.camera, *self.mouse, *self.size))
        batch = InstanceBatch()
        self.scene.build(batch)
        self.draw_hud()
        self.renderer.render(batch.array(), self.camera)

    def screenshot(self, path):
        w, h = self.size
        data = self.ctx.screen.read(viewport=(0, 0, w, h), components=3)
        img = pygame.image.frombytes(data, (w, h), "RGB", True)
        pygame.image.save(img, path)

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
    ap = argparse.ArgumentParser(description="Tabletop voxel de Xadrez e Go")
    ap.add_argument("--jogo", choices=["xadrez", "go"], default="xadrez", help="mesa inicial")
    ap.add_argument("--pixel", type=int, default=3, help="tamanho do pixel (1 = sem pixelização)")
    ap.add_argument("--largura", type=int, default=1280)
    ap.add_argument("--altura", type=int, default=760)
    args = ap.parse_args(argv)
    App((args.largura, args.altura), args.jogo, args.pixel).run()


if __name__ == "__main__":
    main()
