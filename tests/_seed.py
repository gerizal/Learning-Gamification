"""Test fixtures written straight to the dev DB (the /api/admin/* endpoints that tests used before were removed
with the admin page, 2026-09-28). Callers track the returned ids and delete them by primary key afterwards."""
from __future__ import annotations

import os
from typing import Optional

import psycopg
from psycopg.rows import dict_row

PACK_COLS = "id, slug, name, topic, description, why_it_matters, is_active, created_at"
Q_COLS = ("id, game_mode, prompt, target_text, keywords, image_url, image_alt, difficulty, base_points, "
          "time_limit_sec, is_active, sort_order, pack_id, options, correct_option")


def _connect():
    return psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row)


def insert_pack(*, slug: str, name: str, topic: str = "ai", description: str = "", why_it_matters: str = "",
                is_active: bool = True, edit_key_hash: Optional[str] = None) -> dict:
    with _connect() as c:
        return c.execute(
            f"""INSERT INTO question_pack (slug, name, topic, description, why_it_matters, is_active, edit_key_hash)
                VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING {PACK_COLS}""",
            (slug, name, topic, description, why_it_matters, is_active, edit_key_hash)).fetchone()


def insert_question(pack_id: Optional[int], *, prompt: str, game_mode: str = "multiple_choice",
                    options: Optional[list[str]] = None, correct_option: Optional[int] = None,
                    target_text: Optional[str] = None, keywords: Optional[list[str]] = None,
                    image_url: Optional[str] = None, image_alt: Optional[str] = None, difficulty: int = 1,
                    base_points: int = 100, time_limit_sec: int = 20, is_active: bool = True,
                    sort_order: int = 0) -> dict:
    """A multiple_choice question by default. game_mode='read_aloud' etc. inserts a LEGACY speaking row, used
    only to prove such rows are never picked and are rejected with 422."""
    with _connect() as c:
        return c.execute(
            f"""INSERT INTO question (game_mode, prompt, target_text, keywords, image_url, image_alt, difficulty,
                                      base_points, time_limit_sec, is_active, sort_order, pack_id, options,
                                      correct_option)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING {Q_COLS}""",
            (game_mode, prompt, target_text, keywords or [], image_url, image_alt, difficulty, base_points,
             time_limit_sec, is_active, sort_order, pack_id, options or [], correct_option)).fetchone()
