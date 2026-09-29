-- Speaking Game Prototype — demo seed data (idempotent)

INSERT INTO users (name, email, avatar) VALUES
  ('Budi Santoso',   'budi@example.com',  '🦁'),
  ('Siti Rahayu',    'siti@example.com',  '🌸'),
  ('Agus Pratama',   'agus@example.com',  '🚀'),
  ('Dewi Lestari',   'dewi@example.com',  '🦋'),
  ('Rizky Hidayat',  'rizky@example.com', '⚽')
ON CONFLICT (email) DO NOTHING;

-- Questions: inserted only if an identical (game_mode, prompt) row does not already exist.
INSERT INTO question (game_mode, prompt, target_text, keywords, image_url, difficulty, base_points, time_limit_sec, sort_order)
SELECT v.game_mode, v.prompt, v.target_text, v.keywords, NULL, v.difficulty, v.base_points, v.time_limit_sec, v.sort_order
FROM (VALUES
  -- read_aloud (Baca Nyaring)
  ('read_aloud', 'Read this sentence aloud.', 'I like to eat rice',                 '{}'::text[], 1, 100, 15, 1),
  ('read_aloud', 'Read this sentence aloud.', 'My name is Budi',                    '{}'::text[], 1, 100, 15, 2),
  ('read_aloud', 'Read this sentence aloud.', 'The cat is on the table',            '{}'::text[], 1, 100, 15, 3),
  ('read_aloud', 'Read this sentence aloud.', 'I go to school every day',           '{}'::text[], 1, 100, 15, 4),
  ('read_aloud', 'Read this sentence aloud.', 'She has a red bag',                  '{}'::text[], 1, 100, 15, 5),
  ('read_aloud', 'Read this sentence aloud.', 'We play football in the afternoon',  '{}'::text[], 2, 100, 20, 6),
  ('read_aloud', 'Read this sentence aloud.', 'My mother cooks fried rice for dinner', '{}'::text[], 2, 100, 20, 7),
  -- repeat_after_me (Tirukan Aku)
  ('repeat_after_me', 'Listen and repeat.', 'Good morning',                 '{}'::text[], 1, 100, 10, 1),
  ('repeat_after_me', 'Listen and repeat.', 'Thank you very much',          '{}'::text[], 1, 100, 10, 2),
  ('repeat_after_me', 'Listen and repeat.', 'How are you today',            '{}'::text[], 1, 100, 10, 3),
  ('repeat_after_me', 'Listen and repeat.', 'I am fine thank you',          '{}'::text[], 1, 100, 10, 4),
  ('repeat_after_me', 'Listen and repeat.', 'Nice to meet you',             '{}'::text[], 1, 100, 10, 5),
  ('repeat_after_me', 'Listen and repeat.', 'Where is the bathroom',        '{}'::text[], 2, 100, 15, 6),
  ('repeat_after_me', 'Listen and repeat.', 'Can you help me please',       '{}'::text[], 2, 100, 15, 7),
  -- picture_talk (Ceritakan Gambar) — big emoji in the prompt, image_url NULL
  ('picture_talk', '🐱🛋️ What do you see?',        NULL, ARRAY['cat','sofa'],           1, 100, 20, 1),
  ('picture_talk', '🐶⚽ What do you see?',         NULL, ARRAY['dog','ball'],           1, 100, 20, 2),
  ('picture_talk', '🍎🍌 What fruit do you see?',   NULL, ARRAY['apple','banana'],       1, 100, 20, 3),
  ('picture_talk', '☀️🏖️ Describe the picture.',    NULL, ARRAY['sun','beach'],          1, 100, 20, 4),
  ('picture_talk', '👦📚 What is the boy doing?',   NULL, ARRAY['boy','book','read'],    2, 100, 25, 5),
  ('picture_talk', '🚗🌧️ Describe the picture.',    NULL, ARRAY['car','rain'],           2, 100, 25, 6),
  ('picture_talk', '👩‍🍳🍳 What is she doing?',      NULL, ARRAY['cook','egg'],           2, 100, 25, 7),
  -- quick_answer (Jawab Cepat) — keywords = accepted answers
  ('quick_answer', 'What color is the sky?',          NULL, ARRAY['blue'],                 1, 100, 10, 1),
  ('quick_answer', 'How many legs does a cat have?',  NULL, ARRAY['four','4'],             1, 100, 10, 2),
  ('quick_answer', 'What animal says "moo"?',         NULL, ARRAY['cow'],                  1, 100, 10, 3),
  ('quick_answer', 'What color is a banana?',         NULL, ARRAY['yellow'],               1, 100, 10, 4),
  ('quick_answer', 'What do you drink when you are thirsty?', NULL, ARRAY['water','juice','milk','tea'], 1, 100, 10, 5),
  ('quick_answer', 'What day comes after Monday?',    NULL, ARRAY['tuesday'],              1, 100, 10, 6),
  ('quick_answer', 'What is two plus three?',         NULL, ARRAY['five','5'],             2, 100, 10, 7)
) AS v(game_mode, prompt, target_text, keywords, difficulty, base_points, time_limit_sec, sort_order)
WHERE NOT EXISTS (
  SELECT 1 FROM question q
  WHERE q.game_mode = v.game_mode AND q.prompt = v.prompt
    AND q.target_text IS NOT DISTINCT FROM v.target_text
);
