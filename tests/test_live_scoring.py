"""Pure unit tests for the live-game / quiz scoring helpers in app/scoring.py (no DB)."""
import pytest

from app import scoring


def test_multiple_choice_correct_and_wrong():
    r = scoring.score_multiple_choice(2, 2)
    assert r["accuracy"] == 100.0 and r["passed"] is True and r["stars"] == 3
    assert r["feedback"] == {"words": [], "extra_words": [], "keywords": [], "choice": 2, "correct": True}
    w = scoring.score_multiple_choice(1, 2)
    assert w["accuracy"] == 0.0 and w["passed"] is False and w["stars"] == 0 and w["feedback"]["correct"] is False
    # no choice / no key -> wrong, never an exception
    assert scoring.score_multiple_choice(None, 0)["passed"] is False
    assert scoring.score_multiple_choice(0, None)["passed"] is False


@pytest.mark.parametrize("answer_ms,limit,factor", [
    (0, 20, 1.0), (5000, 20, 0.875), (10000, 20, 0.75), (20000, 20, 0.5),
    (23000, 20, 0.5),   # grace period: clamped at the minimum
    (-50, 20, 1.0),     # clock skew: clamped at the maximum
])
def test_speed_factor(answer_ms, limit, factor):
    assert scoring.live_speed_factor(answer_ms, limit) == pytest.approx(factor)


def test_live_points_formula():
    # points = round(base * acc/100 * (1 - 0.5 * t/limit)) ; base = base_points * difficulty multiplier
    p = scoring.live_points(base_points=100, difficulty=1, accuracy=100, passed=True,
                            answer_ms=10000, time_limit_sec=20, streak=1)
    assert p == {"points": 75, "speed_factor": 0.75, "streak_multiplier": 1.0}
    # difficulty 2 = x1.5, accuracy 80, instant
    p = scoring.live_points(base_points=100, difficulty=2, accuracy=80, passed=True,
                            answer_ms=0, time_limit_sec=20, streak=1)
    assert p["points"] == 120
    # difficulty 3 = x2.0, slowest possible -> half
    p = scoring.live_points(base_points=200, difficulty=3, accuracy=100, passed=True,
                            answer_ms=30000, time_limit_sec=30, streak=1)
    assert p["points"] == 200
    # failed -> 0 whatever the speed
    p = scoring.live_points(base_points=100, difficulty=1, accuracy=50, passed=False,
                            answer_ms=0, time_limit_sec=20, streak=0)
    assert p == {"points": 0, "speed_factor": 0.0, "streak_multiplier": 1.0}


@pytest.mark.parametrize("streak,mult,points", [(1, 1.0, 100), (2, 1.1, 110), (4, 1.3, 130),
                                                 (6, 1.5, 150), (20, 1.5, 150)])
def test_live_points_streak_bonus_capped(streak, mult, points):
    p = scoring.live_points(base_points=100, difficulty=1, accuracy=100, passed=True,
                            answer_ms=0, time_limit_sec=20, streak=streak)
    assert p["streak_multiplier"] == mult and p["points"] == points


def test_existing_compute_points_unchanged():
    # guard: the classroom formula is untouched by the live additions
    p = scoring.compute_points(base_points=100, difficulty=1, accuracy=100, passed=True, streak=2,
                               duration_ms=1000, time_limit_sec=20)
    assert p == {"points": 120, "earned": 100, "streak_multiplier": 1.1, "speed_bonus": 10}
