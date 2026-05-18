# Snake Neon

A modern, neon-styled Snake game for PC built with **Python + Pygame**, with a
built-in **Bot / Auto-Play** mode and optional **gameplay recording** powered
by OpenCV.

## Features

- Landscape window with a 9:16 portrait arena on the left and a control /
  info panel on the right.
- Expressive snake character: gradient body, glowing outline, eyes that look
  forward and a mouth that opens when eating.
- Modern food with pulsing glow, plus a small particle burst when eaten.
- Three themes: **Neon Cyber**, **Soft Futuristic** and **Sunset Glow**.
- Full keyboard control (`WASD` or arrow keys) **and** clickable on-screen
  directional pad.
- Bot mode that pathfinds with BFS + flood-fill fallback. Configurable
  target wins / target losses.
- Win / lose screens with score, configurable target score and auto-restart
  while the bot still has targets to hit.
- Statistics panel: wins, losses, total games, win rate.
- One-click gameplay recording (`mp4`/`avi`) via OpenCV with a blinking
  `REC` indicator and timestamped filenames in `recordings/`.
- Settings screen for speed, win score, bot targets, theme and sound on/off.
- Synthesised sound effects for click / eat / win / lose.

## Project layout

```
main.py        # Application bootstrap, main menu and settings scenes
game.py        # Gameplay scene: arena + right side control panel
snake.py       # Snake entity with expressive head and gradient body
food.py        # Food + particle burst effect
bot.py         # BFS / flood-fill auto-play algorithm
recorder.py    # OpenCV-based screen recorder (graceful fallback)
ui.py          # Reusable UI primitives (button, panel, background)
settings.py    # Theme palettes, constants, runtime Settings container
requirements.txt
setup.bat      # Windows one-time setup helper
run.bat        # Windows launcher
```

## Requirements

- Python 3.9 or newer.
- The packages in `requirements.txt`:

```
pygame>=2.5
opencv-python>=4.8
numpy>=1.24
```

> If `opencv-python` cannot be installed in your environment the game will
> still run; the **Start Recording** button will show a friendly error
> instead of crashing.

## Running

### Linux / macOS

```bash
pip install -r requirements.txt
python main.py
```

### Windows

```
setup.bat
run.bat
```

`setup.bat` creates a local `venv\` virtual environment and installs the
dependencies. `run.bat` activates it and launches `main.py`.

## Controls

| Action       | Keyboard               | Mouse                       |
| ------------ | ---------------------- | --------------------------- |
| Move Up      | `W` or `Up` arrow      | Click the up button         |
| Move Down    | `S` or `Down` arrow    | Click the down button       |
| Move Left    | `A` or `Left` arrow    | Click the left button       |
| Move Right   | `D` or `Right` arrow   | Click the right button      |
| Restart      | `R`                    | "Restart" button            |
| Back to menu | `Esc`                  | "Main Menu" button          |
| Toggle Bot   | `B`                    | "Bot: ON / OFF" button      |
| Record       | -                      | "Start / Stop Recording"    |

## Bot mode

Press **Bot Mode** from the main menu, or toggle the **Bot** button on the
right panel during a manual game. The bot uses BFS to find the shortest safe
path to the food; if no path exists it falls back to a flood-fill heuristic
that maximises free space.

You can set:

- **Target Wins** - the bot stops after this many wins.
- **Target Losses** - the bot stops after this many losses.

After each win or loss the game automatically restarts while the bot still
has either target available.

## Recording

Click **Start Recording** to begin capturing the window. A blinking red `REC`
indicator appears in the top-left of the arena. Click **Stop Recording** to
save the file - it is written to `recordings/snake_record_YYYY-MM-DD_HH-MM-SS.mp4`
(or `.avi` if `mp4v` is unavailable on your system).

If OpenCV is missing the button shows a clear error in the panel instead of
crashing the game.
