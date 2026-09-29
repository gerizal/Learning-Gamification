// classroom.js — PlayClass "one screen, teams" mode (fallback when students have no devices).
// One setup screen → Lobby → Stage (team quiz turns) → Finale (+ participation CSV); /reports linked from the finale.
// Teacher = game master on one laptop + projector. Quiz only (multiple_choice); the captain of the team answers.
// Vanilla ES module, no build. API: CONTRACT.md "CLASSROOM MODE" + "Classroom mode — multiple_choice turns".

const LS_LANG = 'classroom.lang';
const LS_SESSION = 'classroom.sessionId';
const LS_TIPS = 'classroom.tipsCollapsed';
const LS_SCHOOL = 'playclass.school';     // JSON {school} — shared with /host
const LS_SCHOOLS = 'playclass.schools';   // JSON [school names used on this device]
const LS_MUTED = 'speakingGame.muted';
const QUIZ = 'multiple_choice';
const TILES = [
  { key: 'red', shape: '▲' }, { key: 'blue', shape: '◆' }, { key: 'yellow', shape: '●' }, { key: 'green', shape: '■' },
];
const reducedMotion = !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);

// ---------------------------------------------------------------- i18n (teacher UI; quiz content stays as written)
const I18N = {
  en: {
    back_home: 'Back to home', skip_to_content: 'Skip to content', brand_sub: 'One screen · Teams',
    lang_label: 'Language',
    mute: 'Mute sound effects', unmute: 'Turn sound effects on', shortcuts: 'Keyboard shortcuts', fullscreen: 'Fullscreen', exit_fullscreen: 'Exit fullscreen',
    close: 'Close', loading: 'Loading…',
    setup_title: 'Team quiz on one screen', saved_class: 'Use a saved class', new_class_opt: '＋ New class (from the names below)',
    saved_opt: '{name} · {n} students', class_auto: 'Class {date}',
    pick_pack: '1 · Pick a quiz pack', why_teach: 'Why teach this?', topic_ai: 'AI', topic_general: 'General', q_count: '{n} questions',
    no_quiz: 'No quiz questions in this pack yet', no_packs: 'No quiz packs yet. Ask your admin to add questions.',
    paste_label: '2 · Paste student names, one per line', paste_ph: 'Aisyah\nArjun\nMei Ling', names_count: '{n} names',
   
    your_school: 'Your school', change: 'Change', school: 'School', school_ph: 'e.g. SK Taman Megah', school_saved: 'Saved on this device.',
    school_from_class: 'From the saved class.', need_school: 'Enter your school at the top.',
    whos_absent: 'Who’s absent? (optional)', whos_absent_n: 'Who’s absent? ({n} absent)',
    attend_hint: 'Everyone is present by default. Tap a name to mark absent; tap again to mark present.',
    present: 'present', absent: 'absent', present_count: '{n} of {total} present',
    game_size: '3 · Teams & rounds', team_count: 'Teams', rounds: 'Rounds', fewer: 'Fewer', more: 'More',
    size_summary: '{teams} teams × {rounds} rounds = {turns} questions · about {per} students per team',
    advice_short: 'Only {turns} of {present} students will be captain once.', advice_fix: 'Use {r} rounds so everyone is captain',
    advice_ok: 'Every student present gets to be captain at least once.',
    need_pack: 'Pick a quiz pack.', need_names: 'Paste at least {n} names (one per team, not absent).',
    start_game: 'Make teams', creating: 'Making teams…',
    lobby_title: 'Meet the teams!', lobby_sub: '{cls} · {pack} · {turns} questions',
    lobby_hint: 'To move a student: tap their name, then tap “Move here” on another team.',
    move_here: 'Move here', moving: 'Moving {name}: pick a team.', move_cancel: 'Cancel', keep_one: 'Each team needs at least one student.',
    shuffle: 'Shuffle teams', shuffled: 'Teams shuffled!', back_setup: 'Setup', start_big: 'START', members_n: '{n} players',
    teams_locked: 'Teams are locked once the game has started.', all_questions: 'All packs',
    scoreboard: 'Scoreboard', round_turn: 'Round {r} of {rt} · Question {t} of {tt}', end_game: 'End game',
    end_confirm: 'End the game now and show the results?', tips_show: 'Tips', tips_hide: 'Hide tips',
    team_turn: 'Team {emoji} {team} — captain {name}!', team_turn_plain: 'Team {team}, captain {name}.',
    captain: 'Team captain this turn', suggested: 'suggested', captain_times: '{n} times captain',
    pts: 'pts', score_aria: '{team}: {score} points, streak {streak}', current_team: 'now playing',
    q_instr: 'Discuss with your team! Captain, pick your answer.', answer_opt: 'Answer {k}: {text}',
    pause: 'Pause timer', resume: 'Resume timer', paused: 'Timer paused', time_up: '⏰ Time’s up! Captain, final answer?',
    discuss: 'Discuss! Then click the team’s answer or press 1–{n}.', locked_in: 'Locked in! …',
    skip: 'Skip', next_turn: 'Next', finish: 'See results', skipped_msg: 'No problem! {team} will get another chance.',
    msg_right: 'CORRECT! Brilliant, {team}!', msg_wrong: 'Good try, {team}!', answer_was: 'The answer: {k} {text}',
    your_answer: 'Team answer: {k}', combo: 'TEAM COMBO x{m}!', fast: 'FAST! +{n}',
    result_aria_right: 'Correct! {team} gets {points} points and now has {score}.', result_aria_wrong: 'Not this time. {team} has {score} points.',
    answered_already: 'This question was already answered. Press Next.',
    finale_title: 'GAME OVER!', participation: 'Participation', mvp: 'MVP', mvp_line: '{name} · {team} · {points} points',
    part_summary: '{present} of {total} present · {spoke} took a turn · {rate}%', part_rate: 'Participation rate',
    col_student: 'Student', col_team: 'Team', col_present: 'Present', col_turns: 'Turns', col_attempts: 'Answers', col_best: 'Best', col_points: 'Points',
    yes: 'Yes', no: 'No', download_csv: 'Download CSV', nav_reports: 'View all reports', play_again: 'Play again with same class', new_game: 'New setup',
    finale_aria: 'Game over. {team} wins with {score} points. {spoke} of {present} students took a turn.',
   
   
   
   
   
    resume_text: 'A game is still running: {cls}, question {t} of {tt}.', resume_done: 'All questions are played in {cls}. Finish the game to see the results.',
    resume_game: 'Resume game', end_it: 'End it and see results',
    gm_tips: 'Game master tips', tips_collapse: 'Hide', tips_expand: 'Show', say: 'Say', do: 'Do',
    tip_s1_say: 'Today we play a team quiz!', tip_s1_do: 'Pick a pack, paste the class list, press Make teams. Read “Why teach this?” to introduce the topic.',
    tip_lobby_say: 'Find your team! Tigers sit here, Eagles there…', tip_lobby_do: 'Move students if a team is too strong. Then press START.',
    tip_ready_say: '{team}, discuss together! {name}, you are captain: tell me your answer.', tip_ready_do: 'Read the question aloud. Click the answer the captain says, or press 1–4. C changes the captain.',
    tip_paused_say: 'Take your time. Think together.', tip_paused_do: 'Timer is paused. Press P to continue.',
    tip_timeup_say: 'Time’s up! Captain, your final answer?', tip_timeup_do: 'Click the team’s answer (or 1–4). Or press S to skip.',
    tip_judge_say: 'Drum roll, everyone!', tip_judge_do: 'Let the class drum on the tables.',
    tip_good_say: 'Big clap for {team}!', tip_good_do: 'Ask: “Why is that the answer?” Then press → for the next team.',
    tip_wrong_say: 'Good try, {team}! Who knows why this is the answer?', tip_wrong_do: 'Explain the correct answer in one sentence. Never blame the captain. Press →.',
    tip_skip_say: 'That’s okay! You can try next time.', tip_skip_do: 'Skipping is fine. Keep the energy positive.',
    tip_final_say: 'Every team did great! Let’s clap for everyone.', tip_final_do: 'Download the CSV for your program report.',
   
    keys_answer: 'Choose answer 1–4', keys_c: 'Next team captain', keys_p: 'Pause / resume timer', keys_next: 'Next question', keys_s: 'Skip question',
    keys_t: 'Show / hide tips', keys_m: 'Mute', keys_f: 'Fullscreen', keys_q: 'This help', keys_esc: 'Close / cancel',
    err_network: 'Cannot reach the server. Check the connection and try again.', err_server: 'Server problem ({s}). Try again in a moment.',
    err_request: 'Request failed ({s}).', health_down: 'Server not reachable. Start the backend and reload.',
    health_db: 'database not connected', health_prefix: 'Server: ', class_api_missing: 'Classroom API is not available on this server yet (/api/class).',
  },
  ms: {
    back_home: 'Kembali ke laman utama', skip_to_content: 'Langkau ke kandungan', brand_sub: 'Satu skrin · Pasukan',
    lang_label: 'Bahasa',
    mute: 'Senyapkan kesan bunyi', unmute: 'Hidupkan kesan bunyi', shortcuts: 'Pintasan papan kekunci', fullscreen: 'Skrin penuh', exit_fullscreen: 'Keluar skrin penuh',
    close: 'Tutup', loading: 'Memuatkan…',
    setup_title: 'Kuiz pasukan pada satu skrin', saved_class: 'Guna kelas tersimpan', new_class_opt: '＋ Kelas baharu (daripada nama di bawah)',
    saved_opt: '{name} · {n} murid', class_auto: 'Kelas {date}',
    pick_pack: '1 · Pilih pek kuiz', why_teach: 'Kenapa ajar topik ini?', topic_ai: 'AI', topic_general: 'Umum', q_count: '{n} soalan',
    no_quiz: 'Belum ada soalan kuiz dalam pek ini', no_packs: 'Belum ada pek kuiz. Minta admin tambah soalan.',
    paste_label: '2 · Tampal nama murid, satu setiap baris', paste_ph: 'Aisyah\nArjun\nMei Ling', names_count: '{n} nama',
   
    your_school: 'Sekolah anda', change: 'Tukar', school: 'Sekolah', school_ph: 'cth. SK Taman Megah', school_saved: 'Disimpan pada peranti ini.',
    school_from_class: 'Daripada kelas tersimpan.', need_school: 'Masukkan nama sekolah di bahagian atas.',
    whos_absent: 'Siapa tidak hadir? (pilihan)', whos_absent_n: 'Siapa tidak hadir? ({n} tidak hadir)',
    attend_hint: 'Semua dianggap hadir. Ketik nama untuk tanda tidak hadir; ketik lagi untuk tanda hadir.',
    present: 'hadir', absent: 'tidak hadir', present_count: '{n} daripada {total} hadir',
    game_size: '3 · Pasukan & pusingan', team_count: 'Pasukan', rounds: 'Pusingan', fewer: 'Kurangkan', more: 'Tambah',
    size_summary: '{teams} pasukan × {rounds} pusingan = {turns} soalan · kira-kira {per} murid setiap pasukan',
    advice_short: 'Hanya {turns} daripada {present} murid akan jadi kapten.', advice_fix: 'Guna {r} pusingan supaya semua jadi kapten',
    advice_ok: 'Setiap murid yang hadir jadi kapten sekurang-kurangnya sekali.',
    need_pack: 'Pilih pek kuiz.', need_names: 'Tampal sekurang-kurangnya {n} nama (seorang setiap pasukan, yang hadir).',
    start_game: 'Bentuk pasukan', creating: 'Membentuk pasukan…',
    lobby_title: 'Kenali pasukan!', lobby_sub: '{cls} · {pack} · {turns} soalan',
    lobby_hint: 'Untuk pindah murid: ketik nama mereka, kemudian ketik “Pindah ke sini” pada pasukan lain.',
    move_here: 'Pindah ke sini', moving: 'Memindahkan {name}: pilih pasukan.', move_cancel: 'Batal', keep_one: 'Setiap pasukan perlu sekurang-kurangnya seorang murid.',
    shuffle: 'Kocok pasukan', shuffled: 'Pasukan dikocok!', back_setup: 'Persediaan', start_big: 'MULA', members_n: '{n} pemain',
    teams_locked: 'Pasukan dikunci selepas permainan bermula.', all_questions: 'Semua pek',
    scoreboard: 'Papan markah', round_turn: 'Pusingan {r} daripada {rt} · Soalan {t} daripada {tt}', end_game: 'Tamatkan',
    end_confirm: 'Tamatkan permainan sekarang dan tunjuk keputusan?', tips_show: 'Tip', tips_hide: 'Sorok tip',
    team_turn: 'Pasukan {emoji} {team} — kapten {name}!', team_turn_plain: 'Pasukan {team}, kapten {name}.',
    captain: 'Kapten pasukan giliran ini', suggested: 'dicadangkan', captain_times: '{n} kali jadi kapten',
    pts: 'mata', score_aria: '{team}: {score} mata, rentetan {streak}', current_team: 'sedang bermain',
    q_instr: 'Bincang dengan pasukan! Kapten, pilih jawapan.', answer_opt: 'Jawapan {k}: {text}',
    pause: 'Jeda pemasa', resume: 'Sambung pemasa', paused: 'Pemasa dijeda', time_up: '⏰ Masa tamat! Kapten, jawapan akhir?',
    discuss: 'Bincang! Kemudian klik jawapan pasukan atau tekan 1–{n}.', locked_in: 'Dikunci! …',
    skip: 'Langkau', next_turn: 'Seterusnya', finish: 'Lihat keputusan', skipped_msg: 'Tiada masalah! {team} akan dapat peluang lagi.',
    msg_right: 'BETUL! Hebat, {team}!', msg_wrong: 'Cubaan yang baik, {team}!', answer_was: 'Jawapannya: {k} {text}',
    your_answer: 'Jawapan pasukan: {k}', combo: 'KOMBO PASUKAN x{m}!', fast: 'PANTAS! +{n}',
    result_aria_right: 'Betul! {team} dapat {points} mata, kini {score}.', result_aria_wrong: 'Bukan kali ini. {team} ada {score} mata.',
    answered_already: 'Soalan ini sudah dijawab. Tekan Seterusnya.',
    finale_title: 'TAMAT!', participation: 'Penyertaan', mvp: 'MVP', mvp_line: '{name} · {team} · {points} mata',
    part_summary: '{present} daripada {total} hadir · {spoke} dapat giliran · {rate}%', part_rate: 'Kadar penyertaan',
    col_student: 'Murid', col_team: 'Pasukan', col_present: 'Hadir', col_turns: 'Giliran', col_attempts: 'Jawapan', col_best: 'Terbaik', col_points: 'Mata',
    yes: 'Ya', no: 'Tidak', download_csv: 'Muat turun CSV', nav_reports: 'Lihat semua laporan', play_again: 'Main lagi dengan kelas sama', new_game: 'Persediaan baharu',
    finale_aria: 'Permainan tamat. {team} menang dengan {score} mata. {spoke} daripada {present} murid dapat giliran.',
   
   
   
   
   
    resume_text: 'Permainan masih berjalan: {cls}, soalan {t} daripada {tt}.', resume_done: 'Semua soalan di {cls} sudah dimain. Tamatkan permainan untuk lihat keputusan.',
    resume_game: 'Sambung permainan', end_it: 'Tamatkan dan lihat keputusan',
    gm_tips: 'Tip pengacara', tips_collapse: 'Sorok', tips_expand: 'Tunjuk', say: 'Sebut', do: 'Buat',
    tip_s1_say: 'Hari ini kita main kuiz berpasukan!', tip_s1_do: 'Pilih pek, tampal senarai kelas, tekan Bentuk pasukan. Baca “Kenapa ajar topik ini?” untuk memperkenalkan topik.',
    tip_lobby_say: 'Cari pasukan kamu! Harimau duduk sini, Helang sana…', tip_lobby_do: 'Pindah murid jika pasukan terlalu kuat. Kemudian tekan MULA.',
    tip_ready_say: '{team}, bincang bersama! {name}, kamu kapten: beritahu jawapan kamu.', tip_ready_do: 'Baca soalan dengan kuat. Klik jawapan kapten, atau tekan 1–4. C tukar kapten.',
    tip_paused_say: 'Ambil masa. Fikir bersama.', tip_paused_do: 'Pemasa dijeda. Tekan P untuk sambung.',
    tip_timeup_say: 'Masa tamat! Kapten, jawapan akhir?', tip_timeup_do: 'Klik jawapan pasukan (atau 1–4). Atau tekan S untuk langkau.',
    tip_judge_say: 'Semua, pukul gendang!', tip_judge_do: 'Biar kelas ketuk meja.',
    tip_good_say: 'Tepukan gemuruh untuk {team}!', tip_good_do: 'Tanya: “Kenapa itu jawapannya?” Kemudian tekan → untuk pasukan seterusnya.',
    tip_wrong_say: 'Cubaan yang baik, {team}! Siapa tahu kenapa ini jawapannya?', tip_wrong_do: 'Terangkan jawapan betul dalam satu ayat. Jangan salahkan kapten. Tekan →.',
    tip_skip_say: 'Tak apa! Boleh cuba lain kali.', tip_skip_do: 'Langkau tidak mengapa. Kekalkan suasana positif.',
    tip_final_say: 'Semua pasukan hebat! Tepuk tangan untuk semua.', tip_final_do: 'Muat turun CSV untuk laporan program.',
   
    keys_answer: 'Pilih jawapan 1–4', keys_c: 'Kapten seterusnya', keys_p: 'Jeda / sambung pemasa', keys_next: 'Soalan seterusnya', keys_s: 'Langkau soalan',
    keys_t: 'Tunjuk / sorok tip', keys_m: 'Senyap', keys_f: 'Skrin penuh', keys_q: 'Bantuan ini', keys_esc: 'Tutup / batal',
    err_network: 'Tidak dapat menghubungi pelayan. Semak sambungan dan cuba lagi.', err_server: 'Masalah pelayan ({s}). Cuba lagi sebentar.',
    err_request: 'Permintaan gagal ({s}).', health_down: 'Pelayan tidak dapat dihubungi. Mulakan backend dan muat semula.',
    health_db: 'pangkalan data tidak bersambung', health_prefix: 'Pelayan: ', class_api_missing: 'API kelas belum tersedia di pelayan ini (/api/class).',
  },
  id: {
    back_home: 'Kembali ke beranda', skip_to_content: 'Lewati ke konten', brand_sub: 'Satu layar · Tim',
    lang_label: 'Bahasa',
    mute: 'Matikan efek suara', unmute: 'Nyalakan efek suara', shortcuts: 'Pintasan keyboard', fullscreen: 'Layar penuh', exit_fullscreen: 'Keluar layar penuh',
    close: 'Tutup', loading: 'Memuat…',
    setup_title: 'Kuis tim di satu layar', saved_class: 'Pakai kelas tersimpan', new_class_opt: '＋ Kelas baru (dari nama di bawah)',
    saved_opt: '{name} · {n} siswa', class_auto: 'Kelas {date}',
    pick_pack: '1 · Pilih paket kuis', why_teach: 'Kenapa materi ini penting?', topic_ai: 'AI', topic_general: 'Umum', q_count: '{n} soal',
    no_quiz: 'Belum ada soal kuis di paket ini', no_packs: 'Belum ada paket kuis. Minta admin menambah soal.',
    paste_label: '2 · Tempel nama siswa, satu per baris', paste_ph: 'Aisyah\nArjun\nMei Ling', names_count: '{n} nama',
   
    your_school: 'Sekolah Anda', change: 'Ubah', school: 'Sekolah', school_ph: 'mis. SDN 1 Menteng', school_saved: 'Tersimpan di perangkat ini.',
    school_from_class: 'Dari kelas tersimpan.', need_school: 'Isi nama sekolah di bagian atas.',
    whos_absent: 'Siapa yang tidak hadir? (opsional)', whos_absent_n: 'Siapa yang tidak hadir? ({n} tidak hadir)',
    attend_hint: 'Semua dianggap hadir. Ketuk nama untuk menandai tidak hadir; ketuk lagi untuk hadir.',
    present: 'hadir', absent: 'tidak hadir', present_count: '{n} dari {total} hadir',
    game_size: '3 · Tim & ronde', team_count: 'Tim', rounds: 'Ronde', fewer: 'Kurangi', more: 'Tambah',
    size_summary: '{teams} tim × {rounds} ronde = {turns} soal · sekitar {per} siswa per tim',
    advice_short: 'Hanya {turns} dari {present} siswa yang jadi kapten.', advice_fix: 'Pakai {r} ronde supaya semua jadi kapten',
    advice_ok: 'Setiap siswa yang hadir jadi kapten minimal sekali.',
    need_pack: 'Pilih paket kuis.', need_names: 'Tempel minimal {n} nama (satu per tim, yang hadir).',
    start_game: 'Bentuk tim', creating: 'Membentuk tim…',
    lobby_title: 'Kenalan dengan tim!', lobby_sub: '{cls} · {pack} · {turns} soal',
    lobby_hint: 'Untuk memindah siswa: ketuk namanya, lalu ketuk “Pindah ke sini” di tim lain.',
    move_here: 'Pindah ke sini', moving: 'Memindah {name}: pilih tim.', move_cancel: 'Batal', keep_one: 'Setiap tim butuh minimal satu siswa.',
    shuffle: 'Acak tim', shuffled: 'Tim diacak!', back_setup: 'Persiapan', start_big: 'MULAI', members_n: '{n} pemain',
    teams_locked: 'Tim dikunci setelah permainan dimulai.', all_questions: 'Semua paket',
    scoreboard: 'Papan skor', round_turn: 'Ronde {r} dari {rt} · Soal {t} dari {tt}', end_game: 'Akhiri',
    end_confirm: 'Akhiri permainan sekarang dan tampilkan hasil?', tips_show: 'Tips', tips_hide: 'Sembunyikan tips',
    team_turn: 'Tim {emoji} {team} — kapten {name}!', team_turn_plain: 'Tim {team}, kapten {name}.',
    captain: 'Kapten tim giliran ini', suggested: 'disarankan', captain_times: '{n} kali jadi kapten',
    pts: 'poin', score_aria: '{team}: {score} poin, beruntun {streak}', current_team: 'sedang main',
    q_instr: 'Diskusikan dengan tim! Kapten, pilih jawaban.', answer_opt: 'Jawaban {k}: {text}',
    pause: 'Jeda waktu', resume: 'Lanjutkan waktu', paused: 'Waktu dijeda', time_up: '⏰ Waktu habis! Kapten, jawaban akhir?',
    discuss: 'Diskusi! Lalu klik jawaban tim atau tekan 1–{n}.', locked_in: 'Terkunci! …',
    skip: 'Lewati', next_turn: 'Lanjut', finish: 'Lihat hasil', skipped_msg: 'Tidak apa-apa! {team} akan dapat kesempatan lagi.',
    msg_right: 'BENAR! Hebat, {team}!', msg_wrong: 'Usaha bagus, {team}!', answer_was: 'Jawabannya: {k} {text}',
    your_answer: 'Jawaban tim: {k}', combo: 'KOMBO TIM x{m}!', fast: 'CEPAT! +{n}',
    result_aria_right: 'Benar! {team} dapat {points} poin, sekarang {score}.', result_aria_wrong: 'Belum kali ini. {team} punya {score} poin.',
    answered_already: 'Soal ini sudah dijawab. Tekan Lanjut.',
    finale_title: 'SELESAI!', participation: 'Partisipasi', mvp: 'MVP', mvp_line: '{name} · {team} · {points} poin',
    part_summary: '{present} dari {total} hadir · {spoke} dapat giliran · {rate}%', part_rate: 'Tingkat partisipasi',
    col_student: 'Siswa', col_team: 'Tim', col_present: 'Hadir', col_turns: 'Giliran', col_attempts: 'Jawaban', col_best: 'Terbaik', col_points: 'Poin',
    yes: 'Ya', no: 'Tidak', download_csv: 'Unduh CSV', nav_reports: 'Lihat semua laporan', play_again: 'Main lagi dengan kelas yang sama', new_game: 'Persiapan baru',
    finale_aria: 'Permainan selesai. {team} menang dengan {score} poin. {spoke} dari {present} siswa dapat giliran.',
   
   
   
   
   
    resume_text: 'Masih ada permainan berjalan: {cls}, soal {t} dari {tt}.', resume_done: 'Semua soal di {cls} sudah dimainkan. Akhiri permainan untuk melihat hasil.',
    resume_game: 'Lanjutkan permainan', end_it: 'Akhiri dan lihat hasil',
    gm_tips: 'Tips pemandu', tips_collapse: 'Sembunyikan', tips_expand: 'Tampilkan', say: 'Ucapkan', do: 'Lakukan',
    tip_s1_say: 'Hari ini kita main kuis per tim!', tip_s1_do: 'Pilih paket, tempel daftar kelas, tekan Bentuk tim. Baca “Kenapa materi ini penting?” untuk membuka topik.',
    tip_lobby_say: 'Cari timmu! Harimau duduk di sini, Elang di sana…', tip_lobby_do: 'Pindahkan siswa kalau satu tim terlalu kuat. Lalu tekan MULAI.',
    tip_ready_say: '{team}, diskusikan bersama! {name}, kamu kapten: sebutkan jawabanmu.', tip_ready_do: 'Bacakan soalnya. Klik jawaban yang disebut kapten, atau tekan 1–4. C ganti kapten.',
    tip_paused_say: 'Santai saja. Pikirkan bersama.', tip_paused_do: 'Waktu dijeda. Tekan P untuk lanjut.',
    tip_timeup_say: 'Waktu habis! Kapten, jawaban akhirnya?', tip_timeup_do: 'Klik jawaban tim (atau 1–4). Atau tekan S untuk melewati.',
    tip_judge_say: 'Semua, tabuh genderang!', tip_judge_do: 'Ajak kelas mengetuk meja.',
    tip_good_say: 'Tepuk tangan untuk {team}!', tip_good_do: 'Tanya: “Kenapa itu jawabannya?” Lalu tekan → untuk tim berikutnya.',
    tip_wrong_say: 'Usaha bagus, {team}! Siapa tahu kenapa ini jawabannya?', tip_wrong_do: 'Jelaskan jawaban yang benar dalam satu kalimat. Jangan menyalahkan kapten. Tekan →.',
    tip_skip_say: 'Tidak apa-apa! Nanti boleh coba lagi.', tip_skip_do: 'Melewati soal boleh. Jaga suasana tetap positif.',
    tip_final_say: 'Semua tim hebat! Tepuk tangan untuk semua.', tip_final_do: 'Unduh CSV untuk laporan program.',
   
    keys_answer: 'Pilih jawaban 1–4', keys_c: 'Kapten berikutnya', keys_p: 'Jeda / lanjutkan waktu', keys_next: 'Soal berikutnya', keys_s: 'Lewati soal',
    keys_t: 'Tampilkan / sembunyikan tips', keys_m: 'Bisukan', keys_f: 'Layar penuh', keys_q: 'Bantuan ini', keys_esc: 'Tutup / batal',
    err_network: 'Tidak bisa terhubung ke server. Periksa koneksi lalu coba lagi.', err_server: 'Server bermasalah ({s}). Coba lagi sebentar.',
    err_request: 'Permintaan gagal ({s}).', health_down: 'Server tidak bisa dihubungi. Jalankan backend lalu muat ulang.',
    health_db: 'database belum tersambung', health_prefix: 'Server: ', class_api_missing: 'API kelas belum tersedia di server ini (/api/class).',
  },
};
// ---- "Teacher presents — individual" strings (CONTRACT "TEACHER PRESENTS — INDIVIDUAL or GROUPS"), merged below.
const I18N_IND = {
  en: {
    grouping_label: 'Students play as', grouping_individual: 'Individuals', grouping_teams: 'Groups',
    brand_sub_ind: 'One screen · Individuals', setup_title_ind: 'Class quiz on one screen',
    q_how_many: '3 · Number of questions', qc_summary: '{q} questions · {n} students · about {per} turns each',
    qc_short: 'Only {q} of {n} students can get a turn. Pick more questions, or play again later.',
    qc_ok: 'Every student present can get at least one turn.', qc_repeat: 'This quiz has {avail} questions, so some will come back.',
    need_names_ind: 'Paste at least one name (not absent).', too_many: 'At most 60 students per game ({n} now).',
    start_ind: 'Start', creating_ind: 'Getting ready…',
    ready_title: 'Ready to play!', ready_sub: '{cls} · {pack} · {q} questions', ready_players: 'Players ({n})',
    who_answering: 'Who’s answering?', who_search_label: 'Find a student by name', who_search_ph: 'Type a name…',
    who_none: 'No student called “{q}”.', who_matches: '{n} matching students', turns_n: '{n} turns so far',
    leaderboard: 'Leaderboard', lb_more: '+{n} more', lb_row: '{rank}. {name}, {score} points',
    q_progress: 'Question {t} of {tt}', ind_turn_plain: '{name}, your answer?',
    q_instr_ind: 'Hands up! Pick a student, then click their answer.', discuss_ind: 'Click {name}’s answer or press 1–{n}.',
    msg_right_ind: 'CORRECT! Brilliant, {name}!', msg_wrong_ind: 'Good try, {name}!',
    result_aria_right_ind: 'Correct! {name} gets {points} points and now has {score}.', result_aria_wrong_ind: 'Not this time. {name} has {score} points.',
    skipped_msg_ind: 'No problem! Let’s try the next question.',
    add_student: 'Add student', add_student_label: 'Name of the student who just arrived', add_student_ph: 'Name', add: 'Add',
    added: '{names} joined the game. Welcome!', added_team: '{name} joined {team}. Welcome!', add_skipped: 'Already playing: {names}',
    full_ranking: 'Full ranking', part_summary_ind: '{spoke} of {present} answered at least once · {rate}%',
    finale_aria_ind: 'Game over. {name} wins with {score} points. {spoke} of {present} students answered at least once.',
    keys_c_ind: 'Next student (fewest turns first)', time_up_ind: '⏰ Time’s up! Final answer?', err_503: 'The server is not ready yet.', err_413: 'That upload is too large.',
    tip_s1_ind_say: 'Today we play a class quiz — everyone for themselves!', tip_s1_ind_do: 'Pick a quiz, paste the class list, choose how many questions, then press Start.',
    tip_readyscr_say: 'Everyone gets a chance today. Hands up when you know the answer!', tip_readyscr_do: 'Check the names. Late students can join any time with “Add student”. Then press START.',
    tip_ready_ind_say: 'Who knows the answer? Hands up!', tip_ready_ind_do: 'Ask the question. Pick a student with a hand up — or the suggested one. Click their answer or press 1–4.',
    tip_timeup_ind_say: 'Time’s up! {name}, your final answer?', tip_timeup_ind_do: 'Click {name}’s answer (or 1–4). Or press S to skip.',
    tip_good_ind_say: 'Big clap for {name}!', tip_good_ind_do: 'Ask: “Why is that the answer?” Then press → for the next question.',
    tip_wrong_ind_say: 'Good try, {name}! Who can explain the answer?', tip_wrong_ind_do: 'Explain the correct answer in one sentence. Never blame the student. Press →.',
    tip_skip_ind_say: 'That’s okay! Everyone gets another chance.', tip_skip_ind_do: 'Skipping is fine. Keep the energy positive.',
    tip_final_ind_say: 'Everyone did great! Let’s clap for the whole class.', tip_final_ind_do: 'Download the CSV for your program report.',
  },
  ms: {
    grouping_label: 'Murid bermain secara', grouping_individual: 'Individu', grouping_teams: 'Kumpulan',
    brand_sub_ind: 'Satu skrin · Individu', setup_title_ind: 'Kuiz kelas pada satu skrin',
    q_how_many: '3 · Bilangan soalan', qc_summary: '{q} soalan · {n} murid · kira-kira {per} giliran setiap murid',
    qc_short: 'Hanya {q} daripada {n} murid dapat giliran. Pilih lebih banyak soalan, atau main lagi nanti.',
    qc_ok: 'Setiap murid yang hadir boleh dapat sekurang-kurangnya satu giliran.', qc_repeat: 'Kuiz ini ada {avail} soalan, jadi ada yang akan berulang.',
    need_names_ind: 'Tampal sekurang-kurangnya satu nama (yang hadir).', too_many: 'Maksimum 60 murid setiap permainan ({n} sekarang).',
    start_ind: 'Mula', creating_ind: 'Bersedia…',
    ready_title: 'Sedia untuk bermain!', ready_sub: '{cls} · {pack} · {q} soalan', ready_players: 'Pemain ({n})',
    who_answering: 'Siapa menjawab?', who_search_label: 'Cari murid mengikut nama', who_search_ph: 'Taip nama…',
    who_none: 'Tiada murid bernama “{q}”.', who_matches: '{n} murid sepadan', turns_n: '{n} giliran setakat ini',
    leaderboard: 'Papan pendahulu', lb_more: '+{n} lagi', lb_row: '{rank}. {name}, {score} mata',
    q_progress: 'Soalan {t} daripada {tt}', ind_turn_plain: '{name}, apa jawapan kamu?',
    q_instr_ind: 'Angkat tangan! Pilih murid, kemudian klik jawapannya.', discuss_ind: 'Klik jawapan {name} atau tekan 1–{n}.',
    msg_right_ind: 'BETUL! Hebat, {name}!', msg_wrong_ind: 'Cubaan yang baik, {name}!',
    result_aria_right_ind: 'Betul! {name} dapat {points} mata, kini {score}.', result_aria_wrong_ind: 'Bukan kali ini. {name} ada {score} mata.',
    skipped_msg_ind: 'Tiada masalah! Jom cuba soalan seterusnya.',
    add_student: 'Tambah murid', add_student_label: 'Nama murid yang baru tiba', add_student_ph: 'Nama', add: 'Tambah',
    added: '{names} menyertai permainan. Selamat datang!', added_team: '{name} menyertai {team}. Selamat datang!', add_skipped: 'Sudah bermain: {names}',
    full_ranking: 'Kedudukan penuh', part_summary_ind: '{spoke} daripada {present} menjawab sekurang-kurangnya sekali · {rate}%',
    finale_aria_ind: 'Permainan tamat. {name} menang dengan {score} mata. {spoke} daripada {present} murid menjawab sekurang-kurangnya sekali.',
    keys_c_ind: 'Murid seterusnya (giliran paling sedikit dahulu)', time_up_ind: '⏰ Masa tamat! Jawapan akhir?', err_503: 'Pelayan belum sedia.', err_413: 'Muat naik itu terlalu besar.',
    tip_s1_ind_say: 'Hari ini kita main kuiz kelas — setiap orang untuk diri sendiri!', tip_s1_ind_do: 'Pilih kuiz, tampal senarai kelas, pilih bilangan soalan, kemudian tekan Mula.',
    tip_readyscr_say: 'Semua dapat peluang hari ini. Angkat tangan bila tahu jawapannya!', tip_readyscr_do: 'Semak nama. Murid lewat boleh masuk bila-bila masa dengan “Tambah murid”. Kemudian tekan MULA.',
    tip_ready_ind_say: 'Siapa tahu jawapannya? Angkat tangan!', tip_ready_ind_do: 'Tanya soalan. Pilih murid yang angkat tangan — atau yang dicadangkan. Klik jawapannya atau tekan 1–4.',
    tip_timeup_ind_say: 'Masa tamat! {name}, jawapan akhir?', tip_timeup_ind_do: 'Klik jawapan {name} (atau 1–4). Atau tekan S untuk langkau.',
    tip_good_ind_say: 'Tepukan gemuruh untuk {name}!', tip_good_ind_do: 'Tanya: “Kenapa itu jawapannya?” Kemudian tekan → untuk soalan seterusnya.',
    tip_wrong_ind_say: 'Cubaan yang baik, {name}! Siapa boleh terangkan jawapannya?', tip_wrong_ind_do: 'Terangkan jawapan betul dalam satu ayat. Jangan salahkan murid. Tekan →.',
    tip_skip_ind_say: 'Tak apa! Semua akan dapat peluang lagi.', tip_skip_ind_do: 'Langkau tidak mengapa. Kekalkan suasana positif.',
    tip_final_ind_say: 'Semua hebat! Tepuk tangan untuk seluruh kelas.', tip_final_ind_do: 'Muat turun CSV untuk laporan program.',
  },
  id: {
    grouping_label: 'Siswa bermain sebagai', grouping_individual: 'Individu', grouping_teams: 'Kelompok',
    brand_sub_ind: 'Satu layar · Individu', setup_title_ind: 'Kuis kelas di satu layar',
    q_how_many: '3 · Jumlah soal', qc_summary: '{q} soal · {n} siswa · sekitar {per} giliran per siswa',
    qc_short: 'Hanya {q} dari {n} siswa yang dapat giliran. Pilih lebih banyak soal, atau main lagi nanti.',
    qc_ok: 'Setiap siswa yang hadir bisa dapat minimal satu giliran.', qc_repeat: 'Kuis ini punya {avail} soal, jadi ada yang muncul lagi.',
    need_names_ind: 'Tempel minimal satu nama (yang hadir).', too_many: 'Maksimal 60 siswa per permainan ({n} sekarang).',
    start_ind: 'Mulai', creating_ind: 'Menyiapkan…',
    ready_title: 'Siap bermain!', ready_sub: '{cls} · {pack} · {q} soal', ready_players: 'Pemain ({n})',
    who_answering: 'Siapa yang menjawab?', who_search_label: 'Cari siswa berdasarkan nama', who_search_ph: 'Ketik nama…',
    who_none: 'Tidak ada siswa bernama “{q}”.', who_matches: '{n} siswa cocok', turns_n: '{n} giliran sejauh ini',
    leaderboard: 'Papan peringkat', lb_more: '+{n} lainnya', lb_row: '{rank}. {name}, {score} poin',
    q_progress: 'Soal {t} dari {tt}', ind_turn_plain: '{name}, apa jawabanmu?',
    q_instr_ind: 'Angkat tangan! Pilih siswa, lalu klik jawabannya.', discuss_ind: 'Klik jawaban {name} atau tekan 1–{n}.',
    msg_right_ind: 'BENAR! Hebat, {name}!', msg_wrong_ind: 'Usaha bagus, {name}!',
    result_aria_right_ind: 'Benar! {name} dapat {points} poin, sekarang {score}.', result_aria_wrong_ind: 'Belum kali ini. {name} punya {score} poin.',
    skipped_msg_ind: 'Tidak apa-apa! Ayo coba soal berikutnya.',
    add_student: 'Tambah siswa', add_student_label: 'Nama siswa yang baru datang', add_student_ph: 'Nama', add: 'Tambah',
    added: '{names} ikut bermain. Selamat datang!', added_team: '{name} bergabung dengan {team}. Selamat datang!', add_skipped: 'Sudah bermain: {names}',
    full_ranking: 'Peringkat lengkap', part_summary_ind: '{spoke} dari {present} menjawab minimal sekali · {rate}%',
    finale_aria_ind: 'Permainan selesai. {name} menang dengan {score} poin. {spoke} dari {present} siswa menjawab minimal sekali.',
    keys_c_ind: 'Siswa berikutnya (giliran paling sedikit dulu)', time_up_ind: '⏰ Waktu habis! Jawaban akhir?', err_503: 'Server belum siap.', err_413: 'Unggahan terlalu besar.',
    tip_s1_ind_say: 'Hari ini kita main kuis kelas — masing-masing untuk diri sendiri!', tip_s1_ind_do: 'Pilih kuis, tempel daftar kelas, pilih jumlah soal, lalu tekan Mulai.',
    tip_readyscr_say: 'Semua dapat kesempatan hari ini. Angkat tangan kalau tahu jawabannya!', tip_readyscr_do: 'Cek nama-namanya. Siswa yang terlambat bisa ikut kapan saja lewat “Tambah siswa”. Lalu tekan MULAI.',
    tip_ready_ind_say: 'Siapa tahu jawabannya? Angkat tangan!', tip_ready_ind_do: 'Bacakan soalnya. Pilih siswa yang angkat tangan — atau yang disarankan. Klik jawabannya atau tekan 1–4.',
    tip_timeup_ind_say: 'Waktu habis! {name}, jawaban akhirnya?', tip_timeup_ind_do: 'Klik jawaban {name} (atau 1–4). Atau tekan S untuk melewati.',
    tip_good_ind_say: 'Tepuk tangan untuk {name}!', tip_good_ind_do: 'Tanya: “Kenapa itu jawabannya?” Lalu tekan → untuk soal berikutnya.',
    tip_wrong_ind_say: 'Usaha bagus, {name}! Siapa bisa menjelaskan jawabannya?', tip_wrong_ind_do: 'Jelaskan jawaban yang benar dalam satu kalimat. Jangan menyalahkan siswa. Tekan →.',
    tip_skip_ind_say: 'Tidak apa-apa! Semua dapat kesempatan lagi.', tip_skip_ind_do: 'Melewati soal boleh. Jaga suasana tetap positif.',
    tip_final_ind_say: 'Semua hebat! Tepuk tangan untuk seluruh kelas.', tip_final_ind_do: 'Unduh CSV untuk laporan program.',
  },
};
for (const l of Object.keys(I18N_IND)) Object.assign(I18N[l], I18N_IND[l]);
const LANGS = ['en', 'ms', 'id'];
const LOCALE = { en: 'en-GB', ms: 'ms-MY', id: 'id-ID' };
let lang = 'en';

function t(key, vars) {
  let s = (I18N[lang] && I18N[lang][key]) ?? I18N.en[key] ?? key;
  if (vars) s = s.replace(/\{(\w+)\}/g, (m, k) => (vars[k] !== undefined && vars[k] !== null ? String(vars[k]) : m));
  return s;
}


// Fun team names per language (keyed by the server's emoji; falls back to the server's name).
const TEAM_I18N = {
  '🐯': { en: 'Tigers', ms: 'Harimau', id: 'Harimau' },
  '🦅': { en: 'Eagles', ms: 'Helang', id: 'Elang' },
  '🐬': { en: 'Dolphins', ms: 'Lumba-lumba', id: 'Lumba-lumba' },
  '🦊': { en: 'Foxes', ms: 'Rubah', id: 'Rubah' },
  '🐘': { en: 'Elephants', ms: 'Gajah', id: 'Gajah' },
  '🦜': { en: 'Parrots', ms: 'Kakak Tua', id: 'Kakatua' },
};
const TEAM_COLORS = ['cyan', 'pink', 'lime', 'amber', 'violet', 'orange'];
/** Server names are "BM / EN" (e.g. "Harimau / Tigers"): known emoji → our per-language name, else pick the matching half. */
function teamName(tm) {
  if (!tm) return '';
  if (TEAM_I18N[tm.emoji] && TEAM_I18N[tm.emoji][lang]) return TEAM_I18N[tm.emoji][lang];
  const parts = String(tm.name || '').split(' / ');
  return parts.length === 2 ? (lang === 'en' ? parts[1] : parts[0]).trim() : (tm.name || '');
}
function teamStyle(tm, i = 0) {
  const c = tm && tm.color;
  if (c && /^#|^rgb|^hsl/.test(c)) return `--team:${c}`;
  const key = TEAM_COLORS.includes(c) ? c : TEAM_COLORS[i % TEAM_COLORS.length];
  return `--team:var(--team-${key})`;
}

// ---------------------------------------------------------------- utilities
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

/** Tiny DOM builder: h('div', {class:'x', onclick: fn}, 'text', child) — strings are always text nodes. */
function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k === 'style') el.style.cssText = v;
    else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
    else if (v === true) el.setAttribute(k, '');
    else el.setAttribute(k, String(v));
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}
const SVGNS = 'http://www.w3.org/2000/svg';
/** Lucide icon from the local sprite (scripts/build_icons.mjs). */
function icon(name) {
  const s = document.createElementNS(SVGNS, 'svg');
  s.setAttribute('class', 'ic'); s.setAttribute('aria-hidden', 'true'); s.setAttribute('focusable', 'false');
  const u = document.createElementNS(SVGNS, 'use'); u.setAttribute('href', `/static/icons.svg#${name}`); s.append(u);
  return s;
}
/** Set a label, keeping the element's data-icon (if any) in front of the text. */
function setLabel(el, text, name = el.dataset.icon) { el.replaceChildren(...(name ? [icon(name), ' '] : []), text); }
/** GAIN mascot per team colour key (5 mascots + the lightbulb for the 6th team). */
const TEAM_MASCOT = { cyan: 'blue-256.webp', pink: 'pink-256.webp', lime: 'green-256.webp', amber: 'lightbulb.svg', violet: 'purple-256.webp', orange: 'red-256.webp' };
function teamKey(tm, i = 0) { const c = tm && tm.color; return TEAM_COLORS.includes(c) ? c : TEAM_COLORS[i % TEAM_COLORS.length]; }
function teamMascot(tm, i = 0, cls = '') {
  return h('span', { class: `se-plate ${cls}`.trim(), 'aria-hidden': 'true' },
    h('img', { src: `/static/brand/mascots/${TEAM_MASCOT[teamKey(tm, i)]}`, alt: '', width: '256', height: '256', decoding: 'async' }));
}
/** Log a recoverable failure ONCE per context, so "storage blocked" / "bad JSON" is visible and never
 *  reads the same as a genuinely empty value (the page then falls back to its defaults on purpose). */
const warned = new Set();
function warnOnce(context, err) {
  if (warned.has(context)) return;
  warned.add(context);
  console.warn(`[classroom] ${context} — falling back to defaults`, err);
}
function lsGet(key) {
  try { return window.localStorage.getItem(key); } catch (err) { warnOnce(`localStorage read failed (${key})`, err); return null; }
}
function lsSet(key, val) { try { window.localStorage.setItem(key, val); } catch (err) { warnOnce(`localStorage write failed (${key})`, err); } }
function lsDel(key) { try { window.localStorage.removeItem(key); } catch (err) { warnOnce(`localStorage delete failed (${key})`, err); } }
/** API numbers (scores, counts, turns, points): absent or not a number means "none yet", so 0 is the
 *  true value here — these are tallies to display, never a limit that 0 could turn into "unbounded". */
function n0(v) { const n = Number(v); return Number.isFinite(n) ? n : 0; }
const fmtInt = (n) => n0(n).toLocaleString(LOCALE[lang]);
const pct = (n) => Math.round(n0(n));
function fmtTime(sec) { const s = Math.max(0, Math.ceil(sec)); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`; }
function fmtDate(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleDateString(LOCALE[lang], { day: 'numeric', month: 'short', year: 'numeric' });
}
function shuffle(arr) { const a = [...arr]; for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; } return a; }
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
function isTypingTarget(el) { return el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT' || el.isContentEditable); }

/** Split a prompt into a leading emoji "picture" and the remaining text (same rule as the learner game). */
function splitEmoji(prompt) {
  const text = String(prompt || '').trim();
  const m = text.match(/^((?:\p{Extended_Pictographic}|\p{Emoji_Modifier}|\p{Regional_Indicator}|‍|️|\s)+)/u);
  if (m && /\p{Extended_Pictographic}|\p{Regional_Indicator}/u.test(m[1])) return { emoji: m[1].trim(), text: text.slice(m[1].length).trim() };
  const all = text.match(/\p{Extended_Pictographic}[️‍\p{Emoji_Modifier}\p{Extended_Pictographic}]*/gu);
  if (all && all.length) return { emoji: all.join(' '), text: text.replace(/\p{Extended_Pictographic}|️|‍|\p{Emoji_Modifier}/gu, '').replace(/\s+/g, ' ').trim() };
  return { emoji: '', text };
}

function toast(message, type = 'info', ms = 4500) {
  const region = $('#toasts');
  const close = h('button', { type: 'button', class: 'toast-close', 'aria-label': t('close') }, '×');
  const cls = type === 'error' ? ' toast-error' : type === 'success' ? ' toast-success' : '';
  const el = h('div', { class: `toast${cls}`, role: type === 'error' ? 'alert' : 'status' }, h('span', { class: 'toast-msg' }, message), close);
  const remove = () => el.remove();
  close.addEventListener('click', remove);
  region.append(el);
  while (region.children.length > 3) region.firstElementChild.remove();
  setTimeout(remove, ms);
}

let announceTimer = 0;
function announce(msg) {
  const el = $('#announcer');
  el.textContent = '';
  clearTimeout(announceTimer);
  announceTimer = setTimeout(() => { el.textContent = msg; }, 60);
}

// ---------------------------------------------------------------- SFX (WebAudio synth, no files)
const sfx = (() => {
  let ctx = null;
  let muted = lsGet(LS_MUTED) === '1';
  function ac() {
    if (muted) return null;
    try {
      if (!ctx) { const C = window.AudioContext || window.webkitAudioContext; if (!C) return null; ctx = new C(); }
      if (ctx.state === 'suspended') ctx.resume();
      return ctx;
    } catch (err) { warnOnce('Web Audio unavailable (sound effects off)', err); return null; }
  }
  function tone(freq, { at = 0, dur = 0.12, type = 'sine', vol = 0.18, to = null } = {}) {
    const c = ac(); if (!c) return;
    const t0 = c.currentTime + at;
    const o = c.createOscillator(); const g = c.createGain();
    o.type = type; o.frequency.setValueAtTime(freq, t0);
    if (to) o.frequency.exponentialRampToValueAtTime(to, t0 + dur);
    g.gain.setValueAtTime(0.0001, t0);
    g.gain.exponentialRampToValueAtTime(vol, t0 + 0.01);
    g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
    o.connect(g).connect(c.destination);
    o.start(t0); o.stop(t0 + dur + 0.02);
  }
  return {
    get muted() { return muted; },
    setMuted(v) { muted = !!v; lsSet(LS_MUTED, muted ? '1' : '0'); },
    unlock() { ac(); },
    click() { tone(880, { dur: 0.05, type: 'square', vol: 0.05 }); },
    recStart() { tone(520, { dur: 0.09, type: 'triangle', to: 880, vol: 0.14 }); },
    recStop() { tone(880, { dur: 0.09, type: 'triangle', to: 440, vol: 0.12 }); },
    tick() { tone(180 + Math.random() * 40, { dur: 0.05, type: 'triangle', vol: 0.09 }); },
    star(i) { tone([1047, 1319, 1568][i] || 1568, { at: 0.1 + i * 0.28, dur: 0.22, type: 'triangle', vol: 0.16 }); },
    coin() { tone(988, { dur: 0.07, type: 'square', vol: 0.07 }); tone(1319, { at: 0.07, dur: 0.22, type: 'square', vol: 0.07 }); },
    soft() { tone(523, { dur: 0.16, type: 'sine', vol: 0.12 }); tone(659, { at: 0.16, dur: 0.24, type: 'sine', vol: 0.12 }); },
    combo() { [659, 784, 988].forEach((f, i) => tone(f, { at: 0.72 + i * 0.06, dur: 0.1, type: 'square', vol: 0.06 })); },
    buzz() { tone(220, { dur: 0.35, type: 'square', to: 180, vol: 0.06 }); },
    whoosh() { tone(300, { dur: 0.25, type: 'sawtooth', to: 1200, vol: 0.04 }); },
    fanfare() { [523, 659, 784, 1047, 784, 1047, 1319].forEach((f, i) => tone(f, { at: i * 0.12, dur: i === 6 ? 0.5 : 0.14, type: 'square', vol: 0.06 })); },
  };
})();

// ---------------------------------------------------------------- confetti (canvas; off with reduced motion)
const fx = (() => {
  let raf = 0; let parts = [];
  let colors = [];
  function burst(n = 160) {
    if (reducedMotion) return;
    // brand confetti colours come from theme-se.css (--se-confetti)
    colors = (getComputedStyle(document.documentElement).getPropertyValue('--se-confetti') || '').split(',').map((x) => x.trim()).filter(Boolean);
    if (!colors.length) colors = ['currentColor'];
    const cv = $('#fx-canvas'); if (!cv) return;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    cv.width = innerWidth * dpr; cv.height = innerHeight * dpr;
    const c2 = cv.getContext('2d'); c2.setTransform(dpr, 0, 0, dpr, 0, 0);
    for (let i = 0; i < n; i++) {
      const fromLeft = i % 2 === 0;
      parts.push({
        x: fromLeft ? -10 : innerWidth + 10, y: innerHeight * (0.45 + Math.random() * 0.3),
        vx: (fromLeft ? 1 : -1) * (4 + Math.random() * 9), vy: -(9 + Math.random() * 11),
        w: 7 + Math.random() * 7, h: 9 + Math.random() * 9, r: Math.random() * Math.PI, vr: (Math.random() - 0.5) * 0.4,
        c: colors[i % colors.length], life: 0,
      });
    }
    cancelAnimationFrame(raf);
    const step = () => {
      c2.clearRect(0, 0, innerWidth, innerHeight);
      parts = parts.filter((p) => p.life < 240 && p.y < innerHeight + 40);
      for (const p of parts) {
        p.life++; p.vy += 0.32; p.vx *= 0.985; p.x += p.vx; p.y += p.vy; p.r += p.vr;
        c2.save(); c2.translate(p.x, p.y); c2.rotate(p.r); c2.fillStyle = p.c;
        c2.globalAlpha = Math.max(0, 1 - p.life / 240);
        c2.fillRect(-p.w / 2, -p.h / 2, p.w, p.h * Math.abs(Math.cos(p.r * 2)) + 2);
        c2.restore();
      }
      if (parts.length) raf = requestAnimationFrame(step); else c2.clearRect(0, 0, innerWidth, innerHeight);
    };
    raf = requestAnimationFrame(step);
  }
  return { burst };
})();

// ---------------------------------------------------------------- API
class ApiError extends Error { constructor(message, status, data) { super(message); this.status = status; this.data = data; } }
function detailToText(detail) {
  if (!detail) return '';
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map((d) => (d && d.msg) ? d.msg : JSON.stringify(d)).join('; ');
  return JSON.stringify(detail);
}
async function api(path, { method = 'GET', json, form } = {}) {
  const opts = { method, headers: { Accept: 'application/json' } };
  if (json !== undefined) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(json); }
  if (form) opts.body = form;
  let res;
  try { res = await fetch(path, opts); } catch { throw new ApiError(t('err_network'), 0); }
  let data = null;
  const text = await res.text();
  if (text) { try { data = JSON.parse(text); } catch { data = null; } }
  if (!res.ok) {
    const detail = detailToText(data && data.detail);
    let msg;
    if (res.status === 503) msg = `${t('err_503')} ${detail}`.trim();
    else if (res.status === 413) msg = t('err_413');
    else msg = detail || (res.status >= 500 ? t('err_server', { s: res.status }) : t('err_request', { s: res.status }));
    throw new ApiError(msg, res.status, data);
  }
  return data;
}
function showError(err) {
  console.error(err);
  toast((err && (err.userMessage || err.message)) || t('err_request', { s: '?' }), 'error', 6000);
}

// ---------------------------------------------------------------- state
const setup = {
  classrooms: [],
  savedId: '',          // '' = new class from the pasted names
  classroom: null,      // detail of the saved class
  packs: [],            // ready-made packs (API) + teacher's own quizzes (localStorage)
  packId: null,
  absent: new Set(),    // lowercased names
  teamCount: 4,
  rounds: 3,
  teamCountTouched: false,
  roundsTouched: false,
  grouping: 'teams',    // 'teams' | 'individual' (CONTRACT "TEACHER PRESENTS")
  questionCount: 10,    // individual: 5 / 10 / 15 / 20
};
const QC_OPTIONS = [5, 10, 15, 20];
const URLP = new URLSearchParams(location.search);   // ?pack=<id>&grouping=individual|teams&school=<name> (from /host)
let paramsApplied = false;
/** The running session is an individual one (one team row per student). */
const sessInd = () => !!(game.session && game.session.grouping === 'individual');
/** Mode for the current screen: setup follows the switch, game screens follow the session. */
const modeInd = () => ((screen === 'setup' || !game.session) ? setup.grouping === 'individual' : sessInd());
function syncMode() {
  const ind = modeInd();
  document.body.classList.toggle('is-ind', ind);
  const sub = $('.cr-brand-sub');
  if (sub) { sub.dataset.i18n = ind ? 'brand_sub_ind' : 'brand_sub'; sub.textContent = t(sub.dataset.i18n); }
}
const game = {
  session: null,
  phase: 'ready',        // ready | judging | result
  speakerId: null,       // team captain this turn
  attemptsUsed: 0,
  lastResult: null,
  lastChoice: null,
  lastTurnNo: null,
  moving: null,
  finish: null,
  manualPick: false,     // individual: teacher changed the suggested student this turn
};
const SCREENS = ['setup', 'lobby', 'ready', 'stage', 'finale', 'loading'];
let screen = null;
let navGuard = false;

function show(name, { focus = true } = {}) {
  screen = name;
  for (const s of SCREENS) { const el = document.getElementById(`scr-${s}`); if (el) el.hidden = s !== name; }
  document.body.classList.toggle('on-stage', name === 'stage');
  const slot = $(`#scr-${name} .tips-slot`);
  const tips = $('#gm-tips');
  if (slot) { if (tips.parentElement !== slot) slot.append(tips); tips.hidden = false; } else tips.hidden = true;
  syncMode();
  placeAddStudent();
  if (name !== 'stage') window.scrollTo({ top: 0, behavior: 'auto' });
  if (focus) {
    const heading = $(`#scr-${name} h1`);
    if (heading) { heading.setAttribute('tabindex', '-1'); heading.focus({ preventScroll: true }); }
  }
  if (location.hash !== '#setup') history.replaceState(history.state, '', '#setup');
  // Browser Back: a running game is guarded by one extra history entry (see the popstate handler in init).
  try {
    if ((name === 'lobby' || name === 'ready' || name === 'stage') && !navGuard) { history.pushState({ cr: 'game' }, '', '#setup'); navGuard = true; }
    else if (name === 'setup') navGuard = false;
  } catch { /* ignore */ }
}

// ---------------------------------------------------------------- tips
let tipKey = 's1';
let tipVars = {};
function setTip(key, vars = {}) { tipKey = key; tipVars = vars; renderTips(); }
/** Individual sessions use their own copy where it exists (tip_<key>_ind_say / _do). */
function tipKeyFor(k) { return modeInd() && I18N.en[`tip_${k}_ind_say`] ? `${k}_ind` : k; }
function renderTips() {
  const body = $('#gm-tips-body');
  const k = tipKeyFor(tipKey);
  const say = t(`tip_${k}_say`, tipVars);
  const doIt = t(`tip_${k}_do`, tipVars);
  body.replaceChildren(...[
    say ? h('p', { class: 'tip-say' }, h('strong', {}, `${t('say')}: `), `“${say}”`) : null,
    doIt ? h('p', { class: 'tip-do' }, h('strong', {}, `${t('do')}: `), doIt) : null].filter(Boolean));
  const collapsed = lsGet(LS_TIPS) === '1';
  $('#gm-tips').classList.toggle('is-collapsed', collapsed);
  body.hidden = collapsed;
  const btn = $('#gm-tips-collapse');
  btn.setAttribute('aria-expanded', String(!collapsed));
  btn.textContent = collapsed ? `▸ ${t('tips_expand')}` : `▾ ${t('tips_collapse')}`;
  const st = $('#stage-tips-toggle');
  setLabel(st, collapsed ? t('tips_show') : t('tips_hide'), 'lightbulb');
  st.setAttribute('aria-expanded', String(!collapsed));
}
function toggleTips() { lsSet(LS_TIPS, lsGet(LS_TIPS) === '1' ? '0' : '1'); renderTips(); if (screen === 'stage') requestAnimationFrame(fitQuestion); }

function applyI18n() {
  document.documentElement.lang = lang;
  for (const el of $$('[data-i18n]')) { if (el.dataset.icon) setLabel(el, t(el.dataset.i18n)); else el.textContent = t(el.dataset.i18n); }
  for (const el of $$('[data-i18n-aria]')) el.setAttribute('aria-label', t(el.dataset.i18nAria));
  for (const el of $$('[data-i18n-title]')) el.setAttribute('title', t(el.dataset.i18nTitle));
  for (const el of $$('[data-i18n-ph]')) el.setAttribute('placeholder', t(el.dataset.i18nPh));
  for (const b of $$('.lang-btn')) b.setAttribute('aria-pressed', String(b.dataset.lang === lang));
  syncMode(); syncMuteBtn(); syncFsBtn(); renderTips(); renderKeys();
}
function setLang(l) {
  if (!LANGS.includes(l) || l === lang) return;
  lang = l;
  lsSet(LS_LANG, l);
  applyI18n();
  if (screen === 'setup') renderSetup();
  else if (screen === 'lobby') renderLobby();
  else if (screen === 'ready') renderReady();
  else if (screen === 'stage') renderStage({ intro: false });
  else if (screen === 'finale' && game.finish) renderFinale(game.finish, { celebrate: false });
}

// ================================================================= 1. SETUP (one screen)
/** Teacher's own quizzes written by the live host UI: [{pack_id, edit_key, name}]. */
function myQuizzes() {
  try {
    const v = JSON.parse(window.localStorage.getItem('live.myQuizzes') || '[]');  // written by host.js
    return Array.isArray(v) ? v.filter((q) => q && Number.isFinite(Number(q.pack_id))) : [];
  } catch (err) { warnOnce('saved quizzes (live.myQuizzes) unreadable', err); return []; }
}
// null = counts unknown (a teacher quiz from localStorage); a missing mode key = no quiz questions → 0
const quizCount = (p) => (p.question_counts ? n0(p.question_counts[QUIZ]) : null);

async function goSetup() {
  show('loading', { focus: false });
  try {
    const [classes, packs] = await Promise.all([api('/api/class/classrooms'), api('/api/class/packs')]);
    setup.classrooms = Array.isArray(classes) ? classes : [];
    const list = Array.isArray(packs) ? packs : [];
    const known = new Set(list.map((p) => p.id));
    const mine = myQuizzes().filter((q) => !known.has(Number(q.pack_id)))
      .map((q) => ({ id: Number(q.pack_id), name: q.name || `Quiz #${q.pack_id}`, topic: 'mine', mine: true, question_counts: null }));
    for (const p of list) if (myQuizzes().some((q) => Number(q.pack_id) === p.id)) p.mine = true;
    // playable packs first (packs without quiz questions stay visible but disabled, at the end)
    setup.packs = [...mine, ...list].sort((a, b) => Number(playable(b)) - Number(playable(a)));
  } catch (err) {
    showError(err.status === 404 ? new Error(t('class_api_missing')) : err);
  }
  applyUrlParams();
  if (!setup.packs.some((p) => p.id === setup.packId && playable(p))) {
    const first = setup.packs.find(playable);
    setup.packId = first ? first.id : null;
  }
  if (setup.savedId && !setup.classrooms.some((c) => String(c.id) === String(setup.savedId))) { setup.savedId = ''; setup.classroom = null; }
  show('setup');
  renderSetup();
  checkResume();
}
const playable = (p) => p && (p.mine || quizCount(p) > 0);

/** One-time preselection from /host "Teacher presents": ?pack=<id>&grouping=individual|teams&school=<name>. */
function applyUrlParams() {
  if (paramsApplied) return;
  paramsApplied = true;
  const g = URLP.get('grouping');
  if (g === 'individual' || g === 'teams') setup.grouping = g;
  const pid = Number(URLP.get('pack'));
  if (Number.isInteger(pid) && pid > 0) {
    // a teacher quiz from another device is unlisted without its key: keep it selectable by id
    if (!setup.packs.some((p) => p.id === pid)) setup.packs.unshift({ id: pid, name: `Quiz #${pid}`, topic: 'mine', mine: true, question_counts: null });
    setup.packId = pid;
  }
  const school = normText(URLP.get('school')).slice(0, 200);
  if (school && !setup.savedId) { $('#cr-school').value = school; $('#cr-school-card').dataset.touched = '1'; }
}

// ---- grouping switch (Individuals | Groups) + number of questions (individual)
function renderGrouping() {
  const ind = setup.grouping === 'individual';
  for (const b of $$('#grouping-switch .seg-btn')) {
    const on = b.dataset.grouping === setup.grouping;
    b.setAttribute('aria-checked', String(on)); b.tabIndex = on ? 0 : -1;
  }
  $('#qc-card').hidden = !ind;
  $('#size-card').hidden = ind;
  const title = $('#setup-title'); title.dataset.i18n = ind ? 'setup_title_ind' : 'setup_title'; title.textContent = t(title.dataset.i18n);
  const btn = $('#wz-next'); btn.dataset.i18n = ind ? 'start_ind' : 'start_game'; btn.dataset.icon = ind ? 'play' : 'users';
  if (!btn.disabled) setLabel(btn, t(btn.dataset.i18n));
  syncMode(); renderKeys();
}
function setGrouping(g) {
  if (g === setup.grouping) return;
  setup.grouping = g; sfx.click();
  renderGrouping(); renderNames(); setTip('s1');
}
function renderQc() {
  const group = $('#qc-group');
  const focused = document.activeElement && group.contains(document.activeElement);
  group.replaceChildren(...QC_OPTIONS.map((n) => h('button', {
    type: 'button', role: 'radio', class: 'seg-btn', 'aria-checked': String(n === setup.questionCount), tabindex: n === setup.questionCount ? '0' : '-1', 'data-n': n,
    onclick: () => { setup.questionCount = n; sfx.click(); renderQc(); },
  }, String(n))));
  if (focused) { const b = $('[aria-checked="true"]', group); if (b) b.focus(); }
  radioKeys(group, (btn) => { setup.questionCount = Number(btn.dataset.n); renderQc(); });
  const n = presentNames().length;
  const q = setup.questionCount;
  $('#qc-summary').textContent = t('qc_summary', { q, n, per: n ? (Math.round((q / n) * 10) / 10).toLocaleString(LOCALE[lang]) : 0 });
  const adv = $('#qc-advice');
  const pack = setup.packs.find((p) => p.id === setup.packId);
  const avail = pack ? quizCount(pack) : null;
  const msgs = [];
  if (n > 60) msgs.push(t('too_many', { n }));
  else if (n && q < n) msgs.push(t('qc_short', { q, n }));
  if (avail !== null && avail > 0 && avail < q) msgs.push(t('qc_repeat', { avail }));
  if (!n) adv.hidden = true;
  else if (msgs.length) { adv.hidden = false; adv.className = 'banner banner-warning'; adv.textContent = msgs.join(' '); }
  else { adv.hidden = false; adv.className = 'banner'; adv.textContent = t('qc_ok'); }
  updateHint();
}

function renderSetup() {
  // saved classes
  const wrap = $('#saved-class-wrap');
  wrap.hidden = !setup.classrooms.length;
  $('#saved-class').replaceChildren(h('option', { value: '' }, t('new_class_opt')),
    ...setup.classrooms.map((c) => h('option', { value: c.id, selected: String(c.id) === String(setup.savedId) }, t('saved_opt', { name: c.name, n: n0(c.student_count) }))));
  renderPacks();
  renderSchool();
  renderGrouping();
  renderNames();
  setTip('s1');
}

const normText = (v) => String(v || '').replace(/\s+/g, ' ').trim();
function lsJson(key) {
  const v = lsGet(key);
  if (!v) return null;
  try { return JSON.parse(v); } catch (err) { warnOnce(`stored value is not JSON (${key})`, err); return null; }
}
function savedSchool() { const v = lsJson(LS_SCHOOL); return normText(v && typeof v === 'object' ? v.school : ''); }
function savedSchools() { const v = lsJson(LS_SCHOOLS); return Array.isArray(v) ? v.filter((x) => typeof x === 'string' && x.trim()) : []; }
function rememberSchool(school) {
  lsSet(LS_SCHOOL, JSON.stringify({ school }));
  lsSet(LS_SCHOOLS, JSON.stringify([school, ...savedSchools().filter((x) => x.toLowerCase() !== school.toLowerCase())].slice(0, 20)));
}
function schoolValue() { return normText(($('#cr-school') || {}).value); }
/** "Your school" card: School is required for a NEW class and remembered; a saved class shows its own school (read-only). */
function renderSchool(editing) {
  const card = $('#cr-school-card');
  if (!card) return;
  const fromClass = !!(setup.savedId && setup.classroom);
  if (fromClass) card.dataset.touched = '0';
  const typed = card.dataset.touched === '1' ? schoolValue() : null;
  const school = fromClass ? normText(setup.classroom.school) : typed ?? savedSchool();
  $('#dl-cr-schools').replaceChildren(...savedSchools().map((x) => h('option', { value: x })));
  $('#cr-school').value = school;
  $('#cr-school').disabled = fromClass;
  if (editing === undefined) editing = !fromClass && (card.dataset.editing === '1' || !school);
  if (fromClass && !school) editing = true;
  card.dataset.editing = editing ? '1' : '0';
  $('#cr-school-fields').hidden = !editing;
  $('#cr-school-summary').hidden = editing;
  const ch = $('#cr-school-change');
  ch.hidden = editing || fromClass || !school;
  ch.setAttribute('aria-expanded', String(!!editing));
  ch.setAttribute('aria-label', `${t('change')}: ${t('your_school')}`);
  $('#cr-school-note').textContent = fromClass ? t('school_from_class') : t('school_saved');
  if (school) $('#cr-school-summary').replaceChildren(icon('school'), h('strong', {}, school));
  $('#cr-school-err').textContent = '';
}
function schoolProblem() { return !setup.savedId && !schoolValue() ? t('need_school') : ''; }
function onSchoolInput() {
  $('#cr-school-card').dataset.touched = '1';
  $('#cr-school-err').textContent = ''; $('#cr-school').removeAttribute('aria-invalid');
  updateHint();
}
function showSchoolErrors() {
  renderSchool(true);
  $('#cr-school-err').textContent = t('need_school'); $('#cr-school').setAttribute('aria-invalid', 'true'); $('#cr-school').focus();
}

function renderPacks() {
  const list = $('#pack-list');
  list.replaceChildren();
  if (!setup.packs.some(playable)) list.append(h('p', { class: 'banner' }, t('no_packs')));
  const tabId = setup.packId ?? (setup.packs.find(playable) || {}).id;
  for (const p of setup.packs) {
    const sel = p.id === setup.packId;
    const n = quizCount(p);
    const ok = playable(p);
    const topic = p.mine ? 'mine' : p.topic === 'ai' ? 'ai' : 'general';
    const card = h('div', { class: `pack-card topic-${topic}${sel ? ' is-selected' : ''}${ok ? '' : ' is-disabled'}` },
      h('button', {
        type: 'button', role: 'radio', class: 'pack-pick', 'aria-checked': String(sel), 'data-id': p.id, tabindex: p.id === tabId ? '0' : '-1',
        'aria-disabled': ok ? null : 'true',
        onclick: () => { if (!ok) return; sfx.click(); setup.packId = p.id; renderPacks(); updateHint(); if (setup.grouping === 'individual') renderQc(); $(`#pack-list [data-id="${p.id}"]`).focus(); },
      },
        h('span', { class: 'pack-head' },
          h('span', { class: `topic-badge topic-badge-${topic}` }, topic === 'ai' ? `🤖 ${t('topic_ai')}` : topic === 'mine' ? '✏️ My quiz' : `🌏 ${t('topic_general')}`),
          n !== null ? h('span', { class: 'badge' }, ok ? t('q_count', { n }) : t('no_quiz')) : null),
        h('span', { class: 'pack-name' }, p.name),
        p.description ? h('span', { class: 'pack-desc' }, p.description) : null));
    if (p.why_it_matters) {
      card.append(h('details', { class: 'why-box' }, h('summary', {}, `💡 ${t('why_teach')}`), h('p', { tabindex: '0' }, p.why_it_matters)));
    }
    list.append(card);
  }
  radioKeys(list, (btn) => { setup.packId = Number(btn.dataset.id); renderPacks(); updateHint(); if (setup.grouping === 'individual') renderQc(); $(`#pack-list [data-id="${btn.dataset.id}"]`).focus(); });
}

/** Arrow-key navigation for a role=radiogroup of buttons (roving tabindex). */
function radioKeys(group, onSelect) {
  group.onkeydown = (e) => {
    const items = $$('[role="radio"]:not([aria-disabled="true"])', group);
    const i = items.indexOf(document.activeElement);
    if (i < 0) return;
    let j = null;
    if (e.key === 'ArrowDown' || e.key === 'ArrowRight') j = (i + 1) % items.length;
    else if (e.key === 'ArrowUp' || e.key === 'ArrowLeft') j = (i - 1 + items.length) % items.length;
    if (j === null) return;
    e.preventDefault();
    items[j].focus();
    onSelect(items[j]);
  };
}

function parseNames() {
  const seen = new Set(); const out = [];
  for (const raw of $('#paste-names').value.split(/\r?\n/)) {
    const n = raw.replace(/\s+/g, ' ').trim().slice(0, 100);
    if (!n || seen.has(n.toLowerCase())) continue;
    seen.add(n.toLowerCase()); out.push(n);
  }
  return out;
}
const presentNames = () => parseNames().filter((n) => !setup.absent.has(n.toLowerCase()));

function renderNames() {
  const names = parseNames();
  for (const a of [...setup.absent]) if (!names.some((n) => n.toLowerCase() === a)) setup.absent.delete(a);
  $('#names-count').textContent = t('names_count', { n: names.length });
  const list = $('#attend-list');
  list.replaceChildren(...names.map((n) => {
    const on = !setup.absent.has(n.toLowerCase());
    return h('button', {
      type: 'button', class: `attend-chip${on ? ' is-present' : ''}`, 'aria-pressed': String(on), 'data-name': n,
      onclick: () => { const k = n.toLowerCase(); if (setup.absent.has(k)) setup.absent.delete(k); else setup.absent.add(k); sfx.click(); renderNames(); const b = $(`#attend-list [data-name="${CSS.escape(n)}"]`); if (b) b.focus(); },
    }, h('span', { class: 'attend-mark', 'aria-hidden': 'true' }, on ? '✓' : '✕'), n, h('span', { class: 'sr-only' }, ` (${on ? t('present') : t('absent')})`));
  }));
  $('#absent-summary').textContent = setup.absent.size ? t('whos_absent_n', { n: setup.absent.size }) : t('whos_absent');
  renderSize();
  if (setup.grouping === 'individual') renderQc();
}

function suggestedRounds(n, teams) { return Math.max(1, Math.min(10, Math.ceil(n / Math.max(1, teams)))); }
function renderSize() {
  const n = presentNames().length;
  if (!setup.teamCountTouched) setup.teamCount = Math.max(2, Math.min(4, n || 2));
  setup.teamCount = Math.max(2, Math.min(6, setup.teamCount));
  if (!setup.roundsTouched) setup.rounds = Math.max(3, Math.min(10, suggestedRounds(n, setup.teamCount)));
  $('#tc-val').textContent = String(setup.teamCount);
  $('#rd-val').textContent = String(setup.rounds);
  $('#tc-minus').disabled = setup.teamCount <= 2; $('#tc-plus').disabled = setup.teamCount >= 6;
  $('#rd-minus').disabled = setup.rounds <= 1; $('#rd-plus').disabled = setup.rounds >= 10;
  $('#team-preview').replaceChildren(...TEAM_COLORS.slice(0, setup.teamCount).map((c, i) =>
    h('span', { class: 'team-dot', style: `--team:var(--team-${c})` }, h('img', { src: `/static/brand/mascots/${TEAM_MASCOT[c]}`, alt: '', width: '256', height: '256' }))));
  const turns = setup.teamCount * setup.rounds;
  $('#size-summary').textContent = t('size_summary', { teams: setup.teamCount, rounds: setup.rounds, turns, per: n ? Math.round(n / setup.teamCount) : 0 });
  const adv = $('#size-advice');
  adv.replaceChildren();
  if (n >= setup.teamCount) {
    adv.hidden = false;
    if (turns < n) {
      const r = suggestedRounds(n, setup.teamCount);
      adv.className = 'banner banner-warning';
      adv.append(h('span', {}, t('advice_short', { turns, present: n }), ' '));
      if (r > setup.rounds) adv.append(h('button', { type: 'button', class: 'btn btn-sm', onclick: () => { setup.rounds = r; setup.roundsTouched = true; renderSize(); } }, t('advice_fix', { r })));
    } else { adv.className = 'banner'; adv.textContent = t('advice_ok'); }
  } else adv.hidden = true;
  updateHint();
}

function setupProblem() {
  const sp = schoolProblem();
  if (sp) return sp;
  if (!setup.packs.some((p) => p.id === setup.packId && playable(p))) return t('need_pack');
  if (setup.grouping === 'individual') {
    const n = presentNames().length;
    return n < 1 ? t('need_names_ind') : n > 60 ? t('too_many', { n }) : '';
  }
  if (presentNames().length < Math.max(2, setup.teamCount)) return t('need_names', { n: Math.max(2, setup.teamCount) });
  return '';
}
function updateHint() {
  const p = setupProblem();
  $('#wz-hint').textContent = p;
  $('#wz-next').setAttribute('aria-disabled', p ? 'true' : 'false');
}

async function onSavedClass(e) {
  setup.savedId = e.target.value;
  setup.absent.clear();
  if (!setup.savedId) { setup.classroom = null; $('#paste-names').value = ''; renderSchool(); renderNames(); return; }
  try {
    setup.classroom = await api(`/api/class/classrooms/${encodeURIComponent(setup.savedId)}`);
    $('#paste-names').value = (setup.classroom.students || []).filter((s) => s.is_active !== false).map((s) => s.name).join('\n');
  } catch (err) { showError(err); }
  renderSchool(); renderNames();
}

async function startSession() {
  const p = setupProblem();
  if (p) { toast(p, 'info'); updateHint(); if (schoolProblem()) showSchoolErrors(); return; }
  const btn = $('#wz-next');
  const ind = setup.grouping === 'individual';
  btn.disabled = true;
  setLabel(btn, t(ind ? 'creating_ind' : 'creating'));
  try {
    const names = parseNames();
    let cls = setup.savedId ? setup.classroom : null;
    if (!cls) {
      const date = new Date().toLocaleString(LOCALE.en, { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
      const school = schoolValue();
      rememberSchool(school);
      $('#cr-school-card').dataset.editing = '0'; $('#cr-school-card').dataset.touched = '0';
      cls = await api('/api/class/classrooms', { method: 'POST', json: { name: I18N.en.class_auto.replace('{date}', date), school } });
    }
    await api(`/api/class/classrooms/${cls.id}/students`, { method: 'POST', json: { names } });
    const detail = await api(`/api/class/classrooms/${cls.id}`);
    setup.savedId = String(cls.id); setup.classroom = detail;
    const want = new Set(presentNames().map((n) => n.toLowerCase()));
    const present = (detail.students || []).filter((s) => s.is_active !== false && want.has(String(s.name).replace(/\s+/g, ' ').trim().toLowerCase())).map((s) => s.id);
    const s = await api('/api/class/sessions', {
      method: 'POST',
      json: ind
        ? { classroom_id: cls.id, pack_id: setup.packId, game_modes: [QUIZ], grouping: 'individual', question_count: setup.questionCount, present_student_ids: present }
        : { classroom_id: cls.id, pack_id: setup.packId, game_modes: [QUIZ], team_count: setup.teamCount, rounds: setup.rounds, present_student_ids: present },
    });
    game.session = s; game.finish = null; game.lastTurnNo = null;
    lsSet(LS_SESSION, s.id);
    sfx.whoosh();
    if (ind) goReady(); else goLobby();
  } catch (err) { showError(err); } finally { btn.disabled = false; setLabel(btn, t(ind ? 'start_ind' : 'start_game')); }
}

async function checkResume() {
  const banner = $('#resume-banner');
  banner.hidden = true;
  const id = lsGet(LS_SESSION);
  if (!id) return;
  try {
    const s = await api(`/api/class/sessions/${encodeURIComponent(id)}`);
    if (!s || s.status !== 'live') { lsDel(LS_SESSION); return; }
    const cls = (s.classroom && s.classroom.name) || '';
    const allDone = !s.next;
    banner.replaceChildren(...[
      h('span', { class: 'grow' }, allDone ? t('resume_done', { cls }) : t('resume_text', { cls, t: Math.min(s.current_turn, s.total_turns), tt: s.total_turns })),
      allDone ? null : h('button', { type: 'button', class: 'btn btn-primary btn-sm', onclick: () => { game.session = s; enterStage(); } }, t('resume_game')),
      h('button', { type: 'button', class: 'btn btn-sm', onclick: () => { game.session = s; finishGame(); } }, t('end_it'))].filter(Boolean));
    banner.hidden = false;
  } catch (err) {
    if (err && err.status === 404) lsDel(LS_SESSION);
    else warnOnce('could not check the running game (resume banner hidden)', err);
  }
}


// ================================================================= LOBBY
function goLobby() { game.moving = null; show('lobby'); renderLobby(); setTip('lobby'); }
function renderLobby() {
  const s = game.session;
  $('#lobby-sub').textContent = t('lobby_sub', { cls: (s.classroom && s.classroom.name) || '', pack: (s.pack && s.pack.name) || t('all_questions'), turns: s.total_turns });
  const wrap = $('#lobby-teams');
  wrap.replaceChildren();
  const moving = game.moving;
  const fromTeam = moving ? s.teams.find((tm) => tm.members.some((m) => m.student_id === moving)) : null;
  s.teams.forEach((tm, i) => {
    const members = tm.members.map((m) => h('li', {},
      h('button', {
        type: 'button', class: `member-chip${moving === m.student_id ? ' is-moving' : ''}`, 'aria-pressed': String(moving === m.student_id), 'data-id': m.student_id,
        onclick: () => pickToMove(m.student_id),
      }, m.name)));
    wrap.append(h('section', { class: `lobby-team${fromTeam && fromTeam.id !== tm.id ? ' is-target' : ''}`, style: teamStyle(tm, i), 'aria-label': teamName(tm) },
      h('div', { class: 'lobby-team-head' },
        teamMascot(tm, i, 'lobby-emoji'),
        h('span', {}, h('span', { class: 'lobby-team-name' }, teamName(tm)), h('span', { class: 'small lobby-count' }, t('members_n', { n: tm.members.length })))),
      h('ul', { class: 'member-list' }, members),
      fromTeam && fromTeam.id !== tm.id ? h('button', { type: 'button', class: 'btn btn-primary btn-sm move-here', onclick: () => moveTo(tm.id) }, t('move_here')) : null));
  });
  const hint = $('#lobby-move-hint');
  if (moving) {
    const m = fromTeam && fromTeam.members.find((x) => x.student_id === moving);
    hint.replaceChildren(t('moving', { name: m ? m.name : '' }), ' ', h('button', { type: 'button', class: 'btn btn-sm', onclick: () => { game.moving = null; renderLobby(); } }, t('move_cancel')));
  } else hint.textContent = t('lobby_hint');
}
function pickToMove(id) {
  sfx.click();
  game.moving = game.moving === id ? null : id;
  renderLobby();
  const target = game.moving ? $('#lobby-teams .move-here') : $(`#lobby-teams [data-id="${id}"]`);
  if (target) target.focus();
}
async function putTeams(teams) {
  try {
    game.session = await api(`/api/class/sessions/${encodeURIComponent(game.session.id)}/teams`, { method: 'PUT', json: { teams } });
  } catch (err) { showError(err.status === 409 ? new Error(t('teams_locked')) : err); }
  renderLobby();
}
async function moveTo(teamId) {
  const s = game.session;
  const id = game.moving;
  const from = s.teams.find((tm) => tm.members.some((m) => m.student_id === id));
  if (!from) return;
  if (from.members.length <= 1) { toast(t('keep_one'), 'info'); return; }
  const teams = s.teams.map((tm) => ({
    team_id: tm.id,
    student_ids: tm.id === from.id ? tm.members.map((m) => m.student_id).filter((x) => x !== id)
      : tm.id === teamId ? [...tm.members.map((m) => m.student_id), id] : tm.members.map((m) => m.student_id),
  }));
  game.moving = null;
  sfx.whoosh();
  await putTeams(teams);
  const b = $(`#lobby-teams [data-id="${id}"]`); if (b) b.focus();
}
async function shuffleTeams() {
  const s = game.session;
  const all = shuffle(s.teams.flatMap((tm) => tm.members.map((m) => m.student_id)));
  const teams = s.teams.map((tm, i) => ({ team_id: tm.id, student_ids: all.filter((_, k) => k % s.teams.length === i) }));
  game.moving = null;
  sfx.whoosh();
  await putTeams(teams);
  toast(t('shuffled'), 'success', 2000);
}

// ================================================================= READY (individuals: no teams, no shuffle)
function goReady() { show('ready'); renderReady(); setTip('readyscr'); }
function renderReady() {
  const s = game.session;
  $('#ready-sub').textContent = t('ready_sub', { cls: (s.classroom && s.classroom.name) || '', pack: (s.pack && s.pack.name) || t('all_questions'), q: s.total_turns });
  const studs = allStudents();
  $('#ready-list-title').textContent = t('ready_players', { n: studs.length });
  $('#ready-list').replaceChildren(...studs.map((x) => h('li', { class: 'ready-chip', style: teamStyle(x.team, x.idx), 'data-id': x.student_id },
    teamMascot(x.team, x.idx, 'ready-mascot'), h('span', {}, x.name))));
}

// ================================================================= "+ Add student" (late arrivals, both groupings)
/** Move the widget into the active screen's slot (stage: leaderboard head for individuals, control panel for teams). */
function placeAddStudent() {
  const box = $('#add-stu');
  if (!box) return;
  const live = game.session && game.session.status === 'live';
  const slot = !live ? null : screen === 'stage' ? $(sessInd() ? '#lb-panel .add-slot' : '#control-panel .add-slot') : (screen === 'lobby' || screen === 'ready') ? $(`#scr-${screen} .add-slot`) : null;
  closeAddForm({ focus: false });
  if (!slot) { box.hidden = true; return; }
  if (box.parentElement !== slot) slot.append(box);
  box.hidden = false;
}
function openAddForm() {
  $('#add-stu-btn').hidden = true; $('#add-stu-btn').setAttribute('aria-expanded', 'true');
  $('#add-stu-form').hidden = false;
  $('#add-stu').classList.add('is-open');
  $('#add-stu-name').focus();
}
function closeAddForm({ focus = true } = {}) {
  const form = $('#add-stu-form');
  if (!form || form.hidden) return;
  form.hidden = true; $('#add-stu-name').value = '';
  $('#add-stu').classList.remove('is-open');
  const b = $('#add-stu-btn'); b.hidden = false; b.setAttribute('aria-expanded', 'false');
  if (focus) b.focus();
}
let adding = false;
async function submitAddStudent(e) {
  e.preventDefault();
  const name = normText($('#add-stu-name').value).slice(0, 100);
  if (!name || adding || !game.session) { $('#add-stu-name').focus(); return; }
  adding = true; $('#add-stu-save').disabled = true;
  try {
    const r = await api(`/api/class/sessions/${encodeURIComponent(game.session.id)}/students`, { method: 'POST', json: { names: [name] } });
    if (r && r.state) game.session = r.state;
    const added = (r && r.added) || [];
    if (added.length) {
      sfx.coin();
      let msg;
      if (sessInd()) msg = t('added', { names: added.map((a) => a.name).join(', ') });
      else { const tm = teamById(added[0].team_id); msg = t('added_team', { name: added[0].name, team: tm ? teamName(tm) : '' }); }
      toast(msg, 'success', 3500); announce(msg);
    }
    if (r && r.skipped && r.skipped.length) toast(t('add_skipped', { names: r.skipped.join(', ') }), 'info', 4000);
    $('#add-stu-name').value = '';
    afterRosterChange();
  } catch (err) { showError(err); } finally { adding = false; $('#add-stu-save').disabled = false; $('#add-stu-name').focus(); }
}
function afterRosterChange() {
  if (screen === 'lobby') renderLobby();
  else if (screen === 'ready') renderReady();
  else if (screen === 'stage') {
    const tu = curTurn();
    if (!tu) return;
    if (sessInd()) {
      const s = game.session;
      const sug = s.next && s.next.turn_no === tu.turn_no ? s.next.suggested_student_id : null;
      if (game.phase === 'ready' && !game.manualPick && sug) game.speakerId = sug;  // a newcomer (0 turns) may be the fairest pick now
      renderLeaderboard();
      if (game.phase === 'ready') { renderWho(); setPhase('ready'); }
    } else {
      renderScoreboard();
      if (game.phase === 'ready') renderPicker(teamById(tu.team_id));
    }
  }
}

// ================================================================= 2. STAGE (team quiz turns)
const timer = { raf: 0, limit: 20, elapsed: 0, last: 0, paused: false, up: false };
const RING_C = 2 * Math.PI * 86;
let judgeTick = 0;

function curTurn() {
  const s = game.session;
  return s && s.turns ? s.turns.find((x) => x.turn_no === s.current_turn) : null;
}
function teamById(id) { return game.session.teams.find((tm) => tm.id === id); }
function teamIndex(id) { return game.session.teams.findIndex((tm) => tm.id === id); }
/** Individual sessions: one team row per student → flat student list {student_id, name, turns_spoken, team, idx}. */
function allStudents() {
  const s = game.session;
  if (!s || !Array.isArray(s.teams)) return [];
  return s.teams.flatMap((tm, idx) => (tm.members || []).map((m) => ({ ...m, team: tm, idx })));
}
function studentById(id) { return allStudents().find((x) => x.student_id === id) || null; }
function suggestedId() { const s = game.session; return s && s.next && s.next.turn_no === s.current_turn ? s.next.suggested_student_id : null; }
/** Fairest order: the server's suggestion first, then fewest turns, then the (shuffled) seat order. */
function queueOrder() {
  const sug = suggestedId();
  return allStudents().sort((a, b) => (Number(b.student_id === sug) - Number(a.student_id === sug))
    || ((n0(a.turns_spoken)) - (n0(b.turns_spoken))) || (a.team.position - b.team.position));
}

function enterStage() {
  const s = game.session;
  if (!s) return goSetup();
  if (s.status !== 'live' || !s.next || !curTurn()) return finishGame();
  sfx.unlock();
  show('stage');
  prepareTurn();
  renderStage({ intro: true });
}

function prepareTurn() {
  const s = game.session;
  const tu = curTurn();
  if (game.lastTurnNo === s.current_turn) return;
  game.lastTurnNo = s.current_turn;
  game.lastResult = null; game.lastChoice = null;
  game.attemptsUsed = tu && tu.attempts_used != null ? Number(tu.attempts_used) : (tu && tu.student_id && tu.status === 'pending' ? 1 : 0);
  if (sessInd()) {
    game.manualPick = false;
    const search = $('#who-search'); if (search) search.value = '';
    const ids = allStudents().map((x) => x.student_id);
    const sug = suggestedId();
    game.speakerId = game.attemptsUsed && ids.includes(tu.student_id) ? tu.student_id : ids.includes(sug) ? sug : ids[0];
    game.phase = game.attemptsUsed ? 'result' : 'ready';
    resetTimer(tu.question);
    return;
  }
  const team = teamById(tu.team_id);
  const suggested = s.next && s.next.turn_no === tu.turn_no ? s.next.suggested_student_id : null;
  const ids = team.members.map((m) => m.student_id);
  game.speakerId = ids.includes(tu.student_id) ? tu.student_id : ids.includes(suggested) ? suggested : ids[0];
  game.phase = game.attemptsUsed ? 'result' : 'ready';
  resetTimer(tu.question);
}

function speakerName() {
  const tu = curTurn(); if (!tu) return '';
  if (sessInd()) { const x = studentById(game.speakerId); return x ? x.name : ''; }
  const m = teamById(tu.team_id).members.find((x) => x.student_id === game.speakerId);
  return m ? m.name : '';
}

function renderStage({ intro = false } = {}) {
  const s = game.session;
  const tu = curTurn();
  if (!tu) return;
  const ind = sessInd();
  $('#scoreboard').hidden = ind; $('#turn-banner').hidden = ind; $('#lb-panel').hidden = !ind;
  if (ind) {
    const prog = t('q_progress', { t: s.current_turn, tt: s.total_turns });
    $('#stage-title').textContent = prog; $('#top-progress').textContent = prog;
    renderLeaderboard();
    renderWho();
    renderQuestion(tu.question);
    if (game.phase === 'result') renderResult(game.lastResult, { animate: false });
    else $('#result-stage').hidden = true;
    setPhase(game.phase);
    if (intro) {
      announce(`${t('ind_turn_plain', { name: speakerName() })} ${tu.question.prompt || ''}`);
      sfx.whoosh();
      if (game.phase === 'ready') startTimer();
    }
    return;
  }
  const team = teamById(tu.team_id);
  const nTeams = s.teams.length;
  const prog = t('round_turn', { r: Math.floor((s.current_turn - 1) / nTeams) + 1, rt: Math.ceil(s.total_turns / nTeams), t: s.current_turn, tt: s.total_turns });
  $('#stage-title').textContent = prog;
  $('#top-progress').textContent = prog;
  renderScoreboard();
  renderBanner(team, intro);
  renderPicker(team);
  renderQuestion(tu.question);
  if (game.phase === 'result') renderResult(game.lastResult, { animate: false });
  else $('#result-stage').hidden = true;
  setPhase(game.phase);
  if (intro) {
    announce(`${t('team_turn_plain', { team: teamName(team), name: speakerName() })} ${tu.question.prompt || ''}`);
    sfx.whoosh();
    if (game.phase === 'ready') startTimer();
  }
}

function renderScoreboard({ bumpTeam = null } = {}) {
  const s = game.session;
  const tu = curTurn();
  const max = Math.max(1, ...s.teams.map((tm) => n0(tm.score)));
  const ol = $('#scoreboard');
  const existing = new Map($$('.sb-team', ol).map((li) => [Number(li.dataset.id), li]));
  s.teams.forEach((tm, i) => {
    let li = existing.get(tm.id);
    if (!li) {
      li = h('li', { class: 'sb-team', 'data-id': tm.id, style: teamStyle(tm, i) },
        teamMascot(tm, i, 'sb-emoji'),
        h('span', { class: 'sb-meta' }, h('span', { class: 'sb-name' }), h('span', { class: 'sb-flames', 'aria-hidden': 'true' })),
        h('span', { class: 'sb-score', 'aria-hidden': 'true' }, fmtInt(tm.score)),
        h('span', { class: 'sb-bar', 'aria-hidden': 'true' }, h('i')),
        h('span', { class: 'sr-only sb-sr' }));
      li.dataset.score = String(n0(tm.score));
      ol.append(li);
    }
    const current = tu && tu.team_id === tm.id && s.status === 'live';
    li.classList.toggle('is-current', !!current);
    if (current) li.setAttribute('aria-current', 'true'); else li.removeAttribute('aria-current');
    $('.sb-name', li).textContent = teamName(tm);
    const streak = n0(tm.streak);
    $('.sb-flames', li).textContent = streak > 0 ? `${'🔥'.repeat(Math.min(3, streak))}${streak > 3 ? ` x${streak}` : ''}` : '';
    li.classList.toggle('is-hot', streak >= 2);
    $('.sb-bar i', li).style.width = `${Math.round((n0(tm.score) / max) * 100)}%`;
    $('.sb-sr', li).textContent = `${t('score_aria', { team: teamName(tm), score: n0(tm.score), streak })}${current ? ` (${t('current_team')})` : ''}`;
    const scoreEl = $('.sb-score', li);
    const from = n0(li.dataset.score);
    const to = n0(tm.score);
    if (from !== to && bumpTeam === tm.id) countTo(scoreEl, from, to, 900);
    else scoreEl.textContent = fmtInt(to);
    li.dataset.score = String(to);
  });
}

function countTo(el, from, to, ms) {
  if (reducedMotion) { el.textContent = fmtInt(to); return; }
  el.classList.remove('bump'); void el.offsetWidth; el.classList.add('bump');
  const t0 = performance.now();
  const step = (now) => {
    const p = Math.min(1, (now - t0) / ms);
    el.textContent = fmtInt(Math.round(from + (to - from) * (1 - Math.pow(1 - p, 3))));
    if (p < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

function renderBanner(team, intro) {
  const b = $('#turn-banner');
  b.setAttribute('style', teamStyle(team, teamIndex(team.id)));
  const name = speakerName();
  const parts = t('team_turn', { emoji: '\u0000', team: '\u0001', name: '\u0002' }).split(/(\u0000|\u0001|\u0002)/);
  b.replaceChildren(...parts.map((p) => p === '\u0000' ? teamMascot(team, game.session && Array.isArray(game.session.teams) ? game.session.teams.findIndex((x) => x.id === team.id) : 0, 'tb-emoji')
    : p === '\u0001' ? h('span', { class: 'tb-team' }, teamName(team))
      : p === '\u0002' ? h('span', { class: 'tb-name' }, name) : p));
  if (intro && !reducedMotion) { b.classList.remove('enter'); void b.offsetWidth; b.classList.add('enter'); }
}

function renderPicker(team) {
  const wrap = $('#speaker-picker');
  const s = game.session;
  const suggested = s.next && s.next.turn_no === s.current_turn ? s.next.suggested_student_id : null;
  const tabId = team.members.some((m) => m.student_id === game.speakerId) ? game.speakerId : (team.members[0] || {}).student_id;
  wrap.replaceChildren(h('span', { class: 'picker-label', id: 'speaker-label' }, `👑 ${t('captain')}`, h('span', { class: 'kbd', 'aria-hidden': 'true' }, 'C')),
    ...team.members.map((m) => {
      const sel = m.student_id === game.speakerId;
      return h('button', {
        type: 'button', role: 'radio', class: 'speaker-chip', 'aria-checked': String(sel), 'data-id': m.student_id, tabindex: m.student_id === tabId ? '0' : '-1',
        onclick: () => chooseSpeaker(m.student_id),
      },
        h('span', { class: 'sp-name' }, m.name),
        m.student_id === suggested ? h('span', { class: 'sp-star', title: t('suggested') }, '⭐', h('span', { class: 'sr-only' }, ` (${t('suggested')})`)) : null,
        h('span', { class: 'sp-turns', title: t('captain_times', { n: n0(m.turns_spoken) }) }, `👑${n0(m.turns_spoken)}`, h('span', { class: 'sr-only' }, ` ${t('captain_times', { n: n0(m.turns_spoken) })}`)));
    }));
  radioKeys(wrap, (btn) => chooseSpeaker(Number(btn.dataset.id)));
}

function chooseSpeaker(id) {
  if (game.phase !== 'ready') return;
  const team = teamById(curTurn().team_id);
  if (!team.members.some((m) => m.student_id === id)) return;
  sfx.click();
  const hadFocus = document.activeElement && document.activeElement.closest('#speaker-picker');
  game.speakerId = id;
  renderPicker(team);
  renderBanner(team, false);
  setPhase('ready');
  announce(t('team_turn_plain', { team: teamName(team), name: speakerName() }));
  if (hadFocus) { const b = $(`#speaker-picker [data-id="${id}"]`); if (b) b.focus(); }
}
function cycleCaptain() {
  if (game.phase !== 'ready') return;
  if (sessInd()) {
    const order = queueOrder().map((x) => x.student_id);
    if (order.length < 2) return;
    chooseStudent(order[(order.indexOf(game.speakerId) + 1) % order.length]);
    return;
  }
  const ids = teamById(curTurn().team_id).members.map((m) => m.student_id);
  if (ids.length < 2) return;
  chooseSpeaker(ids[(ids.indexOf(game.speakerId) + 1) % ids.length]);
}

// ---- individual: "Who's answering?" picker (suggested student preselected; click, type to filter, C cycles)
function renderWho() {
  const wrap = $('#who-list');
  const q = normText($('#who-search').value).toLowerCase();
  const sug = suggestedId();
  const order = queueOrder();
  const sel = order.find((x) => x.student_id === game.speakerId);
  let rest = order.filter((x) => x !== sel);
  if (q) rest = rest.filter((x) => x.name.toLowerCase().includes(q));
  const shown = [sel, ...rest.slice(0, q ? 5 : 3)].filter(Boolean);   // one row on a projector; the search box finds the rest
  const hadFocus = document.activeElement && wrap.contains(document.activeElement) ? Number(document.activeElement.dataset.id) : null;
  wrap.replaceChildren(...shown.map((x) => {
    const on = x.student_id === game.speakerId;
    return h('button', {
      type: 'button', role: 'radio', class: `speaker-chip who-chip${on ? ' is-selected' : ''}`, 'aria-checked': String(on), 'data-id': x.student_id,
      tabindex: on ? '0' : '-1', style: teamStyle(x.team, x.idx), onclick: () => chooseStudent(x.student_id, { fromSearch: !!q }),
    },
      teamMascot(x.team, x.idx, 'who-mascot'),
      h('span', { class: 'sp-name' }, x.name),
      x.student_id === sug ? h('span', { class: 'sp-star', title: t('suggested') }, '⭐', h('span', { class: 'sr-only' }, ` (${t('suggested')})`)) : null,
      h('span', { class: 'sp-turns', title: t('turns_n', { n: n0(x.turns_spoken) }) }, `${n0(x.turns_spoken)}×`, h('span', { class: 'sr-only' }, ` ${t('turns_n', { n: n0(x.turns_spoken) })}`)));
  }), ...(q && !rest.length ? [h('span', { class: 'who-none' }, t('who_none', { q: $('#who-search').value.trim() }))] : []));
  $('#who-count').textContent = q ? (rest.length ? t('who_matches', { n: rest.length }) : t('who_none', { q: $('#who-search').value.trim() })) : '';
  radioKeys(wrap, (btn) => chooseStudent(Number(btn.dataset.id)));
  if (hadFocus) { const b = $(`[data-id="${hadFocus}"]`, wrap) || $('[aria-checked="true"]', wrap); if (b) b.focus(); }
}
function chooseStudent(id, { fromSearch = false } = {}) {
  if (game.phase !== 'ready' || !studentById(id)) return;
  sfx.click();
  game.speakerId = id;
  game.manualPick = id !== suggestedId();
  if (fromSearch) $('#who-search').value = '';
  const hadFocus = document.activeElement && document.activeElement.closest('#who-list');
  renderWho();
  renderLeaderboard();
  setPhase('ready');
  announce(t('ind_turn_plain', { name: speakerName() }));
  if (hadFocus || fromSearch) { const b = $(`#who-list [data-id="${id}"]`); if (b) b.focus(); }
}
function onWhoSearchKey(e) {
  if (e.key === 'Enter') {
    e.preventDefault();
    const q = normText(e.target.value).toLowerCase();
    if (!q) return;
    const hit = queueOrder().find((x) => x.student_id !== game.speakerId && x.name.toLowerCase().includes(q))
      || queueOrder().find((x) => x.name.toLowerCase().includes(q));
    if (hit) chooseStudent(hit.student_id, { fromSearch: true });
  } else if (e.key === 'Escape') {
    e.preventDefault();
    if (e.target.value) { e.target.value = ''; renderWho(); } else { const b = $('#who-list [aria-checked="true"]'); if (b) b.focus(); }
  }
}

// ---- individual: live leaderboard (top 10 + "+N more"), rank changes animated (FLIP)
function renderLeaderboard({ bump = null } = {}) {
  const s = game.session;
  const lb = (s && s.leaderboard) || { top: [], count: 0 };
  const ol = $('#lb-list');
  const old = new Map($$('.lb-row', ol).map((li) => [Number(li.dataset.id), li]));
  const before = new Map([...old].map(([id, li]) => [id, li.getBoundingClientRect().top]));
  const byTeam = new Map((s.teams || []).map((tm, i) => [tm.id, i]));
  const rows = (lb.top || []).map((e) => {
    let li = old.get(e.student_id);
    const idx = byTeam.get(e.team_id) ?? 0;
    if (!li) {
      li = h('li', { class: 'lb-row', 'data-id': e.student_id, style: teamStyle(e, idx) },
        h('span', { class: 'lb-rank' }), teamMascot(e, idx, 'lb-mascot'),
        h('span', { class: 'lb-name' }), h('span', { class: 'lb-flames', 'aria-hidden': 'true' }),
        h('span', { class: 'lb-score', 'aria-hidden': 'true' }, fmtInt(e.score)), h('span', { class: 'sr-only lb-sr' }));
      li.dataset.score = String(n0(e.score)); li.dataset.rank = String(e.rank);
    }
    const prevRank = Number(li.dataset.rank || e.rank);
    $('.lb-rank', li).textContent = String(e.rank);
    $('.lb-name', li).textContent = e.name;
    const streak = n0(e.streak);
    $('.lb-flames', li).textContent = streak > 1 ? `🔥${streak > 2 ? streak : ''}` : '';
    $('.lb-sr', li).textContent = t('lb_row', { rank: e.rank, name: e.name, score: n0(e.score) });
    li.classList.toggle('is-current', e.student_id === game.speakerId && s.status === 'live');
    li.classList.toggle('is-up', e.rank < prevRank);
    const scoreEl = $('.lb-score', li);
    const from = n0(li.dataset.score); const to = n0(e.score);
    if (from !== to && bump === e.student_id) countTo(scoreEl, from, to, 900); else scoreEl.textContent = fmtInt(to);
    li.dataset.score = String(to); li.dataset.rank = String(e.rank);
    return li;
  });
  ol.replaceChildren(...rows);
  if (!reducedMotion && ol.offsetParent) {
    for (const li of rows) {
      const id = Number(li.dataset.id);
      const top = li.getBoundingClientRect().top;
      if (!before.has(id)) { if (old.size) li.animate([{ opacity: 0, transform: 'translateX(-16px)' }, { opacity: 1, transform: 'none' }], { duration: 450, easing: 'ease-out' }); }
      else if (Math.abs(before.get(id) - top) > 1) li.animate([{ transform: `translateY(${before.get(id) - top}px)` }, { transform: 'none' }], { duration: 650, easing: 'cubic-bezier(.2,.8,.2,1)' });
    }
  }
  const more = Math.max(0, n0(lb.count) - rows.length);
  const m = $('#lb-more'); m.hidden = !more; m.textContent = more ? t('lb_more', { n: more }) : '';
}

function renderQuestion(q) {
  const box = $('#q-stage');
  box.dataset.mode = q.game_mode;
  const { emoji, text } = splitEmoji(q.prompt);
  const body = h('div', { class: 'q-body' });
  if (q.image_url) body.append(h('img', { class: 'q-image', src: q.image_url, alt: q.image_alt || '', onerror: (e) => e.currentTarget.remove() }));
  else if (emoji && text) body.append(h('div', { class: 'q-emoji q-emoji-sm', 'aria-hidden': 'true' }, emoji));
  body.append(h('p', { class: 'q-text fit' }, text || q.prompt || ''));
  const opts = Array.isArray(q.options) ? q.options.slice(0, 4) : [];
  const tiles = h('div', { class: `tiles tiles-${opts.length}`, role: 'group', 'aria-label': t('q_instr') },
    opts.map((o, i) => h('button', {
      type: 'button', class: `tile tile-${TILES[i].key}`, 'data-idx': i, 'aria-keyshortcuts': String(i + 1),
      'aria-label': t('answer_opt', { k: i + 1, text: o }), onclick: () => answer(i),
    },
      h('span', { class: 'tile-shape', 'aria-hidden': 'true' }, TILES[i].shape),
      h('span', { class: 'tile-text' }, o),
      h('span', { class: 'tile-key kbd', 'aria-hidden': 'true' }, String(i + 1)),
      h('span', { class: 'tile-who', 'aria-hidden': 'true' }),
      h('span', { class: 'tile-mark', 'aria-hidden': 'true' }))));
  const instr = sessInd() ? t('q_instr_ind') : t('q_instr');
  tiles.setAttribute('aria-label', instr);
  box.replaceChildren(h('div', { class: 'q-head' }, h('span', { class: 'q-instr' }, instr)), body, tiles);
  box.hidden = false;
  requestAnimationFrame(fitQuestion);
}

/** Shrink the question text until question + tiles fit (never below 48px — readable from the back). */
function fitQuestion() {
  const el = $('#q-stage .fit');
  const box = $('#q-stage');
  if (!el || !box || box.hidden) return;
  el.style.fontSize = '';
  let size = parseFloat(getComputedStyle(el).fontSize);
  let guard = 40;
  const body = el.parentElement;   // .q-body clips (overflow: hidden), so measure it as well as the whole box
  const over = () => box.scrollHeight > box.clientHeight + 1 || body.scrollHeight > body.clientHeight + 1 || el.scrollWidth > el.clientWidth + 1;
  while (guard-- > 0 && size > 48 && over()) {
    size = Math.max(48, size - 4);
    el.style.fontSize = `${size}px`;
  }
}

// ---- discussion timer (teacher can pause with P; never auto-answers)
function resetTimer(q) {
  cancelAnimationFrame(timer.raf);
  timer.limit = Math.max(5, Number((q && q.time_limit_sec) || 20));
  timer.elapsed = 0; timer.paused = false; timer.up = false;
  setRing(1, timer.limit);
}
function startTimer() {
  cancelAnimationFrame(timer.raf);
  timer.last = performance.now();
  const tick = (now) => {
    if (game.phase !== 'ready') return;
    if (!timer.paused) timer.elapsed += Math.max(0, now - timer.last);  // rAF time can precede performance.now()
    timer.last = now;
    const left = timer.limit - timer.elapsed / 1000;
    setRing(left / timer.limit, left);
    if (left <= 0 && !timer.up) {
      timer.up = true;
      sfx.buzz();
      setPhase('ready');
      announce(t(sessInd() ? 'time_up_ind' : 'time_up'));
      return;
    }
    if (left > 0) timer.raf = requestAnimationFrame(tick);
  };
  timer.raf = requestAnimationFrame(tick);
}
function togglePause() {
  if (game.phase !== 'ready' || timer.up) return;
  timer.paused = !timer.paused;
  timer.last = performance.now();
  sfx.click();
  setPhase('ready');
  announce(timer.paused ? t('paused') : t(sessInd() ? 'q_instr_ind' : 'q_instr'));
}
function setRing(fraction, secondsLeft) {
  const fg = $('#ring-fg');
  fg.style.strokeDasharray = `${RING_C}`;
  fg.style.strokeDashoffset = `${RING_C * (1 - Math.max(0, Math.min(1, fraction)))}`;
  const low = secondsLeft <= 5;
  $('#timer-wrap .timer-ring').classList.toggle('is-low', low);
  const tt = $('#timer-text');
  tt.classList.toggle('is-low', low);
  tt.textContent = fmtTime(secondsLeft);
}

function setPhase(phase) {
  game.phase = phase;
  const tu = curTurn();
  const team = tu ? teamById(tu.team_id) : null;
  document.body.dataset.phase = phase;
  const ready = phase === 'ready';
  const ind = sessInd();
  $('#speaker-picker').hidden = !ready || ind;
  $('#who-picker').hidden = !ready || !ind;
  for (const b of $$('#q-stage .tile')) b.disabled = !ready;
  const pause = $('#btn-pause');
  pause.hidden = !ready || timer.up;
  setLabel(pause, timer.paused ? t('resume') : t('pause'), timer.paused ? 'play' : 'pause');
  pause.setAttribute('aria-pressed', String(timer.paused));
  $('#timer-wrap').classList.toggle('is-paused', ready && timer.paused);
  $('#timer-wrap').hidden = phase === 'result';
  const skip = $('#btn-skip'); const next = $('#btn-next');
  skip.hidden = !(ready && game.attemptsUsed === 0);
  setLabel(skip, t('skip'), 'skip-forward');
  next.hidden = phase !== 'result';
  const isLast = game.session && game.session.current_turn >= game.session.total_turns;
  setLabel(next, isLast ? t('finish') : t('next_turn'), isLast ? 'flag' : 'arrow-right');
  const n = tu && Array.isArray(tu.question.options) ? tu.question.options.length : 4;
  const status = $('#rec-status');
  if (ready) status.textContent = timer.up ? t(ind ? 'time_up_ind' : 'time_up') : timer.paused ? t('paused') : ind ? t('discuss_ind', { n, name: speakerName() }) : t('discuss', { n });
  else if (phase === 'judging') status.textContent = t('locked_in');
  else status.textContent = game.lastResult ? '' : t('answered_already');
  const vars = { team: team ? teamName(team) : '', name: speakerName() };
  if (ready) setTip(timer.up ? 'timeup' : timer.paused ? 'paused' : 'ready', vars);
  else if (phase === 'judging') setTip('judge', vars);
  else setTip(game.lastResult && game.lastResult.passed ? 'good' : 'wrong', vars);
}

async function answer(idx) {
  if (game.phase !== 'ready' || game.attemptsUsed > 0) return;
  const tu = curTurn();
  const opts = tu.question.options || [];
  if (idx < 0 || idx >= opts.length) return;
  const s = game.session;
  cancelAnimationFrame(timer.raf);
  game.lastChoice = idx;
  const tile = $(`#q-stage .tile[data-idx="${idx}"]`);
  if (tile) tile.classList.add('is-chosen');
  setPhase('judging');
  sfx.click();
  if (!reducedMotion) judgeTick = setInterval(() => sfx.tick(), 110);
  const form = new FormData();
  form.append('student_id', String(game.speakerId));
  form.append('duration_ms', String(Math.max(0, Math.round(Math.min(timer.elapsed, timer.limit * 1000)))));
  form.append('choice', String(idx));
  try {
    const [r] = await Promise.all([
      api(`/api/class/sessions/${encodeURIComponent(s.id)}/turns/${tu.turn_no}/attempts`, { method: 'POST', form }),
      sleep(reducedMotion ? 0 : 1100), // drum roll suspense
    ]);
    clearInterval(judgeTick);
    game.session = r.state || game.session;
    game.lastTurnNo = game.session.current_turn;
    game.attemptsUsed = 1;
    game.lastResult = r;
    setPhase('result');
    renderResult(r, { animate: true });
  } catch (err) {
    clearInterval(judgeTick);
    if (tile) tile.classList.remove('is-chosen');
    if (err.status === 409) {
      try { game.session = await api(`/api/class/sessions/${encodeURIComponent(s.id)}`); } catch (e2) { console.warn('[classroom] reload after 409 failed; keeping the last state', e2); }
      if (game.session.status !== 'live' || !game.session.next) { finishGame(); return; }
      if (game.session.current_turn === tu.turn_no) { game.attemptsUsed = 1; setPhase('result'); renderResult(null, { animate: false }); }
      else { prepareTurn(); renderStage({ intro: true }); }
      showError(err);
      return;
    }
    setPhase('ready');
    startTimer();
    showError(err);
  }
}

function correctIndex(r) {
  const fb = (r && r.feedback) || {};
  for (const v of [fb.correct_option, r && r.correct_option]) if (Number.isInteger(v)) return v;
  if (fb.correct === true && Number.isInteger(fb.choice)) return fb.choice;
  return null;
}

function renderResult(r, { animate }) {
  const box = $('#result-stage');
  const tu = curTurn();
  const team = teamById(tu.team_id);
  const opts = tu.question.options || [];
  // tiles: mark the team's answer and the correct one
  const chosen = r && r.feedback && Number.isInteger(r.feedback.choice) ? r.feedback.choice : game.lastChoice;
  const correct = correctIndex(r);
  const ind = sessInd();
  const who = ind ? speakerName() : '';
  for (const b of $$('#q-stage .tile')) {
    const i = Number(b.dataset.idx);
    b.disabled = true;
    b.classList.toggle('is-chosen', i === chosen);
    b.classList.toggle('is-correct', i === correct);
    b.classList.toggle('is-wrong', i === chosen && r && !r.passed);
    b.classList.toggle('is-dim', i !== chosen && i !== correct);
    $('.tile-mark', b).textContent = i === correct ? '✓' : i === chosen && r && !r.passed ? '✕' : '';
    // individual: the student's name on the tile they picked ("Aisyah +100")
    const tw = $('.tile-who', b);
    if (tw) tw.textContent = ind && r && i === chosen ? (r.passed ? `${who} +${fmtInt(r.points)}` : who) : '';
  }
  if (!r) { box.hidden = true; return; }
  if (ind) { renderResultInd(r, { animate, correct, chosen, who, opts }); return; }
  const right = !!r.passed;
  const stars = Math.max(0, Math.min(3, n0(r.stars)));
  const mult = Number(r.streak_multiplier || 1);
  const speed = n0(r.speed_bonus);
  const pts = h('span', { class: 'res-points-num' }, animate ? '+0' : `+${fmtInt(r.points)}`);
  box.className = `result-stage ${right ? 'is-right' : 'is-wrong'}`;
  box.replaceChildren(...[
    h('span', { class: 'se-plate res-mascot', 'aria-hidden': 'true' }, h('img', { src: `/static/brand/mascots/${right ? 'pink' : 'purple'}-256.webp`, alt: '', width: '256', height: '256' })),
    right ? h('div', { class: `stars res-stars${animate ? '' : ' no-anim'}`, 'aria-hidden': 'true' }, [0, 1, 2].map((i) => h('span', { class: `star${i < stars ? ' is-on' : ''}` }, '★'))) : null,
    h('div', { class: 'res-headline' },
      h('p', { class: 'res-msg' }, right ? t('msg_right', { team: teamName(team) }) : t('msg_wrong', { team: teamName(team) })),
      right ? h('div', { class: 'res-points', 'aria-hidden': 'true' }, pts, h('span', { class: 'res-to-team' }, ` → ${teamName(team)}`))
        : correct !== null ? h('p', { class: 'res-answer' }, t('answer_was', { k: `${TILES[correct].shape} ${correct + 1}`, text: opts[correct] || '' }))
          : h('p', { class: 'res-answer is-team' }, t('your_answer', { k: `${TILES[chosen] ? TILES[chosen].shape : ''} ${chosen + 1}` }))),
    h('div', { class: 'res-chips' },
      mult > 1 && right ? h('span', { class: 'combo-banner', 'aria-hidden': 'true' }, h('span', {}, t('combo', { m: mult.toFixed(1) }))) : null,
      speed > 0 ? h('span', { class: 'speed-badge' }, t('fast', { n: fmtInt(speed) })) : null),
  ].filter(Boolean));
  box.hidden = false;
  box.classList.remove('reveal'); void box.offsetWidth;
  if (animate && !reducedMotion) box.classList.add('reveal');
  requestAnimationFrame(fitQuestion);
  if (!animate) { renderScoreboard(); return; }

  const score = (r.team && r.team.score) ?? team.score;
  announce(right ? t('result_aria_right', { team: teamName(team), points: n0(r.points), score }) : t('result_aria_wrong', { team: teamName(team), score }));
  $('#btn-next').focus({ preventScroll: true });
  const target = n0(r.points);
  if (reducedMotion || target <= 0) pts.textContent = `+${fmtInt(target)}`;
  else {
    const t0 = performance.now();
    const step = (now) => { const p = Math.min(1, (now - t0) / 900); pts.textContent = `+${fmtInt(Math.round(target * (1 - Math.pow(1 - p, 3))))}`; if (p < 1) requestAnimationFrame(step); };
    requestAnimationFrame(step);
  }
  if (!right) sfx.soft();
  else { for (let i = 0; i < stars; i++) sfx.star(i); setTimeout(() => sfx.coin(), 150 + stars * 280); }
  if (mult > 1 && right) sfx.combo();
  if (right && stars === 3) setTimeout(() => fx.burst(170), 500);
  const li = $(`#scoreboard .sb-team[data-id="${team.id}"]`);
  setTimeout(() => {
    if (target > 0) flyPoints(pts, li && $('.sb-score', li), `+${fmtInt(target)}`);
    setTimeout(() => renderScoreboard({ bumpTeam: team.id }), reducedMotion ? 0 : 750);
  }, reducedMotion ? 0 : 900);
}

function renderResultInd(r, { animate, correct, chosen, who, opts }) {
  const box = $('#result-stage');
  const right = !!r.passed;
  const stars = Math.max(0, Math.min(3, n0(r.stars)));
  const mult = Number(r.streak_multiplier || 1);
  const speed = n0(r.speed_bonus);
  const x = studentById(game.speakerId);
  const pts = h('span', { class: 'res-points-num' }, animate ? '+0' : `+${fmtInt(r.points)}`);
  box.className = `result-stage ${right ? 'is-right' : 'is-wrong'}`;
  box.replaceChildren(...[
    x ? teamMascot(x.team, x.idx, 'res-mascot') : null,
    right ? h('div', { class: `stars res-stars${animate ? '' : ' no-anim'}`, 'aria-hidden': 'true' }, [0, 1, 2].map((i) => h('span', { class: `star${i < stars ? ' is-on' : ''}` }, '★'))) : null,
    h('div', { class: 'res-headline' },
      h('p', { class: 'res-msg' }, right ? t('msg_right_ind', { name: who }) : t('msg_wrong_ind', { name: who })),
      right ? h('div', { class: 'res-points', 'aria-hidden': 'true' }, h('span', { class: 'res-who' }, who), ' ', pts)
        : correct !== null ? h('p', { class: 'res-answer' }, t('answer_was', { k: `${TILES[correct].shape} ${correct + 1}`, text: opts[correct] || '' }))
          : h('p', { class: 'res-answer is-team' }, t('your_answer', { k: `${TILES[chosen] ? TILES[chosen].shape : ''} ${chosen + 1}` }))),
    h('div', { class: 'res-chips' },
      mult > 1 && right ? h('span', { class: 'combo-banner', 'aria-hidden': 'true' }, h('span', {}, `🔥 x${mult.toFixed(1)}`)) : null,
      speed > 0 ? h('span', { class: 'speed-badge' }, t('fast', { n: fmtInt(speed) })) : null),
  ].filter(Boolean));
  box.hidden = false;
  box.classList.remove('reveal'); void box.offsetWidth;
  if (animate && !reducedMotion) box.classList.add('reveal');
  requestAnimationFrame(fitQuestion);
  if (!animate) { renderLeaderboard(); return; }
  const score = (r.team && r.team.score) ?? (x ? x.team.score : 0);
  announce(right ? t('result_aria_right_ind', { name: who, points: n0(r.points), score }) : t('result_aria_wrong_ind', { name: who, score }));
  $('#btn-next').focus({ preventScroll: true });
  const target = n0(r.points);
  if (reducedMotion || target <= 0) pts.textContent = `+${fmtInt(target)}`;
  else {
    const t0 = performance.now();
    const step = (now) => { const p = Math.min(1, (now - t0) / 900); pts.textContent = `+${fmtInt(Math.round(target * (1 - Math.pow(1 - p, 3))))}`; if (p < 1) requestAnimationFrame(step); };
    requestAnimationFrame(step);
  }
  if (!right) sfx.soft();
  else { for (let i = 0; i < stars; i++) sfx.star(i); setTimeout(() => sfx.coin(), 150 + stars * 280); }
  if (mult > 1 && right) sfx.combo();
  if (right && stars === 3) setTimeout(() => fx.burst(170), 500);
  const id = game.speakerId;
  setTimeout(() => {
    const row = $(`#lb-list .lb-row[data-id="${id}"] .lb-score`);
    if (target > 0 && row) flyPoints(pts, row, `+${fmtInt(target)}`);
    setTimeout(() => { if (screen === 'stage' && sessInd()) renderLeaderboard({ bump: id }); }, reducedMotion ? 0 : 750);
  }, reducedMotion ? 0 : 900);
}

function flyPoints(fromEl, toEl, text) {
  if (reducedMotion || !fromEl || !toEl || !fromEl.animate) return;
  const a = fromEl.getBoundingClientRect(); const b = toEl.getBoundingClientRect();
  const el = h('div', { class: 'fly-pts', 'aria-hidden': 'true' }, text);
  el.style.left = `${a.left + a.width / 2}px`; el.style.top = `${a.top + a.height / 2}px`;
  document.body.append(el);
  const dx = b.left + b.width / 2 - (a.left + a.width / 2);
  const dy = b.top + b.height / 2 - (a.top + a.height / 2);
  el.animate([
    { transform: 'translate(-50%, -50%) scale(1)', opacity: 1 },
    { transform: `translate(calc(-50% + ${dx * 0.5}px), calc(-50% + ${dy * 0.5 - 60}px)) scale(1.2)`, opacity: 1, offset: 0.5 },
    { transform: `translate(calc(-50% + ${dx}px), calc(-50% + ${dy}px)) scale(0.5)`, opacity: 0.2 },
  ], { duration: 750, easing: 'cubic-bezier(.45,0,.55,1)' }).finished.then(() => el.remove(), () => el.remove());
}

let advancing = false;
async function nextTurn() {
  if (advancing || $('#btn-next').hidden) return;
  advancing = true;
  sfx.click();
  const s = game.session;
  try {
    game.session = await api(`/api/class/sessions/${encodeURIComponent(s.id)}/turns/${s.current_turn}/next`, { method: 'POST', json: {} });
    afterAdvance();
  } catch (err) { showError(err); await resync(); } finally { advancing = false; }
}

async function skipTurn() {
  if (advancing || game.phase !== 'ready' || game.attemptsUsed > 0) return;
  advancing = true;
  const s = game.session;
  const tu = curTurn();
  const team = teamById(tu.team_id);
  const ind = sessInd();
  try {
    let st = await api(`/api/class/sessions/${encodeURIComponent(s.id)}/turns/${tu.turn_no}/skip`, { method: 'POST', json: { student_id: game.speakerId } });
    if (st && st.status === 'live' && st.current_turn === tu.turn_no) {
      st = await api(`/api/class/sessions/${encodeURIComponent(s.id)}/turns/${tu.turn_no}/next`, { method: 'POST', json: {} });
    }
    game.session = st;
    const msg = ind ? t('skipped_msg_ind') : t('skipped_msg', { team: teamName(team) });
    toast(msg, 'info', 3000);
    announce(msg);
    sfx.soft();
    afterAdvance({ keepTip: true });
  } catch (err) { showError(err); await resync(); } finally { advancing = false; }
}

function afterAdvance({ keepTip = false } = {}) {
  const s = game.session;
  if (s.status !== 'live' || !s.next || !curTurn()) { finishGame(); return; }
  prepareTurn();
  renderStage({ intro: true });
  if (keepTip) setTip('skip');
  const first = $('#q-stage .tile');
  if (first) first.focus({ preventScroll: true });
}
async function resync() {
  try { game.session = await api(`/api/class/sessions/${encodeURIComponent(game.session.id)}`); game.lastTurnNo = null; afterAdvance(); } catch (err) { console.warn('[classroom] resync failed; keeping the last state', err); }
}
function stopStage() { cancelAnimationFrame(timer.raf); clearInterval(judgeTick); }
function endGameEarly() {
  if (!window.confirm(t('end_confirm'))) return;
  stopStage();
  finishGame();
}


// ================================================================= 3. FINALE
async function finishGame() {
  const s = game.session;
  if (!s) return goSetup();
  stopStage();
  show('loading', { focus: false });
  let f;
  try {
    f = await api(`/api/class/sessions/${encodeURIComponent(s.id)}/finish`, { method: 'POST' });
  } catch (err) {
    // already finished (or finish not idempotent): build the finale from the session state
    try {
      const st = await api(`/api/class/sessions/${encodeURIComponent(s.id)}`);
      const ranked = [...st.teams].sort((a, b) => b.score - a.score);
      f = { state: st, ranking: ranked.map((tm, i) => ({ team_id: tm.id, student_id: tm.members && tm.members[0] ? tm.members[0].student_id : null, name: tm.name, emoji: tm.emoji, color: tm.color, score: tm.score, rank: i + 1 })), mvp: null, participation: { ...st.participation, students: [] } };
    } catch { showError(err); return goSetup(); }
  }
  lsDel(LS_SESSION);
  game.session = f.state || s;
  game.finish = f;
  show('finale');
  renderFinale(f, { celebrate: true });
}

function renderFinale(f, { celebrate }) {
  const st = f.state || game.session;
  const teams = st.teams || [];
  const ind = st.grouping === 'individual';
  const label = (tm, r) => (ind ? (r && r.name) || tm.name || '' : teamName(tm));
  const ranking = (f.ranking || []).slice().sort((a, b) => a.rank - b.rank);
  const byId = (id) => teams.find((tm) => tm.id === id) || {};
  const podium = $('#podium');
  const top = ranking.slice(0, 3);
  const order = [1, 0, 2].filter((i) => top[i]); // 2nd, 1st, 3rd
  podium.replaceChildren(...order.map((i) => {
    const r = top[i];
    const tm = { ...byId(r.team_id), ...r, id: r.team_id };
    return h('div', { class: `podium-col place-${r.rank}`, style: teamStyle(byId(r.team_id), teams.findIndex((x) => x.id === r.team_id)) },
      h('div', { class: 'podium-team' },
        teamMascot(tm, teams.findIndex((x) => x.id === r.team_id), 'podium-emoji'),
        h('span', { class: 'podium-name' }, label(tm, r)),
        h('span', { class: 'podium-score' }, `${fmtInt(r.score)} ${t('pts')}`)),
      h('div', { class: 'podium-block' }, h('span', { class: 'podium-rank' }, h('span', { 'aria-hidden': 'true' }, r.rank === 1 ? icon('trophy') : null, String(r.rank)), h('span', { class: 'sr-only' }, ` #${r.rank}`))));
  }));
  const mvpBox = $('#mvp');
  // individual: the podium already shows the best students → full ranking list instead of an MVP card
  const rankCard = $('#rank-card');
  rankCard.hidden = !ind;
  if (ind) {
    $('#rank-list').replaceChildren(...ranking.map((r) => {
      const tm = { ...byId(r.team_id), ...r, id: r.team_id };
      const idx = teams.findIndex((x) => x.id === r.team_id);
      return h('li', { class: `rank-row${r.rank <= 3 ? ` is-top place-${r.rank}` : ''}`, style: teamStyle(tm, idx) },
        h('span', { class: 'rank-no' }, String(r.rank)), teamMascot(tm, idx, 'rank-mascot'),
        h('span', { class: 'rank-name' }, r.name), h('span', { class: 'rank-score' }, `${fmtInt(r.score)} ${t('pts')}`));
    }));
  }
  if (f.mvp && !ind) {
    const tm = byId(f.mvp.team_id);
    mvpBox.hidden = false;
    mvpBox.setAttribute('style', teamStyle(tm, teams.findIndex((x) => x.id === f.mvp.team_id)));
    mvpBox.replaceChildren(h('span', { class: 'mvp-badge' }, `⭐ ${t('mvp')}`),
      h('span', { class: 'mvp-line' }, t('mvp_line', { name: f.mvp.name, emoji: '', team: teamName(tm), points: fmtInt(f.mvp.points) })));
  } else mvpBox.hidden = true;

  const p = f.participation || st.participation || {};
  const studs = Array.isArray(p.students) ? p.students : [];
  const present = Number(p.present ?? studs.filter((x) => x.present).length);
  const spoke = n0(p.spoke);
  const knownTotal = setup.classroom && setup.classroom.id === (st.classroom && st.classroom.id) ? (setup.classroom.students || []).filter((x) => x.is_active !== false).length : 0;
  const total = Math.max(present, studs.length, knownTotal);
  const rate = p.rate != null ? Math.round(Number(p.rate) * (Number(p.rate) <= 1 ? 100 : 1)) : (present ? Math.round((spoke / present) * 100) : 0);
  $('#part-summary').textContent = ind ? t('part_summary_ind', { present, spoke, rate }) : t('part_summary', { present, total, spoke, rate });
  const bar = $('#part-bar');
  bar.setAttribute('aria-valuenow', String(rate));
  bar.setAttribute('aria-label', t('part_rate'));
  bar.querySelector('i').style.width = `${rate}%`;
  const rows = studs.slice().sort((a, b) => (b.present - a.present) || (b.points - a.points) || String(a.name).localeCompare(String(b.name)));
  const teamLabel = (name) => { const tm = teams.find((x) => x.name === name); return tm ? teamName(tm) : (name || '—'); };
  const cols = ['col_student', 'col_team', 'col_present', 'col_turns', 'col_attempts', 'col_best', 'col_points'].filter((k) => !(ind && k === 'col_team'));
  $('#part-table').replaceChildren(
    h('thead', {}, h('tr', {}, cols.map((k, i) => h('th', { scope: 'col', class: i >= cols.length - 4 ? 'num' : null }, t(k))))),
    h('tbody', {}, rows.length ? rows.map((r) => h('tr', { class: r.present ? '' : 'is-absent' },
      h('th', { scope: 'row' }, r.name),
      ind ? null : h('td', {}, r.present ? teamLabel(r.team) : '—'),
      h('td', {}, r.present ? `✓ ${t('yes')}` : t('no')),
      h('td', { class: 'num' }, fmtInt(r.turns)),
      h('td', { class: 'num' }, fmtInt(r.attempts)),
      h('td', { class: 'num' }, r.best_accuracy == null ? '—' : `${pct(r.best_accuracy)}%`),
      h('td', { class: 'num' }, fmtInt(r.points)))) : h('tr', {}, h('td', { colspan: String(cols.length), class: 'empty' }, '—'))));
  const csv = $('#btn-csv');
  csv.href = `/api/class/sessions/${encodeURIComponent(st.id)}/participation.csv`;
  csv.setAttribute('download', `participation-${((st.classroom && st.classroom.name) || 'class').replace(/[^\w-]+/g, '_')}-${new Date().toISOString().slice(0, 10)}.csv`);
  $('#btn-again').hidden = !(st.classroom && st.classroom.id);
  setTip('final');
  if (celebrate) {
    const w = ranking[0] ? { ...byId(ranking[0].team_id), ...ranking[0] } : null;
    if (ind) announce(t('finale_aria_ind', { name: w ? w.name : '', score: w ? w.score : 0, spoke, present }));
    else announce(t('finale_aria', { team: w ? teamName(w) : '', score: w ? w.score : 0, spoke, present }));
    sfx.fanfare();
    fx.burst(220);
    setTimeout(() => fx.burst(160), 900);
  }
}

async function playAgain() {
  const st = game.session;
  sfx.click();
  const cid = st && st.classroom && st.classroom.id;
  game.session = null; game.finish = null; game.lastTurnNo = null;
  await goSetup();
  if (cid && setup.classrooms.some((c) => c.id === cid)) {
    $('#saved-class').value = String(cid);
    await onSavedClass({ target: $('#saved-class') });
    if (st.pack && st.pack.id && setup.packs.some((p) => p.id === st.pack.id)) { setup.packId = st.pack.id; renderPacks(); }
    if (st.grouping === 'individual') {
      setup.grouping = 'individual';
      if (QC_OPTIONS.includes(st.total_turns)) setup.questionCount = st.total_turns;
      renderGrouping(); renderNames(); setTip('s1');
      return;
    }
    setup.grouping = 'teams'; renderGrouping();
    setup.teamCount = st.teams.length || setup.teamCount; setup.teamCountTouched = true;
    setup.rounds = Math.max(1, Math.round(st.total_turns / Math.max(1, st.teams.length))); setup.roundsTouched = true;
    renderSize();
  }
}


// ================================================================= shortcuts, header buttons, health
const KEYS = [['1–4', 'keys_answer'], ['C', 'keys_c'], ['P', 'keys_p'], ['→ / Enter', 'keys_next'], ['S', 'keys_s'],
  ['T', 'keys_t'], ['M', 'keys_m'], ['F', 'keys_f'], ['?', 'keys_q'], ['Esc', 'keys_esc']];
function renderKeys() {
  const ind = modeInd();
  $('#keys-list').replaceChildren(...KEYS.flatMap(([k, d]) => [h('dt', {}, h('kbd', { class: 'kbd' }, k)), h('dd', {}, t(ind && d === 'keys_c' ? 'keys_c_ind' : d))]));
}
function openKeys() { const d = $('#keys-dlg'); if (!d.open) { renderKeys(); d.showModal(); $('#keys-close').focus(); } }

function syncMuteBtn() {
  const b = $('#btn-mute');
  b.replaceChildren(icon(sfx.muted ? 'volume-x' : 'volume-2'));
  b.setAttribute('aria-pressed', String(sfx.muted));
  b.setAttribute('aria-label', sfx.muted ? t('unmute') : t('mute'));
  b.title = b.getAttribute('aria-label');
}
function syncFsBtn() {
  const b = $('#btn-fs');
  const on = !!document.fullscreenElement;
  b.setAttribute('aria-label', on ? t('exit_fullscreen') : t('fullscreen'));
  b.title = b.getAttribute('aria-label');
  b.setAttribute('aria-pressed', String(on));
}
async function toggleFullscreen() {
  try {
    if (document.fullscreenElement) await document.exitFullscreen();
    else await document.documentElement.requestFullscreen();
  } catch { /* not allowed (e.g. iframe) */ }
}
function toggleMute() { sfx.setMuted(!sfx.muted); syncMuteBtn(); sfx.click(); }

async function checkHealth() {
  const banner = $('#health-banner');
  try {
    const res = await api('/api/health');
    const issues = [];
    if (res && res.db === false) issues.push(t('health_db'));
    banner.className = 'banner banner-warning cr-banner';
    banner.hidden = !issues.length;
    banner.textContent = issues.length ? `${t('health_prefix')}${issues.join('; ')}.` : '';
  } catch {
    banner.hidden = false;
    banner.className = 'banner banner-danger cr-banner';
    banner.textContent = t('health_down');
  }
}

function onKeyDown(e) {
  if (e.defaultPrevented || e.ctrlKey || e.metaKey || e.altKey) return;
  if ($('#keys-dlg').open) return;
  if (isTypingTarget(e.target)) return;
  const k = e.key;
  if (k === '?') { e.preventDefault(); openKeys(); return; }
  if (k === 'f' || k === 'F') { e.preventDefault(); toggleFullscreen(); return; }
  if (k === 'm' || k === 'M') { e.preventDefault(); toggleMute(); return; }
  if (k === 't' || k === 'T') { e.preventDefault(); toggleTips(); return; }
  if (k === 'Escape' && !$('#add-stu-form').hidden) { closeAddForm(); return; }
  if (screen === 'lobby' && k === 'Escape' && game.moving) { game.moving = null; renderLobby(); return; }
  if (screen !== 'stage') return;
  const onControl = e.target && e.target.closest && e.target.closest('button, a, [role="radio"]');
  if (/^[1-4]$/.test(k)) { e.preventDefault(); answer(Number(k) - 1); return; }
  if (k === 'c' || k === 'C') { e.preventDefault(); cycleCaptain(); return; }
  if (k === 'p' || k === 'P') { e.preventDefault(); togglePause(); return; }
  if (k === 's' || k === 'S') { e.preventDefault(); skipTurn(); return; }
  if (k === 'ArrowRight' || (k === 'Enter' && !onControl)) { if (!$('#btn-next').hidden) { e.preventDefault(); nextTurn(); } }
}

function route() {
  // the in-page report moved to the dedicated /reports page
  if (location.hash === '#reports') { location.replace('/reports'); return; }
  if (!screen) goSetup();
}

// ================================================================= init
function init() {
  const saved = lsGet(LS_LANG);
  lang = LANGS.includes(saved) ? saved : 'en';
  for (const b of $$('.lang-btn')) b.addEventListener('click', () => { sfx.click(); setLang(b.dataset.lang); });
  $('#btn-mute').addEventListener('click', toggleMute);
  $('#btn-keys').addEventListener('click', openKeys);
  $('#keys-close').addEventListener('click', () => $('#keys-dlg').close());
  $('#btn-fs').addEventListener('click', toggleFullscreen);
  document.addEventListener('fullscreenchange', () => { syncFsBtn(); if (screen === 'stage') requestAnimationFrame(fitQuestion); });
  $('#gm-tips-collapse').addEventListener('click', toggleTips);
  $('#stage-tips-toggle').addEventListener('click', toggleTips);
  $('#stage-end').addEventListener('click', endGameEarly);

  // setup
  $('#wz-next').addEventListener('click', startSession);
  $('#saved-class').addEventListener('change', onSavedClass);
  let nt = 0;
  $('#paste-names').addEventListener('input', () => { clearTimeout(nt); nt = setTimeout(renderNames, 200); });
  $('#cr-school').addEventListener('input', onSchoolInput);
  $('#cr-school-change').addEventListener('click', () => { renderSchool(true); $('#cr-school').focus(); });
  const step = (key, d, lo, hi) => () => { setup[key] = Math.max(lo, Math.min(hi, setup[key] + d)); setup[`${key}Touched`] = true; sfx.click(); renderSize(); };
  $('#tc-minus').addEventListener('click', step('teamCount', -1, 2, 6));
  $('#tc-plus').addEventListener('click', step('teamCount', 1, 2, 6));
  $('#rd-minus').addEventListener('click', step('rounds', -1, 1, 10));
  $('#rd-plus').addEventListener('click', step('rounds', 1, 1, 10));

  // lobby
  $('#lobby-back').addEventListener('click', () => { sfx.click(); goSetup(); });
  $('#lobby-shuffle').addEventListener('click', shuffleTeams);
  $('#lobby-start').addEventListener('click', () => { sfx.fanfare(); enterStage(); });

  // setup: grouping switch
  for (const b of $$('#grouping-switch .seg-btn')) b.addEventListener('click', () => setGrouping(b.dataset.grouping));
  radioKeys($('#grouping-switch'), (btn) => setGrouping(btn.dataset.grouping));
  // ready (individual)
  $('#ready-back').addEventListener('click', () => { sfx.click(); goSetup(); });
  $('#ready-start').addEventListener('click', () => { sfx.fanfare(); enterStage(); });
  // + Add student
  $('#add-stu-btn').addEventListener('click', openAddForm);
  $('#add-stu-cancel').addEventListener('click', () => closeAddForm());
  $('#add-stu-form').addEventListener('submit', submitAddStudent);
  $('#add-stu-name').addEventListener('keydown', (e) => { if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); closeAddForm(); } });
  // who's answering (individual)
  $('#who-search').addEventListener('input', () => renderWho());
  $('#who-search').addEventListener('keydown', onWhoSearchKey);

  // stage
  $('#btn-pause').addEventListener('click', togglePause);
  $('#btn-skip').addEventListener('click', skipTurn);
  $('#btn-next').addEventListener('click', nextTurn);
  document.addEventListener('keydown', onKeyDown);
  window.addEventListener('resize', () => { if (screen === 'stage') requestAnimationFrame(fitQuestion); });

  // finale + reports
  $('#btn-again').addEventListener('click', playAgain);
  $('#btn-new-game').addEventListener('click', () => { sfx.click(); game.session = null; game.finish = null; setup.savedId = ''; setup.classroom = null; $('#paste-names').value = ''; goSetup(); });

  window.addEventListener('pagehide', stopStage);
  window.addEventListener('hashchange', route);
  // Browser Back mirrors the on-screen buttons: stage → "End game" (confirm), lobby → Setup, never a silent exit.
  window.addEventListener('popstate', () => {
    for (const d of $$('dialog[open]')) d.close();
    if (screen === 'stage') { try { history.pushState({ cr: 'game' }, '', '#setup'); } catch { /* ignore */ } endGameEarly(); return; }
    if (screen === 'lobby' || screen === 'ready') { navGuard = false; sfx.click(); goSetup(); }
  });
  document.addEventListener('pointerdown', () => sfx.unlock(), { once: true });

  applyI18n();
  checkHealth();
  route();
}

init();
