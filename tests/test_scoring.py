"""Unit tests for app/scoring.py — one block per CONTRACT scoring rule (quiz-only MVP)."""
import pytest

from app import scoring as s


# ---------------------------------------------------------------- pass / stars
@pytest.mark.parametrize("acc,stars,passed", [
    (100, 3, True), (90, 3, True), (89.99, 2, True), (75, 2, True), (74.99, 1, True),
    (60, 1, True), (59.99, 0, False), (0, 0, False),
])
def test_stars_and_pass(acc, stars, passed):
    assert s.stars_for(acc) == stars
    assert s.is_passed(acc) is passed


# ---------------------------------------------------------------- streak
def test_next_streak():
    assert s.next_streak(None, True) == 1
    assert s.next_streak(0, True) == 1
    assert s.next_streak(3, True) == 4
    assert s.next_streak(3, False) == 0
    assert s.next_streak(None, False) == 0


@pytest.mark.parametrize("streak,mult", [
    (0, 1.0), (1, 1.0), (2, 1.1), (3, 1.2), (4, 1.3), (5, 1.4), (6, 1.5), (7, 1.5), (100, 1.5),
])
def test_streak_multiplier_cap(streak, mult):
    assert s.streak_multiplier(streak) == pytest.approx(mult)


# ---------------------------------------------------------------- points
def pts(**kw):
    args = dict(base_points=100, difficulty=1, accuracy=100.0, passed=True, streak=1,
                duration_ms=15000, time_limit_sec=20)
    args.update(kw)
    return s.compute_points(**args)


@pytest.mark.parametrize("difficulty,base", [(1, 100), (2, 150), (3, 200)])
def test_difficulty_multiplier(difficulty, base):
    assert s.base_for(100, difficulty) == base
    assert pts(difficulty=difficulty)["points"] == base


def test_earned_scales_with_accuracy():
    assert pts(accuracy=80.0)["earned"] == 80
    assert pts(accuracy=66.67, base_points=100)["earned"] == 67


def test_speed_bonus_boundary():
    # half of 20s = 10000ms -> bonus round(100*0.1)=10
    assert pts(duration_ms=10000)["speed_bonus"] == 10
    assert pts(duration_ms=10000)["points"] == 110
    assert pts(duration_ms=10001)["speed_bonus"] == 0
    assert pts(duration_ms=0, difficulty=3)["speed_bonus"] == 20


def test_streak_multiplier_applied_to_earned_then_bonus_added():
    r = pts(accuracy=80.0, streak=3, duration_ms=1000)
    assert r["earned"] == 80 and r["streak_multiplier"] == pytest.approx(1.2)
    assert r["speed_bonus"] == 10
    assert r["points"] == round(80 * 1.2) + 10


def test_failed_attempt_gets_only_earned():
    r = pts(accuracy=50.0, passed=False, streak=0, duration_ms=100)
    assert r == {"points": 50, "earned": 50, "streak_multiplier": 1.0, "speed_bonus": 0}


def test_max_streak_points():
    r = pts(streak=9, duration_ms=20000)
    assert r["points"] == 150
