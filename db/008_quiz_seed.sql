-- Quiz content (multiple_choice) for the LIVE GAME. Idempotent, non-destructive.
-- Requires db/003_classroom.sql, db/004_packs_seed.sql (packs) and db/006_live.sql (options/correct_option).
-- * Pack 'ai-for-teachers' is added with ON CONFLICT (slug) DO NOTHING.
-- * Questions for a pack are inserted ONLY if that pack has no multiple_choice questions yet (looked up by slug).
-- * correct_option is 0-based. True/false questions use options ['True','False'] and a 15 s limit.

BEGIN;

INSERT INTO question_pack (slug, name, topic, description, why_it_matters) VALUES
  ('ai-for-teachers', 'AI for Teachers', 'ai',
   'For the teacher track: lesson planning with AI, checking AI output, and simple classroom AI policies. / Untuk guru: merancang pelajaran dengan AI, menyemak hasil AI, dan peraturan AI yang mudah di bilik darjah.',
   'Students, parents and colleagues are already asking teachers about AI, often before any training has been offered. This pack gives you a short, practical grounding: how AI can save time on planning and materials, why every AI output must be checked for accuracy, level and bias, and which simple classroom rules keep students and their personal data safe. Play it together in a training session or staff meeting before you run the student packs. It does not replace your professional judgement: the message throughout is that the teacher stays in charge.

— BM —
Murid, ibu bapa dan rakan sekerja sudah mula bertanya kepada guru tentang AI, selalunya sebelum sebarang latihan diberikan. Pek ini memberi asas yang ringkas dan praktikal: bagaimana AI boleh menjimatkan masa untuk merancang pelajaran dan menyediakan bahan, mengapa setiap hasil AI mesti disemak dari segi ketepatan, tahap dan kecenderungan (bias), dan peraturan bilik darjah yang mudah untuk menjaga keselamatan murid serta data peribadi mereka. Mainkannya bersama dalam sesi latihan atau mesyuarat guru sebelum anda menjalankan pek untuk murid. Ia tidak menggantikan pertimbangan profesional anda: mesej utamanya ialah guru tetap memegang kawalan.')
ON CONFLICT (slug) DO NOTHING;

INSERT INTO question (pack_id, game_mode, prompt, target_text, keywords, options, correct_option, image_url,
                      difficulty, base_points, time_limit_sec, sort_order)
SELECT p.id, 'multiple_choice', v.prompt, NULL, '{}'::text[], v.options, v.correct_option, NULL,
       v.difficulty, 100, v.time_limit_sec, v.sort_order
FROM (VALUES
  -- ai-basics
  ('ai-basics', 'What does AI stand for?', ARRAY['Automatic internet', 'Animal information', 'Artificial intelligence', 'Always online']::text[], 2, 1, 20, 1),
  ('ai-basics', 'Which app can use AI to find the fastest road?', ARRAY['A calculator', 'A clock', 'A paint app', 'A map app']::text[], 3, 1, 20, 2),
  ('ai-basics', 'You type ''Selamat pagi'' and the app shows ''Good morning''. What is the app doing?', ARRAY['Drawing', 'Counting', 'Charging', 'Translating']::text[], 3, 1, 20, 3),
  ('ai-basics', 'Why does a video app show you videos you might like?', ARRAY['It learns what you watch', 'It reads your mind', 'It is magic', 'Your teacher picks them']::text[], 0, 1, 20, 4),
  ('ai-basics', 'You ask your phone ''What is the weather today?'' and it answers. What is this?', ARRAY['A camera', 'A voice assistant', 'A calculator', 'A torch']::text[], 1, 1, 20, 5),
  ('ai-basics', 'How does AI usually learn?', ARRAY['By sleeping', 'By eating food', 'From many examples', 'It never learns']::text[], 2, 1, 20, 6),
  ('ai-basics', 'AI gives you an answer that looks wrong. What should you do?', ARRAY['Check it another way', 'Believe it anyway', 'Share it quickly', 'Throw away your books']::text[], 0, 1, 20, 7),
  ('ai-basics', 'Who should make the final decision on important things?', ARRAY['The AI', 'People', 'The phone', 'Nobody']::text[], 1, 1, 20, 8),
  ('ai-basics', 'Which of these usually does NOT use AI?', ARRAY['A translation app', 'A map app', 'A voice assistant', 'A paper notebook']::text[], 3, 1, 20, 9),
  ('ai-basics', 'Your phone unlocks when it sees your face. What does AI do here?', ARRAY['Recognises your face', 'Charges the battery', 'Makes a phone call', 'Plays music']::text[], 0, 2, 20, 10),
  ('ai-basics', 'To learn what a cat looks like, what does AI need?', ARRAY['One cat sound', 'Many cat pictures', 'A real cat to hold', 'Cat food']::text[], 1, 2, 20, 11),
  ('ai-basics', 'An online shop shows ''You may also like…''. What usually picks these items?', ARRAY['Your best friend', 'Your teacher', 'A computer program', 'A lucky draw']::text[], 2, 2, 20, 12),
  ('ai-basics', '''Artificial'' means…', ARRAY['Found in nature', 'Very old', 'Made by people', 'Alive']::text[], 2, 2, 20, 13),
  ('ai-basics', 'A robot vacuum cleans the floor and goes around chairs. What helps it?', ARRAY['Sensors and a program', 'Magic', 'A hidden person', 'Nothing at all']::text[], 0, 2, 20, 14),
  ('ai-basics', 'Why can AI make mistakes?', ARRAY['It gets tired', 'Its examples can be wrong', 'It gets angry', 'It wants to trick you']::text[], 1, 2, 20, 15),
  ('ai-basics', 'AI is always right.', ARRAY['True', 'False']::text[], 1, 1, 15, 16),
  ('ai-basics', 'A map app can use AI to help you avoid traffic jams.', ARRAY['True', 'False']::text[], 0, 1, 15, 17),
  ('ai-basics', 'AI can help translate English into Malay.', ARRAY['True', 'False']::text[], 0, 1, 15, 18),
  ('ai-basics', 'AI understands feelings exactly like a person.', ARRAY['True', 'False']::text[], 1, 2, 15, 19),
  ('ai-basics', 'People can check and correct answers from AI.', ARRAY['True', 'False']::text[], 0, 1, 15, 20),
  -- ai-safe-smart
  ('ai-safe-smart', 'A stranger online asks for your password. What do you do?', ARRAY['Send it quickly', 'Post it online', 'Say no and tell an adult', 'Give half of it']::text[], 2, 1, 20, 1),
  ('ai-safe-smart', 'Which is the strongest password?', ARRAY['123456', 'Blue!Tiger7Rain', 'password', 'abc123']::text[], 1, 1, 20, 2),
  ('ai-safe-smart', 'A message says: ''You won a free phone! Click here now.'' This is probably…', ARRAY['A real gift', 'From your school', 'A prize from a friend', 'A scam']::text[], 3, 1, 20, 3),
  ('ai-safe-smart', 'What is a deepfake?', ARRAY['A fake video made by AI', 'A deep swimming pool', 'A kind of fish', 'A strong password']::text[], 0, 1, 20, 4),
  ('ai-safe-smart', 'You see surprising news online. What should you do first?', ARRAY['Share it with everyone', 'Believe it', 'Change the words', 'Check other sources']::text[], 3, 1, 20, 5),
  ('ai-safe-smart', 'Which information should you keep private?', ARRAY['Your favourite colour', 'Your home address', 'Your favourite food', 'Your hobby']::text[], 1, 1, 20, 6),
  ('ai-safe-smart', 'Someone posts a mean comment about your friend. What is a kind action?', ARRAY['Add another mean comment', 'Share the comment', 'Support your friend', 'Laugh at it']::text[], 2, 1, 20, 7),
  ('ai-safe-smart', 'You use AI to help with homework. What is the smart way?', ARRAY['Copy every word', 'Never read the answer', 'Use it to learn and check', 'Let it do your tests']::text[], 2, 2, 20, 8),
  ('ai-safe-smart', 'A video shows a famous person saying something very strange. It could be…', ARRAY['Always real', 'A deepfake', 'A weather report', 'A radio show']::text[], 1, 2, 20, 9),
  ('ai-safe-smart', 'AI can do some tasks. What will people still need most for future jobs?', ARRAY['No skills at all', 'Only sleep', 'Thinking and creativity', 'Nothing new']::text[], 2, 2, 20, 10),
  ('ai-safe-smart', 'How can AI help a doctor?', ARRAY['Help read X-ray scans', 'Cook the patient''s food', 'Wash the doctor''s car', 'Water the plants']::text[], 0, 2, 20, 11),
  ('ai-safe-smart', 'Before you install a new app, you should…', ARRAY['Give it all your photos', 'Ask a trusted adult', 'Share your password', 'Tell it your address']::text[], 1, 1, 20, 12),
  ('ai-safe-smart', 'Which is safe to share with a new online friend?', ARRAY['Your favourite sport', 'Your password', 'Your home address', 'Your phone number']::text[], 0, 1, 20, 13),
  ('ai-safe-smart', 'Why should you check who made a website?', ARRAY['To change its colour', 'To make it faster', 'To win points', 'To see if it is reliable']::text[], 3, 2, 20, 14),
  ('ai-safe-smart', 'An AI chatbot tells you a fact for your school project. What should you do?', ARRAY['Check another source', 'Copy it without reading', 'Delete your project', 'Tell it your password']::text[], 0, 2, 20, 15),
  ('ai-safe-smart', 'It is OK to share your password with your best friend.', ARRAY['True', 'False']::text[], 1, 1, 15, 16),
  ('ai-safe-smart', 'AI can make fake photos that look real.', ARRAY['True', 'False']::text[], 0, 1, 15, 17),
  ('ai-safe-smart', 'Everything you see on the internet is true.', ARRAY['True', 'False']::text[], 1, 1, 15, 18),
  ('ai-safe-smart', 'Learning new skills helps you get ready for future jobs.', ARRAY['True', 'False']::text[], 0, 1, 15, 19),
  ('ai-safe-smart', 'If a message makes you feel scared or rushed, it might be a scam.', ARRAY['True', 'False']::text[], 0, 2, 15, 20),
  -- everyday-english
  ('everyday-english', 'What do you say when you meet your teacher in the morning?', ARRAY['Good morning', 'Good night', 'Goodbye', 'See you later']::text[], 0, 1, 20, 1),
  ('everyday-english', 'Choose the correct sentence.', ARRAY['She go to school.', 'She goes to school.', 'She going school.', 'She goed to school.']::text[], 1, 2, 20, 2),
  ('everyday-english', 'What is the opposite of ''hot''?', ARRAY['Warm', 'Cold', 'Big', 'Fast']::text[], 1, 1, 20, 3),
  ('everyday-english', 'My mother''s sister is my…', ARRAY['Aunt', 'Uncle', 'Cousin', 'Grandmother']::text[], 0, 1, 20, 4),
  ('everyday-english', 'Which one is a fruit?', ARRAY['Mango', 'Carrot', 'Rice', 'Chicken']::text[], 0, 1, 20, 5),
  ('everyday-english', 'Where do you borrow books at school?', ARRAY['The canteen', 'The field', 'The car park', 'The library']::text[], 3, 1, 20, 6),
  ('everyday-english', 'What day comes after Friday?', ARRAY['Saturday', 'Thursday', 'Sunday', 'Monday']::text[], 0, 1, 20, 7),
  ('everyday-english', 'I ___ breakfast at 7 o''clock every day.', ARRAY['has', 'having', 'to have', 'have']::text[], 3, 2, 20, 8),
  ('everyday-english', 'Which one is a hobby?', ARRAY['Brushing your teeth', 'Waking up', 'Taking a bus', 'Playing badminton']::text[], 3, 1, 20, 9),
  ('everyday-english', 'How do you ask for help politely?', ARRAY['Help me now!', 'Can you help me, please?', 'You help me.', 'Give me help!']::text[], 1, 2, 20, 10),
  ('everyday-english', 'What do you say when someone gives you a gift?', ARRAY['Sorry', 'Excuse me', 'Thank you', 'You''re welcome']::text[], 2, 1, 20, 11),
  ('everyday-english', 'Who helps sick people in a hospital?', ARRAY['A farmer', 'A pilot', 'A doctor', 'A chef']::text[], 2, 1, 20, 12),
  ('everyday-english', 'One child, two ___.', ARRAY['childs', 'children', 'childes', 'child']::text[], 1, 2, 20, 13),
  ('everyday-english', 'What time is ''half past seven''?', ARRAY['7:15', '6:30', '7:30', '7:45']::text[], 2, 2, 20, 14),
  ('everyday-english', 'Which question asks about age?', ARRAY['How are you?', 'Where are you?', 'How old are you?', 'Who are you?']::text[], 2, 1, 20, 15),
  ('everyday-english', '''Breakfast'' is the meal we eat in the morning.', ARRAY['True', 'False']::text[], 0, 1, 15, 16),
  ('everyday-english', 'A week has eight days.', ARRAY['True', 'False']::text[], 1, 1, 15, 17),
  ('everyday-english', '''Brother'' and ''sister'' are family words.', ARRAY['True', 'False']::text[], 0, 1, 15, 18),
  ('everyday-english', 'We use a spoon to write.', ARRAY['True', 'False']::text[], 1, 1, 15, 19),
  ('everyday-english', '''Tuesday'' comes before ''Monday''.', ARRAY['True', 'False']::text[], 1, 2, 15, 20),
  -- ai-for-teachers
  ('ai-for-teachers', 'What is a good way to use AI for lesson planning?', ARRAY['Copy the plan unchanged', 'Draft ideas, then adapt', 'Let it teach the class', 'Skip checking the level']::text[], 1, 2, 20, 1),
  ('ai-for-teachers', 'AI writes a quiz for your class. What should you do before using it?', ARRAY['Print it immediately', 'Check facts and level', 'Share it with no review', 'Make it longer']::text[], 1, 2, 20, 2),
  ('ai-for-teachers', 'AI states a wrong fact very confidently. What is this often called?', ARRAY['A hallucination', 'A deepfake', 'A password', 'A backup']::text[], 0, 2, 20, 3),
  ('ai-for-teachers', 'What should you NOT paste into a public AI tool?', ARRAY['A general topic', 'A grammar question', 'Names and personal info', 'A well-known poem']::text[], 2, 1, 20, 4),
  ('ai-for-teachers', 'A student''s essay may be AI-written. What is the best first step?', ARRAY['Talk with the student', 'Give zero at once', 'Post it online', 'Ignore it forever']::text[], 0, 2, 20, 5),
  ('ai-for-teachers', 'Which classroom AI rule is most helpful?', ARRAY['Never talk about AI', 'AI does all homework', 'Tell when AI was used', 'Hide any AI use']::text[], 2, 1, 20, 6),
  ('ai-for-teachers', 'AI can help teachers save time on…', ARRAY['Knowing each student', 'Caring for students', 'Drafting worksheets', 'Final grading decisions']::text[], 2, 1, 20, 7),
  ('ai-for-teachers', 'How can AI help with students at different levels?', ARRAY['Create levelled versions', 'Give all the same text', 'Remove reading practice', 'Replace the teacher']::text[], 0, 2, 20, 8),
  ('ai-for-teachers', 'Why teach students to check AI answers?', ARRAY['AI is never useful', 'Builds critical thinking', 'It wastes class time', 'Books are always wrong']::text[], 1, 1, 20, 9),
  ('ai-for-teachers', 'Who is responsible for AI-made material you use in class?', ARRAY['The AI company', 'The students', 'Nobody', 'The teacher']::text[], 3, 1, 20, 10),
  ('ai-for-teachers', 'A good prompt for an AI lesson helper includes…', ARRAY['Only one word', 'Your password', 'Student home addresses', 'Age, level and goal']::text[], 3, 2, 20, 11),
  ('ai-for-teachers', 'What is a safe way to use AI with younger students?', ARRAY['Own accounts, no rules', 'Share their photos', 'Unsupervised chatting', 'Teacher-led class demo']::text[], 3, 2, 20, 12),
  ('ai-for-teachers', 'AI-generated text can contain errors or bias.', ARRAY['True', 'False']::text[], 0, 1, 15, 13),
  ('ai-for-teachers', 'It is fine to upload students'' test results with their names to any AI tool.', ARRAY['True', 'False']::text[], 1, 1, 15, 14),
  ('ai-for-teachers', 'Students should learn that people make the final decision, not AI.', ARRAY['True', 'False']::text[], 0, 1, 15, 15)
) AS v(slug, prompt, options, correct_option, difficulty, time_limit_sec, sort_order)
JOIN question_pack p ON p.slug = v.slug
WHERE NOT EXISTS (SELECT 1 FROM question q WHERE q.pack_id = p.id AND q.game_mode = 'multiple_choice');

COMMIT;
