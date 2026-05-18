"""Food item plus a small particle system used for the eat effect."""

from __future__ import annotations

import math
import random

import pygame

from settings import CELL, ARENA_X, ARENA_Y, COLS, ROWS


class Food:
    """Food token that pulses and glows on the arena grid."""

    def __init__(self, theme: dict) -> None:
        self.theme = theme
        self.pos = (0, 0)
        self.spawn_time = 0
        # Pick an initial position so the food is valid before the first frame.
        self.respawn(set(), 0)

    def respawn(self, occupied: set, time_ms: int) -> bool:
        """Place the food in a random cell that is not occupied by the snake."""
        free = [
            (x, y)
            for x in range(COLS)
            for y in range(ROWS)
            if (x, y) not in occupied
        ]
        if not free:
            return False
        self.pos = random.choice(free)
        self.spawn_time = time_ms
        return True

    def rect(self) -> pygame.Rect:
        x, y = self.pos
        return pygame.Rect(ARENA_X + x * CELL, ARENA_Y + y * CELL, CELL, CELL)

    def draw(self, surface: pygame.Surface, time_ms: int) -> None:
        rect = self.rect()
        cx, cy = rect.center
        # Time since spawn -> drives the pulse animation.
        t = (time_ms - self.spawn_time) / 1000.0
        base_r = CELL * 0.32
        pulse = math.sin(t * 5.0) * (CELL * 0.06)
        r = max(2, int(base_r + pulse))

        # Soft outer glow built on a separate alpha surface.
        glow_surface = pygame.Surface((CELL * 3, CELL * 3), pygame.SRCALPHA)
        gx, gy = glow_surface.get_width() // 2, glow_surface.get_height() // 2
        glow_color = self.theme["food_glow"]
        for layer in range(8, 0, -1):
            alpha = 18 + layer * 6
            pygame.draw.circle(
                glow_surface,
                (*glow_color, alpha),
                (gx, gy),
                int(r + layer * 2),
            )
        surface.blit(glow_surface, (cx - gx, cy - gy))

        # Solid core + highlight.
        pygame.draw.circle(surface, self.theme["food"], (cx, cy), r)
        pygame.draw.circle(
            surface,
            (255, 255, 255),
            (cx - r // 3, cy - r // 3),
            max(1, r // 4),
        )


class Particle:
    """A single short-lived spark used for the eating burst effect."""

    __slots__ = ("x", "y", "vx", "vy", "color", "life", "age")

    def __init__(self, x: float, y: float, color: tuple,
                 vx: float, vy: float, life: int = 600) -> None:
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.color = color
        self.life = life
        self.age = 0

    def update(self, dt_ms: int) -> None:
        # 16 ms ≈ one frame at 60 fps -> normalise the velocity for any dt.
        self.x += self.vx * dt_ms / 16.0
        self.y += self.vy * dt_ms / 16.0
        self.vx *= 0.92
        self.vy *= 0.92
        self.age += dt_ms

    def alive(self) -> bool:
        return self.age < self.life

    def draw(self, surface: pygame.Surface) -> None:
        if not self.alive():
            return
        progress = self.age / self.life
        alpha = max(0, int(255 * (1 - progress)))
        r = max(1, int(3 * (1 - progress)) + 1)
        s = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
        pygame.draw.circle(s, (*self.color, alpha), (r, r), r)
        surface.blit(s, (int(self.x) - r, int(self.y) - r))


def spawn_burst(particles: list, x: float, y: float,
                color: tuple, count: int = 22) -> None:
    """Append a circular burst of particles centred on (x, y)."""
    for _ in range(count):
        angle = random.uniform(0, math.tau)
        speed = random.uniform(1.5, 4.5)
        particles.append(
            Particle(
                x, y, color,
                math.cos(angle) * speed,
                math.sin(angle) * speed,
                life=500 + random.randint(0, 350),
            )
        )
