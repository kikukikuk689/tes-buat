"""Snake entity with expressive head, gradient body and glow."""

from __future__ import annotations

import pygame

from settings import CELL, ARENA_X, ARENA_Y, COLS, ROWS


# Direction vectors used everywhere else in the project.
DIR_UP = (0, -1)
DIR_DOWN = (0, 1)
DIR_LEFT = (-1, 0)
DIR_RIGHT = (1, 0)


class Snake:
    """The player character. Stores cells, direction, growth queue and look."""

    def __init__(self, theme: dict) -> None:
        self.theme = theme
        self.reset()

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------
    def reset(self) -> None:
        """Re-spawn the snake in the centre of the arena, length = 3."""
        cx, cy = COLS // 2, ROWS // 2
        # Body is ordered from head (index 0) to tail.
        self.body = [(cx, cy), (cx, cy + 1), (cx, cy + 2)]
        self.direction = DIR_UP
        self.pending_direction = self.direction
        self.grow_pending = 0
        # Mouth animates open briefly when the snake eats.
        self.mouth_open = 0.0
        self.alive = True

    def set_direction(self, new_dir: tuple) -> None:
        """Queue a direction change. Direct 180° reversals are ignored."""
        if new_dir[0] == -self.direction[0] and new_dir[1] == -self.direction[1]:
            return
        self.pending_direction = new_dir

    def head(self) -> tuple:
        return self.body[0]

    def step(self) -> bool:
        """Advance one grid cell. Returns False if the snake died."""
        self.direction = self.pending_direction
        hx, hy = self.body[0]
        nx, ny = hx + self.direction[0], hy + self.direction[1]

        # Hit the wall?
        if nx < 0 or nx >= COLS or ny < 0 or ny >= ROWS:
            self.alive = False
            return False

        # Hit its own body? (the tail is allowed because it will move out.)
        if (nx, ny) in self.body[:-1]:
            self.alive = False
            return False

        self.body.insert(0, (nx, ny))
        if self.grow_pending > 0:
            self.grow_pending -= 1
        else:
            self.body.pop()

        # Decay the eating-mouth animation a little each step.
        self.mouth_open = max(0.0, self.mouth_open - 0.15)
        return True

    def grow(self, n: int = 1) -> None:
        """Queue some extra growth and trigger the mouth-open animation."""
        self.grow_pending += n
        self.mouth_open = 1.0

    def occupies(self, cell: tuple) -> bool:
        return cell in self.body

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------
    def _cell_rect(self, cx: int, cy: int) -> pygame.Rect:
        return pygame.Rect(ARENA_X + cx * CELL, ARENA_Y + cy * CELL, CELL, CELL)

    def draw(self, surface: pygame.Surface, time_ms: int) -> None:
        """Render the snake with gradient body, glow and an expressive head."""
        n = len(self.body)
        # Soft outer glow underlay around the whole body.
        glow = pygame.Surface((surface.get_width(), surface.get_height()),
                              pygame.SRCALPHA)
        for cx, cy in self.body:
            rect = self._cell_rect(cx, cy)
            pygame.draw.rect(
                glow,
                (*self.theme["snake_head"], 35),
                rect.inflate(10, 10),
                border_radius=12,
            )
        surface.blit(glow, (0, 0))

        # Gradient body from head colour -> body colour along the length.
        head_color = self.theme["snake_head"]
        body_color = self.theme["snake_body"]
        outline_color = self.theme["snake_outline"]
        for idx, (cx, cy) in enumerate(self.body):
            t = idx / max(1, n - 1)
            r = int(head_color[0] * (1 - t) + body_color[0] * t)
            g = int(head_color[1] * (1 - t) + body_color[1] * t)
            b = int(head_color[2] * (1 - t) + body_color[2] * t)
            rect = self._cell_rect(cx, cy)
            # outer rounded rect (slightly bigger, lighter for "rim light").
            pygame.draw.rect(
                surface,
                (min(255, r + 40), min(255, g + 40), min(255, b + 40)),
                rect.inflate(-1, -1),
                border_radius=8,
            )
            # body fill
            pygame.draw.rect(surface, (r, g, b),
                             rect.inflate(-4, -4), border_radius=7)
            # subtle outline
            pygame.draw.rect(surface, outline_color,
                             rect.inflate(-1, -1), width=1, border_radius=8)

        # Expressive head: eyes + mouth on top of the head cell.
        self._draw_head(surface)

    def _draw_head(self, surface: pygame.Surface) -> None:
        """Draw eyes (with pupils that look forward) and an animated mouth."""
        hx, hy = self.body[0]
        rect = self._cell_rect(hx, hy)
        cx_px, cy_px = rect.centerx, rect.centery
        dx, dy = self.direction

        eye_offset = CELL * 0.22
        eye_radius = max(2, int(CELL * 0.14))
        pupil_radius = max(1, int(CELL * 0.07))

        # Perpendicular direction to place the two eyes symmetrically.
        perp = (-dy, dx)
        ex1 = int(cx_px + dx * eye_offset + perp[0] * eye_offset)
        ey1 = int(cy_px + dy * eye_offset + perp[1] * eye_offset)
        ex2 = int(cx_px + dx * eye_offset - perp[0] * eye_offset)
        ey2 = int(cy_px + dy * eye_offset - perp[1] * eye_offset)

        # White sclera.
        pygame.draw.circle(surface, (245, 245, 250), (ex1, ey1), eye_radius)
        pygame.draw.circle(surface, (245, 245, 250), (ex2, ey2), eye_radius)
        # Pupils pulled slightly forward in the movement direction.
        pupil_shift = eye_radius * 0.45
        pygame.draw.circle(
            surface, (20, 20, 35),
            (int(ex1 + dx * pupil_shift), int(ey1 + dy * pupil_shift)),
            pupil_radius,
        )
        pygame.draw.circle(
            surface, (20, 20, 35),
            (int(ex2 + dx * pupil_shift), int(ey2 + dy * pupil_shift)),
            pupil_radius,
        )

        # Mouth: a small rectangle in front of the head that grows when eating.
        mouth_cx = int(cx_px + dx * (CELL * 0.40))
        mouth_cy = int(cy_px + dy * (CELL * 0.40))
        long_side = int(CELL * (0.22 + 0.22 * self.mouth_open))
        short_side = int(CELL * (0.06 + 0.18 * self.mouth_open))
        if dx == 0:
            mouth_rect = pygame.Rect(0, 0, long_side, short_side)
        else:
            mouth_rect = pygame.Rect(0, 0, short_side, long_side)
        mouth_rect.center = (mouth_cx, mouth_cy)
        pygame.draw.rect(surface, (40, 20, 35), mouth_rect, border_radius=3)
