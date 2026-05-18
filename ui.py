"""Reusable UI primitives: buttons, text, panel + arena background."""

from __future__ import annotations

from typing import Callable, Optional

import pygame

from settings import (
    ARENA_HEIGHT,
    ARENA_WIDTH,
    ARENA_X,
    ARENA_Y,
    CELL,
    COLS,
    PANEL_HEIGHT,
    PANEL_WIDTH,
    PANEL_X,
    PANEL_Y,
    ROWS,
)


# Cache for the rendered window background gradient. Building one per frame is
# expensive, so we keep it keyed by (top, bottom, width, height).
_BG_CACHE: dict = {}


class Button:
    """A clickable button with optional icon arrow and toggle state."""

    def __init__(
        self,
        rect,
        label: str,
        callback: Optional[Callable[[], None]] = None,
        *,
        font: pygame.font.Font,
        theme: dict,
        toggled: bool = False,
        icon: Optional[str] = None,
    ) -> None:
        self.rect = pygame.Rect(rect)
        self.label = label
        self.callback = callback
        self.font = font
        self.theme = theme
        self.toggled = toggled
        self.hover = False
        self.icon = icon  # one of: "up", "down", "left", "right", "rec"
        self.enabled = True

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------
    def set_label(self, label: str) -> None:
        self.label = label

    def set_toggled(self, toggled: bool) -> None:
        self.toggled = toggled

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------
    def handle_event(self, event: pygame.event.Event) -> bool:
        if not self.enabled:
            return False
        if event.type == pygame.MOUSEMOTION:
            self.hover = self.rect.collidepoint(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos) and self.callback:
                self.callback()
                return True
        return False

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------
    def draw(self, surface: pygame.Surface) -> None:
        theme = self.theme
        if not self.enabled:
            base = theme["button"]
            border = theme["panel_border"]
            text_color = theme["text_dim"]
        elif self.toggled:
            base = theme["button_active"]
            border = theme["button_active"]
            text_color = theme.get("button_text_active", (10, 12, 24))
        elif self.hover:
            base = theme["button_hover"]
            border = theme["accent"]
            text_color = theme["text"]
        else:
            base = theme["button"]
            border = theme["panel_border"]
            text_color = theme["text"]

        pygame.draw.rect(surface, base, self.rect, border_radius=10)
        pygame.draw.rect(surface, border, self.rect, width=2, border_radius=10)

        if self.icon:
            self._draw_icon(surface, text_color)
        if self.label:
            label_surface = self.font.render(self.label, True, text_color)
            label_rect = label_surface.get_rect(center=self.rect.center)
            surface.blit(label_surface, label_rect)

    def _draw_icon(self, surface: pygame.Surface, color: tuple) -> None:
        cx, cy = self.rect.center
        size = min(self.rect.width, self.rect.height) * 0.35
        if self.icon == "up":
            pts = [(cx, cy - size * 0.6),
                   (cx - size * 0.6, cy + size * 0.4),
                   (cx + size * 0.6, cy + size * 0.4)]
        elif self.icon == "down":
            pts = [(cx, cy + size * 0.6),
                   (cx - size * 0.6, cy - size * 0.4),
                   (cx + size * 0.6, cy - size * 0.4)]
        elif self.icon == "left":
            pts = [(cx - size * 0.6, cy),
                   (cx + size * 0.4, cy - size * 0.6),
                   (cx + size * 0.4, cy + size * 0.6)]
        elif self.icon == "right":
            pts = [(cx + size * 0.6, cy),
                   (cx - size * 0.4, cy - size * 0.6),
                   (cx - size * 0.4, cy + size * 0.6)]
        elif self.icon == "rec":
            pygame.draw.circle(
                surface, (255, 70, 80),
                (int(cx - self.rect.width * 0.35), int(cy)),
                max(4, int(size * 0.5)),
            )
            return
        else:
            return
        pygame.draw.polygon(surface, color, pts)


# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------

def draw_text(
    surface: pygame.Surface,
    text: str,
    font: pygame.font.Font,
    color: tuple,
    x: int,
    y: int,
    *,
    center: bool = False,
) -> pygame.Rect:
    """Render `text` and return the destination rect."""
    surf = font.render(text, True, color)
    rect = surf.get_rect()
    if center:
        rect.center = (x, y)
    else:
        rect.topleft = (x, y)
    surface.blit(surf, rect)
    return rect


def draw_background(surface: pygame.Surface, theme: dict) -> None:
    """Vertical-gradient background covering the full window (cached)."""
    top = tuple(theme["bg"])
    bot = tuple(theme["bg_grad"])
    w, h = surface.get_size()
    key = (top, bot, w, h)
    cached = _BG_CACHE.get(key)
    if cached is None:
        cached = pygame.Surface((w, h)).convert()
        for y in range(h):
            t = y / max(1, h - 1)
            r = int(top[0] * (1 - t) + bot[0] * t)
            g = int(top[1] * (1 - t) + bot[1] * t)
            b = int(top[2] * (1 - t) + bot[2] * t)
            pygame.draw.line(cached, (r, g, b), (0, y), (w, y))
        _BG_CACHE[key] = cached
    surface.blit(cached, (0, 0))


def draw_panel_background(surface: pygame.Surface, theme: dict) -> None:
    panel_rect = pygame.Rect(PANEL_X, PANEL_Y, PANEL_WIDTH, PANEL_HEIGHT)
    pygame.draw.rect(surface, theme["panel_bg"], panel_rect, border_radius=14)
    pygame.draw.rect(
        surface, theme["panel_border"], panel_rect, width=2, border_radius=14
    )


def draw_arena_background(surface: pygame.Surface, theme: dict) -> None:
    """Arena rectangle plus a subtle grid for the modern look."""
    arena_rect = pygame.Rect(ARENA_X, ARENA_Y, ARENA_WIDTH, ARENA_HEIGHT)
    pygame.draw.rect(surface, theme["arena_bg"], arena_rect, border_radius=14)

    grid_color = theme["grid"]
    for c in range(1, COLS):
        x = ARENA_X + c * CELL
        pygame.draw.line(
            surface, grid_color,
            (x, ARENA_Y + 2), (x, ARENA_Y + ARENA_HEIGHT - 2), 1,
        )
    for r in range(1, ROWS):
        y = ARENA_Y + r * CELL
        pygame.draw.line(
            surface, grid_color,
            (ARENA_X + 2, y), (ARENA_X + ARENA_WIDTH - 2, y), 1,
        )

    pygame.draw.rect(
        surface, theme["panel_border"], arena_rect, width=2, border_radius=14,
    )
