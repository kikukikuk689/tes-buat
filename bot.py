"""Simple but solid auto-play algorithm for the Snake.

The bot uses BFS to find the shortest safe path to the food. When no path
exists, it falls back to a flood-fill heuristic that picks the direction with
the most reachable empty space, biased toward food when possible.
"""

from __future__ import annotations

from collections import deque

from settings import COLS, ROWS


# Candidate movement directions. The order does not matter for correctness.
DIRS = [(0, -1), (0, 1), (-1, 0), (1, 0)]


def _in_bounds(cell: tuple) -> bool:
    return 0 <= cell[0] < COLS and 0 <= cell[1] < ROWS


def _bfs_first_step(start: tuple, goal: tuple, blocked: set) -> tuple | None:
    """Return the first direction of the shortest path from start to goal.

    `blocked` is the set of cells we cannot step into (snake body cells).
    The goal cell itself is allowed even if it is in `blocked` (it isn't here
    but we handle that case defensively).
    """
    if start == goal:
        return None

    # Each queue entry remembers the *first* direction taken from `start` so
    # we can return it directly once we reach the goal.
    visited = {start}
    queue = deque([(start, None)])
    while queue:
        cell, first_dir = queue.popleft()
        for d in DIRS:
            nx, ny = cell[0] + d[0], cell[1] + d[1]
            nxt = (nx, ny)
            if not _in_bounds(nxt) or nxt in visited:
                continue
            if nxt in blocked and nxt != goal:
                continue
            visited.add(nxt)
            step_dir = first_dir if first_dir is not None else d
            if nxt == goal:
                return step_dir
            queue.append((nxt, step_dir))
    return None


def _flood_fill_size(start: tuple, blocked: set) -> int:
    """Count how many cells are reachable from `start` avoiding `blocked`."""
    if not _in_bounds(start) or start in blocked:
        return 0
    visited = {start}
    queue = deque([start])
    while queue:
        c = queue.popleft()
        for d in DIRS:
            nxt = (c[0] + d[0], c[1] + d[1])
            if not _in_bounds(nxt) or nxt in visited or nxt in blocked:
                continue
            visited.add(nxt)
            queue.append(nxt)
    return len(visited)


def pick_direction(snake_body: list, food_pos: tuple,
                   current_direction: tuple) -> tuple:
    """Decide which direction the bot should turn next.

    Steps:
      1. Try to find a BFS path to the food. If the resulting next cell still
         leaves enough free space, take that direction.
      2. Otherwise pick the safe direction whose flood-fill area is largest
         (and as a tiebreaker, the one closest to the food).
      3. As a last resort keep going in the current direction.
    """
    head = snake_body[0]
    # The snake's tail will leave its cell on the next move, so it is not a
    # real obstacle. Excluding it from `blocked` lets the bot squeeze through
    # tight spots.
    blocked = set(snake_body[:-1])
    reverse = (-current_direction[0], -current_direction[1])

    # Cells the snake will occupy *after* the next move (head moves forward,
    # tail leaves). We don't add the new head cell here: flood_fill needs to
    # start on a non-blocked cell, and the new head is by definition empty.
    def _future_blocked() -> set:
        return set(snake_body[:-1])

    # 1) Shortest BFS path toward the food.
    bfs_dir = _bfs_first_step(head, food_pos, blocked)
    if bfs_dir is not None and bfs_dir != reverse:
        nx, ny = head[0] + bfs_dir[0], head[1] + bfs_dir[1]
        space = _flood_fill_size((nx, ny), _future_blocked())
        # Make sure following the BFS path still leaves enough room to live.
        if space >= max(3, len(snake_body) // 2):
            return bfs_dir

    # 2) Fallback heuristic: maximise reachable space and prefer food proximity.
    best_dir = None
    best_score = -10 ** 9
    for d in DIRS:
        if d == reverse:
            continue
        nx, ny = head[0] + d[0], head[1] + d[1]
        if not _in_bounds((nx, ny)) or (nx, ny) in blocked:
            continue
        space = _flood_fill_size((nx, ny), _future_blocked())
        if space <= 0:
            continue
        dist = abs(nx - food_pos[0]) + abs(ny - food_pos[1])
        score = space * 100 - dist
        if score > best_score:
            best_score = score
            best_dir = d

    if best_dir is not None:
        return best_dir

    # 3) Last resort: any legal move (even a tight squeeze) before suiciding.
    for d in DIRS:
        if d == reverse:
            continue
        nx, ny = head[0] + d[0], head[1] + d[1]
        if _in_bounds((nx, ny)) and (nx, ny) not in blocked:
            return d

    return current_direction
