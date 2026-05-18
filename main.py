"""Entry point: window/loop, scenes (main menu, settings) and sound bootstrap."""

from __future__ import annotations

import math
import sys
from typing import Dict

import pygame

from game import Game
from settings import FPS, Settings, WINDOW_HEIGHT, WINDOW_WIDTH
from ui import Button, draw_background, draw_text


# ---------------------------------------------------------------------------
# Sound generation (synthesised so we don't need any external audio assets).
# ---------------------------------------------------------------------------

def _build_sounds() -> Dict[str, pygame.mixer.Sound]:
    """Synthesise the click/eat/win/lose sounds at startup.

    Generation is done with numpy if available so the audio cues are pleasant.
    If anything goes wrong (no audio device, numpy missing, ...) we silently
    return an empty mapping; the game then just plays no sound.
    """
    sounds: Dict[str, pygame.mixer.Sound] = {}
    try:
        # Set up the mixer if it isn't yet (e.g. headless boot).
        if not pygame.mixer.get_init():
            try:
                pygame.mixer.init(frequency=22050, channels=1, buffer=512)
            except pygame.error:
                return sounds

        import numpy as np  # noqa: WPS433 - optional at runtime
    except Exception:
        return sounds

    init_info = pygame.mixer.get_init()
    if not init_info:
        return sounds
    sample_rate, _, channels = init_info

    def _envelope(arr, attack: float = 0.005, release: float = 0.12):
        env = np.ones_like(arr)
        a = max(1, int(sample_rate * attack))
        r = max(1, int(sample_rate * release))
        env[:a] = np.linspace(0.0, 1.0, a)
        env[-r:] = np.linspace(1.0, 0.0, r)
        return arr * env

    def _to_sound(arr, vol: float = 0.4) -> pygame.mixer.Sound:
        arr = np.clip(arr * vol, -1.0, 1.0)
        samples = (arr * 32767).astype(np.int16)
        if channels == 2:
            samples = np.stack([samples, samples], axis=-1)
        return pygame.sndarray.make_sound(samples)

    def tone(freq: float, duration_ms: int, *, vol: float = 0.4):
        n = int(sample_rate * duration_ms / 1000.0)
        t = np.arange(n) / sample_rate
        wave = np.sin(2 * np.pi * freq * t)
        return _to_sound(_envelope(wave, release=min(0.12, duration_ms / 2000.0)), vol)

    def chord(freqs, duration_ms: int, *, vol: float = 0.4):
        n = int(sample_rate * duration_ms / 1000.0)
        t = np.arange(n) / sample_rate
        wave = sum(np.sin(2 * np.pi * f * t) for f in freqs) / len(freqs)
        return _to_sound(_envelope(wave, release=0.15), vol)

    def sweep(start_freq: float, end_freq: float, duration_ms: int,
              *, vol: float = 0.4):
        n = int(sample_rate * duration_ms / 1000.0)
        t = np.arange(n) / sample_rate
        freqs = np.linspace(start_freq, end_freq, n)
        phase = 2 * np.pi * np.cumsum(freqs) / sample_rate
        wave = np.sin(phase)
        return _to_sound(_envelope(wave, release=0.15), vol)

    try:
        sounds["click"] = tone(440, 60, vol=0.3)
        sounds["eat"] = sweep(500, 880, 120, vol=0.4)
        sounds["lose"] = chord([220, 165, 110], 450, vol=0.5)
        sounds["win"] = chord([523, 659, 784, 988], 600, vol=0.5)
    except Exception:
        return {}
    return sounds


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

class App:
    """Top-level controller. Owns the window, fonts, sounds and current scene."""

    def __init__(self) -> None:
        # Try to pre-init the mixer for better latency. Safe to fail.
        try:
            pygame.mixer.pre_init(22050, -16, 1, 512)
        except pygame.error:
            pass

        pygame.init()
        pygame.display.set_caption("Snake Neon")
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        self.clock = pygame.time.Clock()
        self.fonts = self._load_fonts()

        self.settings = Settings()
        self.sounds = _build_sounds()
        self.scene = None
        self.show_menu()

    # ------------------------------------------------------------------
    def _load_fonts(self) -> dict:
        pygame.font.init()
        try:
            font_name = (pygame.font.match_font("dejavusans")
                         or pygame.font.get_default_font())
        except Exception:
            font_name = pygame.font.get_default_font()
        return {
            "xl": pygame.font.Font(font_name, 48),
            "title": pygame.font.Font(font_name, 26),
            "body": pygame.font.Font(font_name, 18),
            "small": pygame.font.Font(font_name, 14),
        }

    # ------------------------------------------------------------------
    # Scene transitions
    # ------------------------------------------------------------------
    def show_menu(self) -> None:
        self.scene = MainMenu(self)

    def start_manual(self) -> None:
        self.scene = Game(self, bot_mode=False)
        self.play_sound("click")

    def start_bot(self) -> None:
        self.scene = Game(self, bot_mode=True)
        self.play_sound("click")

    def show_settings(self) -> None:
        self.scene = SettingsScene(self)
        self.play_sound("click")

    def return_to_menu(self) -> None:
        self.show_menu()
        self.play_sound("click")

    def play_sound(self, name: str) -> None:
        if not self.settings.sound_enabled:
            return
        snd = self.sounds.get(name)
        if snd is not None:
            try:
                snd.play()
            except pygame.error:
                pass

    # ------------------------------------------------------------------
    def run(self) -> None:
        running = True
        while running:
            dt_ms = self.clock.tick(FPS)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                else:
                    self.scene.handle_event(event)
            self.scene.update(dt_ms)
            self.scene.draw(self.screen)
            pygame.display.flip()
        pygame.quit()
        sys.exit(0)


# ---------------------------------------------------------------------------
# Main menu scene
# ---------------------------------------------------------------------------

class MainMenu:
    """Title screen with Play Manual / Bot Mode / Settings / Quit."""

    def __init__(self, app: App) -> None:
        self.app = app
        self.theme = app.settings.theme
        font_body = app.fonts["body"]

        cx = WINDOW_WIDTH // 2
        button_w, button_h = 260, 50
        gap = 18
        start_y = WINDOW_HEIGHT // 2

        self.buttons = [
            Button((cx - button_w // 2, start_y, button_w, button_h),
                   "Play Manual", app.start_manual,
                   font=font_body, theme=self.theme),
            Button((cx - button_w // 2, start_y + (button_h + gap),
                    button_w, button_h),
                   "Bot Mode", app.start_bot,
                   font=font_body, theme=self.theme),
            Button((cx - button_w // 2, start_y + (button_h + gap) * 2,
                    button_w, button_h),
                   "Settings", app.show_settings,
                   font=font_body, theme=self.theme),
            Button((cx - button_w // 2, start_y + (button_h + gap) * 3,
                    button_w, button_h),
                   "Quit", self._quit,
                   font=font_body, theme=self.theme),
        ]

    # ------------------------------------------------------------------
    def _quit(self) -> None:
        pygame.event.post(pygame.event.Event(pygame.QUIT))

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self._quit()
            return
        for btn in self.buttons:
            btn.handle_event(event)

    def update(self, dt_ms: int) -> None:
        return None

    def draw(self, surface: pygame.Surface) -> None:
        # Pick up theme changes coming back from the settings screen.
        self.theme = self.app.settings.theme
        for btn in self.buttons:
            btn.theme = self.theme

        draw_background(surface, self.theme)
        self._draw_decoration(surface)

        font_xl = self.app.fonts["xl"]
        font_body = self.app.fonts["body"]
        font_small = self.app.fonts["small"]

        draw_text(
            surface, "SNAKE NEON", font_xl, self.theme["accent"],
            WINDOW_WIDTH // 2, WINDOW_HEIGHT // 4 - 10, center=True,
        )
        draw_text(
            surface, "Modern PC Snake Game with Bot + Recording",
            font_body, self.theme["text_dim"],
            WINDOW_WIDTH // 2, WINDOW_HEIGHT // 4 + 34, center=True,
        )

        for btn in self.buttons:
            btn.draw(surface)

        draw_text(
            surface, "WASD / Arrows  to move    R = Restart    Esc = Menu",
            font_small, self.theme["text_dim"],
            WINDOW_WIDTH // 2, WINDOW_HEIGHT - 28, center=True,
        )

    def _draw_decoration(self, surface: pygame.Surface) -> None:
        """Soft animated snake-like curve behind the title."""
        cx = WINDOW_WIDTH // 2
        cy = WINDOW_HEIGHT // 2 - 20
        head = self.theme["snake_head"]
        body = self.theme["snake_body"]
        now = pygame.time.get_ticks() / 600.0
        for i in range(40):
            t = i / 39.0
            x = cx + math.sin(t * 6 + now) * 280
            y = cy - 120 + math.cos(t * 4 + now * 0.7) * 50
            r = int(7 + math.sin(t * 3 + now) * 4)
            color = (
                int(head[0] * (1 - t) + body[0] * t),
                int(head[1] * (1 - t) + body[1] * t),
                int(head[2] * (1 - t) + body[2] * t),
            )
            glow = pygame.Surface((r * 4, r * 4), pygame.SRCALPHA)
            pygame.draw.circle(glow, (*color, 50),
                               (r * 2, r * 2), r * 2)
            pygame.draw.circle(glow, (*color, 180),
                               (r * 2, r * 2), r)
            surface.blit(glow, (int(x - r * 2), int(y - r * 2)))


# ---------------------------------------------------------------------------
# Settings scene
# ---------------------------------------------------------------------------

class SettingsScene:
    """Settings screen with +/- adjusters, theme picker and sound toggle."""

    def __init__(self, app: App) -> None:
        self.app = app
        self.theme = app.settings.theme
        font_body = app.fonts["body"]

        cx = WINDOW_WIDTH // 2
        start_y = 170
        row_h = 56
        small_w = 36

        # Each row binds to an attribute on settings.
        self.rows = [
            ("Snake Speed", "speed", 1, 30),
            ("Win Score", "win_score", 5, 200),
            ("Bot Target Win", "bot_target_win", 1, 50),
            ("Bot Target Lose", "bot_target_lose", 1, 50),
        ]
        self.row_widgets = []
        for i, (label, attr, lo, hi) in enumerate(self.rows):
            y = start_y + i * row_h
            minus = Button(
                (cx + 70, y, small_w, 32), "-",
                lambda a=attr, lo=lo, hi=hi: self._adjust(a, -1, lo, hi),
                font=font_body, theme=self.theme,
            )
            plus = Button(
                (cx + 70 + small_w + 60, y, small_w, 32), "+",
                lambda a=attr, lo=lo, hi=hi: self._adjust(a, 1, lo, hi),
                font=font_body, theme=self.theme,
            )
            self.row_widgets.append((label, attr, minus, plus, y))

        theme_y = start_y + len(self.rows) * row_h + 10
        sound_y = theme_y + 60
        self.btn_theme = Button(
            (cx - 130, theme_y, 260, 42),
            f"Theme: {app.settings.theme_name}",
            self._cycle_theme,
            font=font_body, theme=self.theme,
        )
        self.btn_sound = Button(
            (cx - 130, sound_y, 260, 42),
            f"Sound: {'ON' if app.settings.sound_enabled else 'OFF'}",
            self._toggle_sound,
            font=font_body, theme=self.theme,
        )

        self.btn_back = Button(
            (cx - 110, WINDOW_HEIGHT - 80, 220, 48),
            "Back to Menu", app.return_to_menu,
            font=font_body, theme=self.theme,
        )

    # ------------------------------------------------------------------
    def _adjust(self, attr: str, delta: int, lo: int, hi: int) -> None:
        value = getattr(self.app.settings, attr)
        value = max(lo, min(hi, value + delta))
        setattr(self.app.settings, attr, value)
        self.app.play_sound("click")

    def _cycle_theme(self) -> None:
        self.app.settings.cycle_theme()
        self.theme = self.app.settings.theme
        self.btn_theme.set_label(f"Theme: {self.app.settings.theme_name}")
        self.app.play_sound("click")

    def _toggle_sound(self) -> None:
        self.app.settings.sound_enabled = not self.app.settings.sound_enabled
        self.btn_sound.set_label(
            f"Sound: {'ON' if self.app.settings.sound_enabled else 'OFF'}"
        )
        self.app.play_sound("click")

    # ------------------------------------------------------------------
    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.app.return_to_menu()
            return
        for (_, _, minus, plus, _) in self.row_widgets:
            minus.handle_event(event)
            plus.handle_event(event)
        self.btn_theme.handle_event(event)
        self.btn_sound.handle_event(event)
        self.btn_back.handle_event(event)

    def update(self, dt_ms: int) -> None:
        return None

    def draw(self, surface: pygame.Surface) -> None:
        # Live theme refresh when the user cycles themes.
        self.theme = self.app.settings.theme
        for (_, _, minus, plus, _) in self.row_widgets:
            minus.theme = self.theme
            plus.theme = self.theme
        self.btn_theme.theme = self.theme
        self.btn_sound.theme = self.theme
        self.btn_back.theme = self.theme

        draw_background(surface, self.theme)

        font_xl = self.app.fonts["xl"]
        font_body = self.app.fonts["body"]
        draw_text(
            surface, "SETTINGS", font_xl, self.theme["accent"],
            WINDOW_WIDTH // 2, 80, center=True,
        )

        cx = WINDOW_WIDTH // 2
        for (label, attr, minus, plus, y) in self.row_widgets:
            value = getattr(self.app.settings, attr)
            draw_text(surface, label, font_body, self.theme["text"],
                      cx - 240, y + 6)
            draw_text(
                surface, str(value), font_body, self.theme["accent"],
                minus.rect.right + 18, y + 6,
            )
            minus.draw(surface)
            plus.draw(surface)

        self.btn_theme.draw(surface)
        self.btn_sound.draw(surface)
        self.btn_back.draw(surface)


def main() -> None:
    App().run()


if __name__ == "__main__":
    main()
