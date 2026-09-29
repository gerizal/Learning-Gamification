-- Speaking Game Prototype — classroom question packs (idempotent, non-destructive).
-- Requires db/003_classroom.sql. Generated from a content source; see docs/CONTENT-GUIDE.md.
-- * Packs: ON CONFLICT (slug) DO NOTHING (edits made later in the admin page are never overwritten).
-- * Questions: inserted for a pack ONLY if that pack has no questions yet.
-- * Backfill: the 002 demo questions with pack_id IS NULL are attached to 'everyday-english'.
--   Runs AFTER the question insert, so on a first run everyday-english still gets its own questions.

BEGIN;

INSERT INTO question_pack (slug, name, topic, description, why_it_matters) VALUES
  ('ai-basics', 'AI Basics / Asas AI', 'ai',
   'What AI is, where we meet it every day (maps, translation, recommendations, voice assistants), that AI can make mistakes, and that people make the final decision. / Apa itu AI, di mana kita menggunakannya setiap hari, AI boleh tersilap, dan manusia yang membuat keputusan akhir.',
   'AI is already part of your students'' daily lives: map apps, translation tools, video recommendations and voice assistants all use it. This pack lets students practise simple English while they learn what AI is, where they meet it, and that it can be wrong. It supports the digital literacy and critical thinking that schools already want to build, and it does not take time away from English: every question is still speaking practice. Students also learn an important habit early: people check AI''s answers and make the final decision.

— BM —
AI sudah menjadi sebahagian daripada kehidupan harian murid anda: aplikasi peta, alat terjemahan, cadangan video dan pembantu suara semuanya menggunakan AI. Pek ini membolehkan murid berlatih bahasa Inggeris yang mudah sambil belajar apa itu AI, di mana mereka menemuinya, dan bahawa AI boleh tersilap. Ia menyokong literasi digital dan pemikiran kritis yang memang ingin dibina oleh sekolah, dan ia tidak mengambil masa daripada pelajaran bahasa Inggeris: setiap soalan tetap latihan bertutur. Murid juga belajar satu tabiat penting sejak awal: manusia menyemak jawapan AI dan membuat keputusan akhir.'),
  ('ai-safe-smart', 'Using AI Safely & Smartly', 'ai',
   'Privacy, checking facts, never sharing passwords, kindness online, and how AI is changing jobs. / Privasi, menyemak fakta, tidak berkongsi kata laluan, berbudi bahasa dalam talian, dan AI serta pekerjaan masa depan.',
   'Many students use phones and apps before anyone teaches them how to stay safe online. This pack practises everyday English while building safe habits: keeping passwords and personal details private, checking facts before sharing, being kind online, and asking a trusted adult when unsure. It also opens a simple conversation about how technology is changing jobs, and why learning new skills, including English, matters for their future. These are topics parents and schools already care about, and they fit naturally with the digital education efforts in Malaysia and Indonesia.

— BM —
Ramai murid menggunakan telefon dan aplikasi sebelum sesiapa mengajar mereka cara untuk kekal selamat dalam talian. Pek ini melatih bahasa Inggeris harian sambil membina tabiat selamat: merahsiakan kata laluan dan maklumat peribadi, menyemak fakta sebelum berkongsi, bersikap baik dalam talian, dan bertanya kepada orang dewasa yang dipercayai apabila tidak pasti. Ia juga membuka perbualan mudah tentang bagaimana teknologi mengubah pekerjaan, dan mengapa mempelajari kemahiran baharu, termasuk bahasa Inggeris, penting untuk masa depan mereka. Topik ini sudah menjadi keprihatinan ibu bapa dan sekolah, dan ia selari dengan usaha pendidikan digital di Malaysia dan Indonesia.'),
  ('everyday-english', 'Everyday English', 'general',
   'Greetings, school, family, food and hobbies: short, familiar sentences for beginners. / Salam, sekolah, keluarga, makanan dan hobi: ayat pendek dan biasa untuk murid peringkat asas.',
   'This pack covers the everyday topics found in most beginner (A1–A2) English courses: greetings, school, family, food and hobbies. Short, familiar sentences give shy or beginner students a safe first experience of speaking English out loud in front of the class. Because the game counts who has spoken, you can see at a glance which students have not had a turn yet. Use it as a warm-up before an AI pack, or on its own for general speaking practice.

— BM —
Pek ini merangkumi topik harian yang terdapat dalam kebanyakan kursus bahasa Inggeris peringkat asas (A1–A2): salam, sekolah, keluarga, makanan dan hobi. Ayat yang pendek dan biasa memberi murid yang pemalu atau baru bermula pengalaman pertama yang selamat untuk bertutur dalam bahasa Inggeris di hadapan kelas. Oleh sebab permainan ini mengira siapa yang sudah bercakap, anda boleh melihat dengan cepat murid mana yang belum mendapat giliran. Gunakannya sebagai aktiviti memanaskan badan sebelum pek AI, atau secara sendiri untuk latihan bertutur umum.')
ON CONFLICT (slug) DO NOTHING;

INSERT INTO question (pack_id, game_mode, prompt, target_text, keywords, image_url, difficulty, base_points, time_limit_sec, sort_order)
SELECT p.id, v.game_mode, v.prompt, v.target_text, v.keywords, NULL, v.difficulty, 100, v.time_limit_sec, v.sort_order
FROM (VALUES
  -- ai-basics · read_aloud
  ('ai-basics', 'read_aloud', 'Read this sentence aloud.', 'A computer can learn from many examples', '{}'::text[], 1, 15, 1),
  ('ai-basics', 'read_aloud', 'Read this sentence aloud.', 'Maps on my phone help me find the way', '{}'::text[], 2, 20, 2),
  ('ai-basics', 'read_aloud', 'Read this sentence aloud.', 'The phone can translate words for me', '{}'::text[], 1, 15, 3),
  ('ai-basics', 'read_aloud', 'Read this sentence aloud.', 'Some apps show videos that I might like', '{}'::text[], 2, 20, 4),
  ('ai-basics', 'read_aloud', 'Read this sentence aloud.', 'I can talk to a voice assistant', '{}'::text[], 1, 15, 5),
  ('ai-basics', 'read_aloud', 'Read this sentence aloud.', 'Smart machines can make mistakes too', '{}'::text[], 1, 15, 6),
  ('ai-basics', 'read_aloud', 'Read this sentence aloud.', 'People must check what the computer says', '{}'::text[], 2, 20, 7),
  ('ai-basics', 'read_aloud', 'Read this sentence aloud.', 'Humans make the final decision', '{}'::text[], 1, 15, 8),
  ('ai-basics', 'read_aloud', 'Read this sentence aloud.', 'Artificial intelligence is a smart computer program', '{}'::text[], 2, 20, 9),
  ('ai-basics', 'read_aloud', 'Read this sentence aloud.', 'A robot follows the rules people give it', '{}'::text[], 2, 20, 10),
  -- ai-basics · repeat_after_me
  ('ai-basics', 'repeat_after_me', 'Listen and repeat.', 'We use artificial intelligence at home', '{}'::text[], 2, 20, 1),
  ('ai-basics', 'repeat_after_me', 'Listen and repeat.', 'The computer learns from data', '{}'::text[], 1, 15, 2),
  ('ai-basics', 'repeat_after_me', 'Listen and repeat.', 'Please check the answer again', '{}'::text[], 1, 15, 3),
  ('ai-basics', 'repeat_after_me', 'Listen and repeat.', 'People should make the choice', '{}'::text[], 1, 15, 4),
  ('ai-basics', 'repeat_after_me', 'Listen and repeat.', 'My phone can hear my voice', '{}'::text[], 1, 15, 5),
  ('ai-basics', 'repeat_after_me', 'Listen and repeat.', 'The map shows the fastest road', '{}'::text[], 1, 15, 6),
  ('ai-basics', 'repeat_after_me', 'Listen and repeat.', 'Computers are not always right', '{}'::text[], 1, 15, 7),
  ('ai-basics', 'repeat_after_me', 'Listen and repeat.', 'We use smart tools to help us', '{}'::text[], 2, 20, 8),
  ('ai-basics', 'repeat_after_me', 'Listen and repeat.', 'The app knows my favorite songs', '{}'::text[], 2, 20, 9),
  ('ai-basics', 'repeat_after_me', 'Listen and repeat.', 'Ask a teacher if you are not sure', '{}'::text[], 2, 20, 10),
  -- ai-basics · picture_talk
  ('ai-basics', 'picture_talk', '🤖📚 What do you see?', NULL, ARRAY['robot', 'book']::text[], 1, 20, 1),
  ('ai-basics', 'picture_talk', '📱🗺️ What is on the phone?', NULL, ARRAY['phone', 'map']::text[], 1, 20, 2),
  ('ai-basics', 'picture_talk', '👧🗣️📱 What is the girl doing?', NULL, ARRAY['girl', 'talk', 'phone']::text[], 2, 25, 3),
  ('ai-basics', 'picture_talk', '🤖🍎🍌 The robot is learning. What does it look at?', NULL, ARRAY['robot', 'apple', 'banana']::text[], 2, 25, 4),
  ('ai-basics', 'picture_talk', '🚗🤖🛣️ This car drives by itself. Describe the picture.', NULL, ARRAY['car', 'road', 'robot']::text[], 2, 25, 5),
  ('ai-basics', 'picture_talk', '👩‍⚕️💻 What do you see?', NULL, ARRAY['doctor', 'computer']::text[], 1, 20, 6),
  ('ai-basics', 'picture_talk', '📷🐱 The phone looks at the picture. What does it see?', NULL, ARRAY['camera', 'cat']::text[], 1, 20, 7),
  ('ai-basics', 'picture_talk', '🎵📱 What does the app play?', NULL, ARRAY['music', 'phone']::text[], 1, 20, 8),
  ('ai-basics', 'picture_talk', '👩‍🏫🤖👦 Who is helping the boy?', NULL, ARRAY['teacher', 'robot', 'boy']::text[], 2, 25, 9),
  ('ai-basics', 'picture_talk', '🌧️📱 What is the phone showing?', NULL, ARRAY['rain', 'phone']::text[], 1, 20, 10),
  -- ai-basics · quick_answer
  ('ai-basics', 'quick_answer', 'Can a computer make mistakes? Yes or no?', NULL, ARRAY['yes', 'yeah', 'can']::text[], 1, 15, 1),
  ('ai-basics', 'quick_answer', 'Who makes the final decision: a person or a robot?', NULL, ARRAY['person', 'human', 'people', 'me', 'teacher']::text[], 1, 15, 2),
  ('ai-basics', 'quick_answer', 'Which app helps you find a place: maps or music?', NULL, ARRAY['maps', 'map']::text[], 1, 15, 3),
  ('ai-basics', 'quick_answer', '🤖🤖🤖 How many robots do you see?', NULL, ARRAY['three', '3']::text[], 1, 15, 4),
  ('ai-basics', 'quick_answer', 'What does AI learn from: data or dreams?', NULL, ARRAY['data', 'examples']::text[], 2, 15, 5),
  ('ai-basics', 'quick_answer', 'Is AI always right? Yes or no?', NULL, ARRAY['no', 'not']::text[], 1, 15, 6),
  ('ai-basics', 'quick_answer', 'Name one thing a voice assistant can do.', NULL, ARRAY['music', 'song', 'weather', 'time', 'call', 'alarm', 'search', 'answer', 'play', 'timer', 'news', 'question']::text[], 2, 20, 7),
  ('ai-basics', 'quick_answer', 'What can translate English into Malay: a phone or a pencil?', NULL, ARRAY['phone', 'app']::text[], 1, 15, 8),
  ('ai-basics', 'quick_answer', 'Is a robot a person? Yes or no?', NULL, ARRAY['no', 'not']::text[], 1, 15, 9),
  ('ai-basics', 'quick_answer', 'Who should check the answer from AI?', NULL, ARRAY['me', 'we', 'us', 'people', 'person', 'human', 'teacher', 'you', 'i']::text[], 2, 20, 10),
  -- ai-safe-smart · read_aloud
  ('ai-safe-smart', 'read_aloud', 'Read this sentence aloud.', 'Never share your password with anyone', '{}'::text[], 1, 15, 1),
  ('ai-safe-smart', 'read_aloud', 'Read this sentence aloud.', 'Keep your home address private', '{}'::text[], 1, 15, 2),
  ('ai-safe-smart', 'read_aloud', 'Read this sentence aloud.', 'Check the facts before you share', '{}'::text[], 1, 15, 3),
  ('ai-safe-smart', 'read_aloud', 'Read this sentence aloud.', 'Be kind to people online', '{}'::text[], 1, 15, 4),
  ('ai-safe-smart', 'read_aloud', 'Read this sentence aloud.', 'Ask an adult when you are not sure', '{}'::text[], 2, 20, 5),
  ('ai-safe-smart', 'read_aloud', 'Read this sentence aloud.', 'Not everything on the internet is true', '{}'::text[], 2, 20, 6),
  ('ai-safe-smart', 'read_aloud', 'Read this sentence aloud.', 'A strong password is long and secret', '{}'::text[], 2, 20, 7),
  ('ai-safe-smart', 'read_aloud', 'Read this sentence aloud.', 'Think before you post a photo', '{}'::text[], 1, 15, 8),
  ('ai-safe-smart', 'read_aloud', 'Read this sentence aloud.', 'New jobs will need new skills', '{}'::text[], 1, 15, 9),
  ('ai-safe-smart', 'read_aloud', 'Read this sentence aloud.', 'Learning English helps me in the future', '{}'::text[], 2, 20, 10),
  -- ai-safe-smart · repeat_after_me
  ('ai-safe-smart', 'repeat_after_me', 'Listen and repeat.', 'My password is a secret', '{}'::text[], 1, 15, 1),
  ('ai-safe-smart', 'repeat_after_me', 'Listen and repeat.', 'Stop and think before you click', '{}'::text[], 1, 15, 2),
  ('ai-safe-smart', 'repeat_after_me', 'Listen and repeat.', 'Check if the news is true', '{}'::text[], 1, 15, 3),
  ('ai-safe-smart', 'repeat_after_me', 'Listen and repeat.', 'Please be kind to other people', '{}'::text[], 1, 15, 4),
  ('ai-safe-smart', 'repeat_after_me', 'Listen and repeat.', 'Please ask your teacher for help', '{}'::text[], 1, 15, 5),
  ('ai-safe-smart', 'repeat_after_me', 'Listen and repeat.', 'Do not click strange links', '{}'::text[], 2, 20, 6),
  ('ai-safe-smart', 'repeat_after_me', 'Listen and repeat.', 'I can learn new skills', '{}'::text[], 1, 15, 7),
  ('ai-safe-smart', 'repeat_after_me', 'Listen and repeat.', 'Robots can help people at work', '{}'::text[], 2, 20, 8),
  ('ai-safe-smart', 'repeat_after_me', 'Listen and repeat.', 'Talk to an adult if someone is mean', '{}'::text[], 2, 20, 9),
  ('ai-safe-smart', 'repeat_after_me', 'Listen and repeat.', 'Check other places for the answer', '{}'::text[], 2, 20, 10),
  -- ai-safe-smart · picture_talk
  ('ai-safe-smart', 'picture_talk', '🔒📱 What do you see?', NULL, ARRAY['lock', 'phone']::text[], 1, 20, 1),
  ('ai-safe-smart', 'picture_talk', '🔑🤫 This key is your password. What do you do?', NULL, ARRAY['secret', 'password', 'keep']::text[], 2, 25, 2),
  ('ai-safe-smart', 'picture_talk', '😊💬 Describe the picture.', NULL, ARRAY['happy', 'face', 'message']::text[], 1, 20, 3),
  ('ai-safe-smart', 'picture_talk', '👩‍💻🏠 What is she doing?', NULL, ARRAY['computer', 'home', 'work']::text[], 2, 25, 4),
  ('ai-safe-smart', 'picture_talk', '📰❓ Is this news true? What do you see?', NULL, ARRAY['news', 'question', 'paper']::text[], 2, 25, 5),
  ('ai-safe-smart', 'picture_talk', '👨‍🔧🤖 What do you see?', NULL, ARRAY['man', 'robot', 'work']::text[], 1, 20, 6),
  ('ai-safe-smart', 'picture_talk', '🧑‍🏫📚💻 Describe the picture.', NULL, ARRAY['teacher', 'book', 'computer']::text[], 1, 20, 7),
  ('ai-safe-smart', 'picture_talk', '😢📱 How does the girl feel?', NULL, ARRAY['sad', 'phone']::text[], 1, 20, 8),
  ('ai-safe-smart', 'picture_talk', '🧑‍🌾🚜🌾 What job is this?', NULL, ARRAY['farmer', 'tractor', 'farm']::text[], 2, 25, 9),
  ('ai-safe-smart', 'picture_talk', '🚫🔑👥 Should you share your password?', NULL, ARRAY['no', 'password']::text[], 1, 20, 10),
  -- ai-safe-smart · quick_answer
  ('ai-safe-smart', 'quick_answer', 'Should you share your password with a friend? Yes or no?', NULL, ARRAY['no', 'not', 'never']::text[], 1, 15, 1),
  ('ai-safe-smart', 'quick_answer', 'Who can help you online: a stranger or a teacher?', NULL, ARRAY['teacher', 'parent', 'mother', 'father', 'adult', 'mom', 'dad']::text[], 1, 15, 2),
  ('ai-safe-smart', 'quick_answer', 'A message says you won a free phone. True or false?', NULL, ARRAY['false', 'fake', 'no', 'not']::text[], 2, 20, 3),
  ('ai-safe-smart', 'quick_answer', 'Is it OK to be mean online? Yes or no?', NULL, ARRAY['no', 'not', 'never']::text[], 1, 15, 4),
  ('ai-safe-smart', 'quick_answer', 'How many places should you check for a fact: one or two?', NULL, ARRAY['two', '2', 'many', 'more']::text[], 1, 15, 5),
  ('ai-safe-smart', 'quick_answer', 'Should a password be long or short?', NULL, ARRAY['long']::text[], 1, 15, 6),
  ('ai-safe-smart', 'quick_answer', 'Name one job that uses computers.', NULL, ARRAY['teacher', 'doctor', 'nurse', 'engineer', 'programmer', 'designer', 'scientist', 'pilot', 'banker', 'police', 'office', 'writer', 'manager', 'cashier', 'driver']::text[], 2, 20, 7),
  ('ai-safe-smart', 'quick_answer', 'Is your home address public or private?', NULL, ARRAY['private', 'secret']::text[], 1, 15, 8),
  ('ai-safe-smart', 'quick_answer', 'Before you share news, do you check it or forget it?', NULL, ARRAY['check']::text[], 1, 15, 9),
  ('ai-safe-smart', 'quick_answer', 'Can robots help doctors? Yes or no?', NULL, ARRAY['yes', 'yeah', 'can']::text[], 1, 15, 10),
  -- everyday-english · read_aloud
  ('everyday-english', 'read_aloud', 'Read this sentence aloud.', 'Good morning to all my friends', '{}'::text[], 1, 15, 1),
  ('everyday-english', 'read_aloud', 'Read this sentence aloud.', 'My little sister likes to dance', '{}'::text[], 1, 15, 2),
  ('everyday-english', 'read_aloud', 'Read this sentence aloud.', 'I have two brothers and one sister', '{}'::text[], 2, 20, 3),
  ('everyday-english', 'read_aloud', 'Read this sentence aloud.', 'My family eats breakfast at seven', '{}'::text[], 1, 15, 4),
  ('everyday-english', 'read_aloud', 'Read this sentence aloud.', 'I like chicken rice very much', '{}'::text[], 1, 15, 5),
  ('everyday-english', 'read_aloud', 'Read this sentence aloud.', 'My school starts at eight o''clock', '{}'::text[], 2, 20, 6),
  ('everyday-english', 'read_aloud', 'Read this sentence aloud.', 'I like to sing and dance', '{}'::text[], 1, 15, 7),
  ('everyday-english', 'read_aloud', 'Read this sentence aloud.', 'My father drives a blue car', '{}'::text[], 1, 15, 8),
  ('everyday-english', 'read_aloud', 'Read this sentence aloud.', 'Please open your book to page ten', '{}'::text[], 2, 20, 9),
  ('everyday-english', 'read_aloud', 'Read this sentence aloud.', 'On Sunday we visit my grandmother', '{}'::text[], 2, 20, 10),
  -- everyday-english · repeat_after_me
  ('everyday-english', 'repeat_after_me', 'Listen and repeat.', 'See you later my friend', '{}'::text[], 1, 15, 1),
  ('everyday-english', 'repeat_after_me', 'Listen and repeat.', 'What is your name', '{}'::text[], 1, 15, 2),
  ('everyday-english', 'repeat_after_me', 'Listen and repeat.', 'My brother has twelve toy cars', '{}'::text[], 1, 15, 3),
  ('everyday-english', 'repeat_after_me', 'Listen and repeat.', 'Let''s play together after school', '{}'::text[], 2, 20, 4),
  ('everyday-english', 'repeat_after_me', 'Listen and repeat.', 'Can I borrow your pencil', '{}'::text[], 1, 15, 5),
  ('everyday-english', 'repeat_after_me', 'Listen and repeat.', 'I love my family very much', '{}'::text[], 1, 15, 6),
  ('everyday-english', 'repeat_after_me', 'Listen and repeat.', 'Do you like to swim', '{}'::text[], 1, 15, 7),
  ('everyday-english', 'repeat_after_me', 'Listen and repeat.', 'This is my best friend', '{}'::text[], 1, 15, 8),
  ('everyday-english', 'repeat_after_me', 'Listen and repeat.', 'Can we eat lunch now', '{}'::text[], 1, 15, 9),
  ('everyday-english', 'repeat_after_me', 'Listen and repeat.', 'Have a nice weekend', '{}'::text[], 1, 15, 10),
  -- everyday-english · picture_talk
  ('everyday-english', 'picture_talk', '👨‍👩‍👧‍👦🏠 Who do you see?', NULL, ARRAY['family', 'house']::text[], 1, 20, 1),
  ('everyday-english', 'picture_talk', '🍜🥢 What is this food?', NULL, ARRAY['noodles', 'chopsticks']::text[], 2, 25, 2),
  ('everyday-english', 'picture_talk', '🏫🎒 Describe the picture.', NULL, ARRAY['school', 'bag']::text[], 1, 20, 3),
  ('everyday-english', 'picture_talk', '⚽👟 What do you see?', NULL, ARRAY['football', 'shoe']::text[], 1, 20, 4),
  ('everyday-english', 'picture_talk', '🎨✏️ What is the hobby?', NULL, ARRAY['draw', 'paint', 'pencil']::text[], 2, 25, 5),
  ('everyday-english', 'picture_talk', '🍚🍗 What is for lunch?', NULL, ARRAY['rice', 'chicken']::text[], 1, 20, 6),
  ('everyday-english', 'picture_talk', '🚲🌳 Describe the picture.', NULL, ARRAY['bike', 'tree', 'park']::text[], 1, 20, 7),
  ('everyday-english', 'picture_talk', '👧📖 What is the girl doing?', NULL, ARRAY['girl', 'read', 'book']::text[], 2, 25, 8),
  ('everyday-english', 'picture_talk', '🎤🎶 What is the hobby?', NULL, ARRAY['sing', 'song', 'music']::text[], 1, 20, 9),
  ('everyday-english', 'picture_talk', '🍞🥛 What is for breakfast?', NULL, ARRAY['bread', 'milk']::text[], 1, 20, 10),
  -- everyday-english · quick_answer
  ('everyday-english', 'quick_answer', 'How many days are in a week?', NULL, ARRAY['seven', '7']::text[], 1, 15, 1),
  ('everyday-english', 'quick_answer', 'What do you say to your teacher in the morning?', NULL, ARRAY['good morning', 'morning', 'hello', 'hi']::text[], 1, 15, 2),
  ('everyday-english', 'quick_answer', 'What do you call your mother''s mother?', NULL, ARRAY['grandmother', 'grandma', 'granny']::text[], 2, 20, 3),
  ('everyday-english', 'quick_answer', 'Where do you go to learn every day?', NULL, ARRAY['school', 'class', 'classroom']::text[], 1, 15, 4),
  ('everyday-english', 'quick_answer', 'What color is milk?', NULL, ARRAY['white']::text[], 1, 15, 5),
  ('everyday-english', 'quick_answer', 'Name one food you eat for breakfast.', NULL, ARRAY['rice', 'bread', 'egg', 'eggs', 'noodles', 'cereal', 'porridge', 'toast', 'banana', 'milk', 'roti', 'cake']::text[], 1, 15, 6),
  ('everyday-english', 'quick_answer', 'How many fingers are on one hand?', NULL, ARRAY['five', '5']::text[], 1, 15, 7),
  ('everyday-english', 'quick_answer', 'What do you use to write?', NULL, ARRAY['pen', 'pencil']::text[], 1, 15, 8),
  ('everyday-english', 'quick_answer', 'What is your favorite hobby?', NULL, ARRAY['read', 'reading', 'draw', 'drawing', 'sing', 'singing', 'dance', 'dancing', 'swim', 'swimming', 'football', 'games', 'music', 'cook', 'cooking', 'badminton', 'run', 'running']::text[], 2, 20, 9),
  ('everyday-english', 'quick_answer', 'What do you say when someone helps you?', NULL, ARRAY['thank you', 'thanks']::text[], 1, 15, 10)
) AS v(slug, game_mode, prompt, target_text, keywords, difficulty, time_limit_sec, sort_order)
JOIN question_pack p ON p.slug = v.slug
WHERE NOT EXISTS (SELECT 1 FROM question q WHERE q.pack_id = p.id);

-- Backfill: attach the 002 demo questions (only those, only if unassigned) to Everyday English.
UPDATE question q SET pack_id = p.id, updated_at = now()
FROM question_pack p, (VALUES
  ('read_aloud', 'Read this sentence aloud.', 'I like to eat rice'),
  ('read_aloud', 'Read this sentence aloud.', 'My name is Budi'),
  ('read_aloud', 'Read this sentence aloud.', 'The cat is on the table'),
  ('read_aloud', 'Read this sentence aloud.', 'I go to school every day'),
  ('read_aloud', 'Read this sentence aloud.', 'She has a red bag'),
  ('read_aloud', 'Read this sentence aloud.', 'We play football in the afternoon'),
  ('read_aloud', 'Read this sentence aloud.', 'My mother cooks fried rice for dinner'),
  ('repeat_after_me', 'Listen and repeat.', 'Good morning'),
  ('repeat_after_me', 'Listen and repeat.', 'Thank you very much'),
  ('repeat_after_me', 'Listen and repeat.', 'How are you today'),
  ('repeat_after_me', 'Listen and repeat.', 'I am fine thank you'),
  ('repeat_after_me', 'Listen and repeat.', 'Nice to meet you'),
  ('repeat_after_me', 'Listen and repeat.', 'Where is the bathroom'),
  ('repeat_after_me', 'Listen and repeat.', 'Can you help me please'),
  ('picture_talk', '🐱🛋️ What do you see?', NULL),
  ('picture_talk', '🐶⚽ What do you see?', NULL),
  ('picture_talk', '🍎🍌 What fruit do you see?', NULL),
  ('picture_talk', '☀️🏖️ Describe the picture.', NULL),
  ('picture_talk', '👦📚 What is the boy doing?', NULL),
  ('picture_talk', '🚗🌧️ Describe the picture.', NULL),
  ('picture_talk', '👩‍🍳🍳 What is she doing?', NULL),
  ('quick_answer', 'What color is the sky?', NULL),
  ('quick_answer', 'How many legs does a cat have?', NULL),
  ('quick_answer', 'What animal says "moo"?', NULL),
  ('quick_answer', 'What color is a banana?', NULL),
  ('quick_answer', 'What do you drink when you are thirsty?', NULL),
  ('quick_answer', 'What day comes after Monday?', NULL),
  ('quick_answer', 'What is two plus three?', NULL)
) AS s(game_mode, prompt, target_text)
WHERE p.slug = 'everyday-english'
  AND q.pack_id IS NULL
  AND q.game_mode = s.game_mode AND q.prompt = s.prompt
  AND q.target_text IS NOT DISTINCT FROM s.target_text;

COMMIT;
