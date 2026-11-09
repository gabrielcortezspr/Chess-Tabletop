"""Área de transferência e posições salvas para treino."""
from __future__ import annotations

import os

import pygame

POS_DIR = "posicoes"


def _scrap_ready():
    try:
        if not pygame.scrap.get_init():
            pygame.scrap.init()
        return True
    except Exception:  # noqa: BLE001 - sem suporte no sistema
        return False


def copy_text(text: str) -> bool:
    """Copia para a área de transferência. Sempre grava também em posicoes/copiado.txt."""
    os.makedirs(POS_DIR, exist_ok=True)
    with open(os.path.join(POS_DIR, "copiado.txt"), "w", encoding="utf-8") as f:
        f.write(text)
    if _scrap_ready():
        try:
            pygame.scrap.put(pygame.SCRAP_TEXT, text.encode("utf-8"))
            return True
        except Exception:  # noqa: BLE001
            return False
    return False


def paste_text() -> str | None:
    if _scrap_ready():
        try:
            for kind in (pygame.SCRAP_TEXT, "text/plain;charset=utf-8", "UTF8_STRING"):
                data = pygame.scrap.get(kind)
                if data:
                    if isinstance(data, bytes):
                        data = data.decode("utf-8", "ignore")
                    return data.replace("\x00", "").strip()
        except Exception:  # noqa: BLE001
            pass
    # alternativa: arquivo posicoes/colar.txt
    path = os.path.join(POS_DIR, "colar.txt")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    return None


def save_position(game: str, text: str) -> int:
    """Acrescenta uma posição (uma por linha) em posicoes/<jogo>.txt. Retorna o total."""
    os.makedirs(POS_DIR, exist_ok=True)
    path = os.path.join(POS_DIR, f"{game}.txt")
    with open(path, "a", encoding="utf-8") as f:
        f.write(text.replace("\n", " ").strip() + "\n")
    return len(load_positions(game))


def load_positions(game: str) -> list:
    path = os.path.join(POS_DIR, f"{game}.txt")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip() and not line.startswith("#")]
