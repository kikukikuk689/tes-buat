"""Gameplay scene: arena on the left + control / info panel on the right."""

from __future__ import annotations

import pygame

from bot import pick_direction
from food import Food, spawn_burst
from recorder import Recorder
from settings import (
    ARENA_HEIGHT,
    ARENA_WIDTH,
    ARENA_X,
    ARENA_Y,
    FPS,
    PANEL_HEIGHT,
    PANEL_WIDTH,
    PANEL_X,
    PANEL_Y,
    RECORDINGS_DIR,
)
from snake import DIR_DOWN, DIR_LEFT, DIR_RIGHT, DIR_UP, Snake
from ui import (
    Button,
    draw_arena_background,
    draw_background,
    draw_panel_background,
    draw_text,
)


STATE_PLAYING = "playing"
STATE_WIN = "win"
STATE_LOSE = "lose"

# Time to show the win/lose screen before auto-restarting in bot mode.
BOT_RESTART_DELAY_MS = 1200


class Game:
    """The main playable scene of the application."""

    def __init__(self, app, bot_mode: bool = False) -> None:
        self.app = app
        self.settings = app.settings
        self.theme = self.settings.theme

        # Game entities.
        self.snake = Snake(self.theme)
        self.food = Food(self.theme)
        self.particles: list = []

        # Game state.
        self.score = 0
        self.state = STATE_PLAYING
        self.move_accumulator = 0.0
        self.move_interval = 1.0 / max(1, self.settings.speed)
        self.result_timer = 0
        self.message = ""

        # Bot configuration.
        self.bot_mode = bot_mode
        self.bot_stopped = False
        # Run-local copies of bot targets (so the user can tweak them on the
        # fly without touching the global settings until exiting the scene).
        self.bot_target_win = self.settings.bot_target_win
        self.bot_target_lose = self.settings.bot_target_lose

        # Stats.
        self.wins = 0
        self.losses = 0
        self.total = 0

        # Recorder.
        self.recorder = Recorder(RECORDINGS_DIR, fps=FPS)

        # Spawn initial food now that the snake exists.
        self.food.theme = self.theme
        self.food.respawn(set(self.snake.body), pygame.time.get_ticks())

        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        font_body = self.app.fonts["body"]
        theme = self.theme

        # ---- D-pad cluster ----
        pad_size = 52
        pad_cx = PANEL_X + PANEL_WIDTH // 2
        pad_cy = PANEL_Y + 150
        gap = 4
        self.btn_up = Button(
            (pad_cx - pad_size // 2, pad_cy - pad_size - gap, pad_size, pad_size),
            "", lambda: self._press_dir(DIR_UP),
            font=font_body, theme=theme, icon="up",
        )
        self.btn_down = Button(
            (pad_cx - pad_size // 2, pad_cy + gap, pad_size, pad_size),
            "", lambda: self._press_dir(DIR_DOWN),
            font=font_body, theme=theme, icon="down",
        )
        self.btn_left = Button(
            (pad_cx - pad_size * 3 // 2 - gap, pad_cy - pad_size // 2,
             pad_size, pad_size),
            "", lambda: self._press_dir(DIR_LEFT),
            font=font_body, theme=theme, icon="left",
        )
        self.btn_right = Button(
            (pad_cx + pad_size // 2 + gap, pad_cy - pad_size // 2,
             pad_size, pad_size),
            "", lambda: self._press_dir(DIR_RIGHT),
            font=font_body, theme=theme, icon="right",
        )

        # ---- Bot toggle + Record buttons ----
        toggle_w = PANEL_WIDTH - 40
        bot_y = PANEL_Y + 220
        rec_y = bot_y + 50
        self.btn_bot = Button(
            (PANEL_X + 20, bot_y, toggle_w, 42),
            "Bot: ON" if self.bot_mode else "Bot: OFF",
            self._toggle_bot,
            font=font_body, theme=theme, toggled=self.bot_mode,
        )
        self.btn_rec = Button(
            (PANEL_X + 20, rec_y, toggle_w, 42),
            "Start Recording", self._toggle_recording,
            font=font_body, theme=theme, icon="rec",
        )

        # ---- Bot target adjusters ----
        small_w = 32
        col_right = PANEL_X + PANEL_WIDTH - 20
        adj_y_w = PANEL_Y + 360
        adj_y_l = adj_y_w + 40
        self.btn_win_minus = Button(
            (col_right - small_w * 2 - 50, adj_y_w, small_w, 30),
            "-", lambda: self._adjust_target("win", -1),
            font=font_body, theme=theme,
        )
        self.btn_win_plus = Button(
            (col_right - small_w, adj_y_w, small_w, 30),
            "+", lambda: self._adjust_target("win", 1),
            font=font_body, theme=theme,
        )
        self.btn_lose_minus = Button(
            (col_right - small_w * 2 - 50, adj_y_l, small_w, 30),
            "-", lambda: self._adjust_target("lose", -1),
            font=font_body, theme=theme,
        )
        self.btn_lose_plus = Button(
            (col_right - small_w, adj_y_l, small_w, 30),
            "+", lambda: self._adjust_target("lose", 1),
            font=font_body, theme=theme,
        )

        # ---- Bottom row: Restart + Menu side by side ----
        bottom_h = 42
        bottom_y = PANEL_Y + PANEL_HEIGHT - bottom_h - 12
        half_w = (PANEL_WIDTH - 60) // 2
        self.btn_restart = Button(
            (PANEL_X + 20, bottom_y, half_w, bottom_h),
            "Restart (R)", self.restart,
            font=font_body, theme=theme,
        )
        self.btn_menu = Button(
            (PANEL_X + 30 + half_w, bottom_y, half_w, bottom_h),
            "Main Menu (Esc)", self.app.return_to_menu,
            font=font_body, theme=theme,
        )

        self._adj_y_w = adj_y_w
        self._adj_y_l = adj_y_l

        self.buttons = [
            self.btn_up, self.btn_down, self.btn_left, self.btn_right,
            self.btn_bot, self.btn_rec,
            self.btn_win_minus, self.btn_win_plus,
            self.btn_lose_minus, self.btn_lose_plus,
            self.btn_restart, self.btn_menu,
        ]

    # ------------------------------------------------------------------
    # Button actions
    # ------------------------------------------------------------------
    def _press_dir(self, d: tuple) -> None:
        self.snake.set_direction(d)
        self.app.play_sound("click")

    def _toggle_bot(self) -> None:
        self.bot_mode = not self.bot_mode
        self.btn_bot.set_toggled(self.bot_mode)
        self.btn_bot.set_label("Bot: ON" if self.bot_mode else "Bot: OFF")
        if self.bot_mode:
            # Reset the bot-stopped flag and stats counters? Keep stats
            # accumulating but allow new runs.
            self.bot_stopped = False
        self.app.play_sound("click")

    def _toggle_recording(self) -> None:
        if not self.recorder.is_available():
            self.message = self.recorder.availability_message()
            return
        if self.recorder.is_recording():
            path = self.recorder.stop()
            self.btn_rec.set_label("Start Recording")
            self.btn_rec.set_toggled(False)
            self.message = f"Saved: {path}"
        else:
            ok = self.recorder.start(self.app.screen)
            if ok:
                self.btn_rec.set_label("Stop Recording")
                self.btn_rec.set_toggled(True)
                self.message = "Recording started"
            else:
                self.message = self.recorder.error or "Recording failed"
        self.app.play_sound("click")

    def _adjust_target(self, which: str, delta: int) -> None:
        if which == "win":
            self.bot_target_win = max(1, self.bot_target_win + delta)
            self.settings.bot_target_win = self.bot_target_win
        else:
            self.bot_target_lose = max(1, self.bot_target_lose + delta)
            self.settings.bot_target_lose = self.bot_target_lose
        self.app.play_sound("click")

    def restart(self) -> None:
        self.snake.reset()
        self.food.respawn(set(self.snake.body), pygame.time.get_ticks())
        self.particles.clear()
        self.score = 0
        self.state = STATE_PLAYING
        self.move_accumulator = 0.0
        self.result_timer = 0
        self.message = ""
        self.app.play_sound("click")

    # ------------------------------------------------------------------
    # Event handling
    # ------------------------------------------------------------------
    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_UP, pygame.K_w):
                self.snake.set_direction(DIR_UP)
            elif event.key in (pygame.K_DOWN, pygame.K_s):
                self.snake.set_direction(DIR_DOWN)
            elif event.key in (pygame.K_LEFT, pygame.K_a):
                self.snake.set_direction(DIR_LEFT)
            elif event.key in (pygame.K_RIGHT, pygame.K_d):
                self.snake.set_direction(DIR_RIGHT)
            elif event.key == pygame.K_r:
                self.restart()
            elif event.key == pygame.K_b:
                self._toggle_bot()
            elif event.key == pygame.K_ESCAPE:
                if self.recorder.is_recording():
                    self.recorder.stop()
                self.app.return_to_menu()
                return

        for btn in self.buttons:
            btn.handle_event(event)

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------
    def update(self, dt_ms: int) -> None:
        time_ms = pygame.time.get_ticks()

        # Refresh theme cached on entities in case the user changed it from
        # the menu (returning here would otherwise still use the old palette).
        self.theme = self.settings.theme
        self.snake.theme = self.theme
        self.food.theme = self.theme
        for btn in self.buttons:
            btn.theme = self.theme

        # Update particles independently of game state for nice visuals.
        self.particles = [p for p in self.particles if p.alive()]
        for p in self.particles:
            p.update(dt_ms)

        # Stop the bot once it has reached either target.
        if self.bot_mode and not self.bot_stopped:
            if (self.wins >= self.bot_target_win
                    or self.losses >= self.bot_target_lose):
                self.bot_stopped = True

        if self.state == STATE_PLAYING:
            self.move_interval = 1.0 / max(1, self.settings.speed)
            self.move_accumulator += dt_ms / 1000.0

            # Step the snake potentially multiple times per frame if speed is
            # very high. We break early on win/lose.
            while self.move_accumulator >= self.move_interval:
                self.move_accumulator -= self.move_interval

                if self.bot_mode and not self.bot_stopped:
                    d = pick_direction(
                        self.snake.body, self.food.pos, self.snake.direction,
                    )
                    if d:
                        self.snake.set_direction(d)

                moved = self.snake.step()
                if not moved:
                    self._on_lose()
                    break
                if self.snake.head() == self.food.pos:
                    self._on_eat(time_ms)
                    if self.score >= self.settings.win_score:
                        self._on_win()
                        break

        elif self.state in (STATE_WIN, STATE_LOSE):
            # Auto-restart while the bot is still trying to hit its targets.
            if self.bot_mode and not self.bot_stopped:
                self.result_timer += dt_ms
                if self.result_timer >= BOT_RESTART_DELAY_MS:
                    self.restart()

    def _on_eat(self, time_ms: int) -> None:
        self.snake.grow(1)
        self.score += 1
        rect = self.food.rect()
        spawn_burst(self.particles, rect.centerx, rect.centery,
                    self.theme["food"])
        self.food.respawn(set(self.snake.body), time_ms)
        self.app.play_sound("eat")

    def _on_win(self) -> None:
        self.state = STATE_WIN
        self.wins += 1
        self.total += 1
        self.result_timer = 0
        self.app.play_sound("win")

    def _on_lose(self) -> None:
        self.state = STATE_LOSE
        self.losses += 1
        self.total += 1
        self.result_timer = 0
        self.app.play_sound("lose")

    # ------------------------------------------------------------------
    # Draw
    # ------------------------------------------------------------------
    def draw(self, surface: pygame.Surface) -> None:
        draw_background(surface, self.theme)
        draw_arena_background(surface, self.theme)
        draw_panel_background(surface, self.theme)

        time_ms = pygame.time.get_ticks()

        # Arena entities.
        self.food.draw(surface, time_ms)
        self.snake.draw(surface, time_ms)
        for p in self.particles:
            p.draw(surface)

        # Win/lose overlay.
        if self.state == STATE_WIN:
            self._draw_result(surface, "YOU WIN!", self.theme["win"])
        elif self.state == STATE_LOSE:
            self._draw_result(surface, "GAME OVER", self.theme["lose"])

        # REC indicator over the arena.
        if self.recorder.is_recording():
            self._draw_rec_indicator(surface, time_ms)

        # Control / info panel.
        self._draw_panel(surface)

        # Send the *fully drawn* frame to the recorder (if recording).
        if self.recorder.is_recording():
            self.recorder.write_frame(surface)

    def _draw_result(self, surface: pygame.Surface,
                     text: str, color: tuple) -> None:
        overlay = pygame.Surface((ARENA_WIDTH, ARENA_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        surface.blit(overlay, (ARENA_X, ARENA_Y))
        font_xl = self.app.fonts["xl"]
        font_md = self.app.fonts["body"]
        draw_text(
            surface, text, font_xl, color,
            ARENA_X + ARENA_WIDTH // 2,
            ARENA_Y + ARENA_HEIGHT // 2 - 30,
            center=True,
        )
        draw_text(
            surface, f"Score: {self.score}", font_md, self.theme["text"],
            ARENA_X + ARENA_WIDTH // 2,
            ARENA_Y + ARENA_HEIGHT // 2 + 10,
            center=True,
        )
        hint = "Press R to play again" if not self.bot_mode else "Bot restarting..."
        draw_text(
            surface, hint, font_md, self.theme["text_dim"],
            ARENA_X + ARENA_WIDTH // 2,
            ARENA_Y + ARENA_HEIGHT // 2 + 50,
            center=True,
        )

    def _draw_rec_indicator(self, surface: pygame.Surface,
                            time_ms: int) -> None:
        blink_on = (time_ms // 500) % 2 == 0
        x, y = ARENA_X + 18, ARENA_Y + 18
        if blink_on:
            pygame.draw.circle(surface, self.theme["rec"], (x, y), 8)
        font = self.app.fonts["small"]
        draw_text(surface, "REC", font, self.theme["rec"], x + 14, y - 9)

    def _draw_panel(self, surface: pygame.Surface) -> None:
        font_title = self.app.fonts["title"]
        font_body = self.app.fonts["body"]
        font_small = self.app.fonts["small"]
        theme = self.theme

        # Title row.
        draw_text(surface, "SNAKE NEON", font_title, theme["accent"],
                  PANEL_X + 20, PANEL_Y + 14)
        draw_text(surface, f"Theme: {self.settings.theme_name}", font_small,
                  theme["text_dim"], PANEL_X + 20, PANEL_Y + 50)

        score_text = f"Score {self.score}/{self.settings.win_score}"
        draw_text(
            surface, score_text, font_body, theme["text"],
            PANEL_X + PANEL_WIDTH - 20 - font_body.size(score_text)[0],
            PANEL_Y + 24,
        )

        # All buttons handle their own drawing.
        for btn in [
            self.btn_up, self.btn_down, self.btn_left, self.btn_right,
            self.btn_bot, self.btn_rec,
            self.btn_restart, self.btn_menu,
        ]:
            btn.draw(surface)

        # Bot settings header + status.
        bot_header_y = self.btn_rec.rect.bottom + 16
        draw_text(surface, "BOT SETTINGS", font_body, theme["accent2"],
                  PANEL_X + 20, bot_header_y)

        status_label = (
            "RUNNING" if (self.bot_mode and not self.bot_stopped)
            else ("STOPPED" if self.bot_mode else "OFF")
        )
        draw_text(surface, f"Status: {status_label}", font_small,
                  theme["text"], PANEL_X + 20, bot_header_y + 24)

        # Target wins / losses adjusters.
        draw_text(surface, "Target Wins", font_body, theme["text"],
                  PANEL_X + 20, self._adj_y_w + 4)
        draw_text(
            surface, str(self.bot_target_win), font_body, theme["accent"],
            self.btn_win_minus.rect.right + 18, self._adj_y_w + 4,
        )
        self.btn_win_minus.draw(surface)
        self.btn_win_plus.draw(surface)

        draw_text(surface, "Target Losses", font_body, theme["text"],
                  PANEL_X + 20, self._adj_y_l + 4)
        draw_text(
            surface, str(self.bot_target_lose), font_body, theme["accent2"],
            self.btn_lose_minus.rect.right + 18, self._adj_y_l + 4,
        )
        self.btn_lose_minus.draw(surface)
        self.btn_lose_plus.draw(surface)

        # Statistics block.
        stats_y = self._adj_y_l + 50
        draw_text(surface, "STATISTICS", font_body, theme["accent"],
                  PANEL_X + 20, stats_y)
        win_rate = (self.wins / self.total * 100.0) if self.total else 0.0
        stats_lines = [
            f"Wins    : {self.wins}",
            f"Losses  : {self.losses}",
            f"Total   : {self.total}",
            f"Winrate : {win_rate:.1f}%",
        ]
        for i, line in enumerate(stats_lines):
            draw_text(surface, line, font_small, theme["text"],
                      PANEL_X + 20, stats_y + 26 + i * 18)

        # Status message (e.g. "Recording started", saved path, errors).
        if self.message:
            message = self.message
            # Make sure long absolute paths don't overflow the panel.
            max_chars = 56
            if len(message) > max_chars:
                message = "..." + message[-(max_chars - 3):]
            draw_text(
                surface, message, font_small, theme["text_dim"],
                PANEL_X + 20, self.btn_restart.rect.top - 22,
            )
