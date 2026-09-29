"""Pure scoring functions (no I/O). See CONTRACT.md "Scoring rules" and "LIVE GAME" › Scoring.

Quiz-only MVP (owner, 2026-09-28): every question is multiple_choice. The speaking scorers (word alignment,
keywords) and the individual-practice helpers were removed together with /practice and app/stt.py.
"""
from __future__ import annotations

PASS_ACCURACY = 60
DIFFICULTY_MULTIPLIER = {1: 1.0, 2: 1.5, 3: 2.0}

MULTIPLE_CHOICE = "multiple_choice"
LIVE_GRACE_SEC = 3  # live game: answers accepted until time_limit_sec + this (server clock)


def is_passed(accuracy: float) -> bool:
    return accuracy >= PASS_ACCURACY


def stars_for(accuracy: float) -> int:
    if accuracy >= 90:
        return 3
    if accuracy >= 75:
        return 2
    if accuracy >= 60:
        return 1
    return 0


def score_multiple_choice(choice: int | None, correct_option: int | None) -> dict:
    """multiple_choice: accuracy 100 if choice == correct_option else 0.
    Returns {accuracy, passed, stars, feedback:{words, extra_words, keywords, choice, correct}}; the empty
    words / extra_words / keywords lists keep the stored feedback shape of older (speaking) answers."""
    correct = choice is not None and correct_option is not None and int(choice) == int(correct_option)
    acc = 100.0 if correct else 0.0
    return {"accuracy": acc, "passed": is_passed(acc), "stars": stars_for(acc),
            "feedback": {"words": [], "extra_words": [], "keywords": [],
                         "choice": None if choice is None else int(choice), "correct": correct}}


def next_streak(previous_streak: int | None, passed: bool) -> int:
    """Consecutive passed answers including this one (0 if failed).

    previous_streak = the stored streak before this answer (None if first).
    """
    if not passed:
        return 0
    return (previous_streak or 0) + 1


def streak_multiplier(streak: int) -> float:
    return round(1 + 0.1 * min(max(streak - 1, 0), 5), 2)


def base_for(base_points: int, difficulty: int) -> float:
    return base_points * DIFFICULTY_MULTIPLIER[int(difficulty)]


def compute_points(*, base_points: int, difficulty: int, accuracy: float, passed: bool,
                   streak: int, duration_ms: int, time_limit_sec: int) -> dict:
    """Classroom turn points. Returns {points, earned, streak_multiplier, speed_bonus}."""
    base = base_for(base_points, difficulty)
    earned = round(base * accuracy / 100)
    if not passed:
        return {"points": earned, "earned": earned, "streak_multiplier": 1.0, "speed_bonus": 0}
    mult = streak_multiplier(streak)
    fast = duration_ms <= time_limit_sec * 1000 * 0.5
    speed_bonus = round(base * 0.1) if fast else 0
    return {"points": round(earned * mult) + speed_bonus, "earned": earned,
            "streak_multiplier": mult, "speed_bonus": speed_bonus}


# --------------------------------------------------------------------------- live game / homework

def live_speed_factor(answer_ms: int, time_limit_sec: int) -> float:
    """Kahoot-style: 1.0 for an instant answer, 0.5 at (or after) the time limit. Clamped to [0.5, 1]."""
    limit_ms = max(int(time_limit_sec), 1) * 1000
    t = min(max(int(answer_ms), 0), limit_ms)
    return 1 - 0.5 * t / limit_ms


def live_points(*, base_points: int, difficulty: int, accuracy: float, passed: bool,
                answer_ms: int, time_limit_sec: int, streak: int) -> dict:
    """Live game points (CONTRACT "LIVE GAME" › Scoring). Returns {points, speed_factor, streak_multiplier}.

    points = round(base * accuracy/100 * speed_factor * streak_multiplier) if passed else 0,
    base = base_points * difficulty multiplier, streak_multiplier = 1 + 0.1 * min(streak-1, 5) (max 1.5).
    """
    if not passed:
        return {"points": 0, "speed_factor": 0.0, "streak_multiplier": 1.0}
    factor = live_speed_factor(answer_ms, time_limit_sec)
    mult = streak_multiplier(streak)
    pts = round(base_for(base_points, difficulty) * float(accuracy) / 100 * factor * mult)
    return {"points": pts, "speed_factor": round(factor, 4), "streak_multiplier": mult}
