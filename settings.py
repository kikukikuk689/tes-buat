"""Global configuration and runtime settings for the modern Snake game.

This module collects every tunable knob in one place so the rest of the code
can stay focused on game logic / rendering. Anything you might want to change
later (window size, grid resolution, colour palettes, default speed, ...) is
defined here.
"""

from __future__ import annotations

from pathlib import Path


# ---------------------------------------------------------------------------
# Window / rendering
# ---------------------------------------------------------------------------

# The game window is landscape; the arena on the left is a 9:16 portrait area
# and the right side is the control / info panel.
WINDOW_WIDTH = 960
WINDOW_HEIGHT = 720
FPS = 60

# Grid configuration. 18 cols * 32 rows * 20px cell = 360 x 640 (9:16).
CELL = 20
COLS = 18
ROWS = 32
ARENA_WIDTH = CELL * COLS           # 360
ARENA_HEIGHT = CELL * ROWS          # 640
ARENA_X = 20                        # left padding from window edge
ARENA_Y = 40                        # top padding from window edge

# Right-hand panel placement (control + info).
PANEL_X = ARENA_X + ARENA_WIDTH + 20            # 400
PANEL_Y = ARENA_Y                               # 40
PANEL_WIDTH = WINDOW_WIDTH - PANEL_X - 20       # 540
PANEL_HEIGHT = ARENA_HEIGHT                     # 640


# ---------------------------------------------------------------------------
# Gameplay defaults
# ---------------------------------------------------------------------------

DEFAULT_SPEED = 8           # snake moves per second
DEFAULT_WIN_SCORE = 20      # foods needed to win
DEFAULT_BOT_TARGET_WIN = 5  # bot stops after N wins
DEFAULT_BOT_TARGET_LOSE = 3 # bot stops after N losses


# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------

# Recordings will be written here relative to the project root.
RECORDINGS_DIR = Path("recordings")


# ---------------------------------------------------------------------------
# Visual themes (neon / cyber / soft futuristic)
# ---------------------------------------------------------------------------

THEMES = {
    "Neon Cyber": {
        "bg":            (10, 12, 24),
        "bg_grad":       (20, 25, 45),
        "arena_bg":      (15, 18, 32),
        "grid":          (28, 32, 55),
        "panel_bg":      (18, 20, 35),
        "panel_border":  (60, 70, 110),
        "text":          (220, 230, 255),
        "text_dim":      (140, 150, 180),
        "accent":        (0, 220, 255),
        "accent2":       (255, 90, 200),
        "snake_head":    (0, 255, 200),
        "snake_body":    (0, 180, 240),
        "snake_outline": (10, 20, 35),
        "food":          (255, 70, 130),
        "food_glow":     (255, 150, 200),
        "win":           (80, 255, 160),
        "lose":          (255, 80, 100),
        "rec":           (255, 60, 80),
        "button":        (35, 40, 70),
        "button_hover":  (60, 70, 120),
        "button_active": (0, 220, 255),
        "button_text_active": (10, 12, 24),
    },
    "Soft Futuristic": {
        "bg":            (240, 244, 255),
        "bg_grad":       (215, 225, 250),
        "arena_bg":      (245, 248, 255),
        "grid":          (215, 220, 235),
        "panel_bg":      (250, 250, 255),
        "panel_border":  (195, 205, 225),
        "text":          (40, 50, 80),
        "text_dim":      (120, 130, 160),
        "accent":        (90, 130, 230),
        "accent2":       (230, 100, 170),
        "snake_head":    (90, 200, 160),
        "snake_body":    (130, 200, 220),
        "snake_outline": (255, 255, 255),
        "food":          (240, 110, 130),
        "food_glow":     (255, 200, 210),
        "win":           (90, 200, 120),
        "lose":          (230, 80, 100),
        "rec":           (230, 80, 100),
        "button":        (235, 240, 255),
        "button_hover":  (215, 225, 250),
        "button_active": (90, 130, 230),
        "button_text_active": (255, 255, 255),
    },
    "Sunset Glow": {
        "bg":            (24, 14, 30),
        "bg_grad":       (70, 26, 60),
        "arena_bg":      (30, 18, 38),
        "grid":          (60, 30, 55),
        "panel_bg":      (40, 20, 45),
        "panel_border":  (120, 60, 110),
        "text":          (255, 240, 230),
        "text_dim":      (180, 150, 170),
        "accent":        (255, 180, 80),
        "accent2":       (255, 110, 130),
        "snake_head":    (255, 200, 90),
        "snake_body":    (255, 130, 90),
        "snake_outline": (40, 20, 30),
        "food":          (120, 220, 255),
        "food_glow":     (180, 230, 255),
        "win":           (140, 255, 180),
        "lose":          (255, 90, 120),
        "rec":           (255, 70, 90),
        "button":        (60, 30, 60),
        "button_hover":  (100, 50, 90),
        "button_active": (255, 180, 80),
        "button_text_active": (40, 20, 30),
    },
}
DEFAULT_THEME = "Neon Cyber"


# ---------------------------------------------------------------------------
# Mutable settings container shared across scenes.
# ---------------------------------------------------------------------------

class Settings:
    """Runtime configuration the user can change via the Settings screen."""

    def __init__(self) -> None:
        self.speed: int = DEFAULT_SPEED
        self.win_score: int = DEFAULT_WIN_SCORE
        self.bot_target_win: int = DEFAULT_BOT_TARGET_WIN
        self.bot_target_lose: int = DEFAULT_BOT_TARGET_LOSE
        self.theme_name: str = DEFAULT_THEME
        self.sound_enabled: bool = True

    # ------------------------------------------------------------------
    @property
    def theme(self) -> dict:
        """Return the colour palette for the currently selected theme."""
        return THEMES[self.theme_name]

    def cycle_theme(self) -> None:
        """Switch to the next theme in the THEMES dict."""
        names = list(THEMES.keys())
        idx = names.index(self.theme_name)
        self.theme_name = names[(idx + 1) % len(names)]
