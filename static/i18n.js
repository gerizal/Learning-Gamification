// i18n.js — shared EN / BM / ID strings for the live pages (home, host, play). Vanilla ES module.
//
//   import { t, getLang, setLang, mountLangSwitch, applyI18n, BRAND } from './i18n.js';
//   t('join')                         // string in the current language (falls back to EN, then the key)
//   t('answered_n', { n: 3, m: 10 })  // "{n}" placeholders
//   applyI18n()                       // fills [data-i18n], [data-i18n-aria], [data-i18n-ph], [data-i18n-title]
//   mountLangSwitch(el, onChange)     // renders EN / BM / ID buttons (aria-pressed)
//
// Brand name is editable here (working name — owner may rename).

export const BRAND = { name: 'PlayClass', long: 'Classroom Learning Game' };

const LS_LANG = 'live.lang';
export const LANGS = [
  { code: 'en', label: 'EN', name: 'English', html: 'en' },
  { code: 'ms', label: 'BM', name: 'Bahasa Melayu', html: 'ms' },
  { code: 'id', label: 'ID', name: 'Bahasa Indonesia', html: 'id' },
];

const S = {
  en: {
    // shared
    lang_label: 'Language', brand_tag: 'Learn together, play together',
    reconnecting: 'Reconnecting…', connected: 'Connected', error_generic: 'Something went wrong. Please try again.',
    offline: 'No connection to the server. Check the Wi-Fi.', close: 'Close', cancel: 'Cancel', save: 'Save',
    pts: 'pts', points_n: '{n} points', rank_n: 'Rank #{n}', of_n: '{n} of {m}',
    q_of: 'Question {n} of {m}', sec_left: '{n} seconds left', time_up: "Time's up!",
    correct: 'Correct!', incorrect: 'Not quite', correct_answer: 'Correct answer', your_answer: 'Your answer',
    shape_0: 'triangle', shape_1: 'diamond', shape_2: 'circle', shape_3: 'square',
    option_label: '{shape}: {text}', leaderboard: 'Leaderboard', you: 'you',
    streak_n: '🔥 {n} in a row', rank_up: 'up {n}', rank_down: 'down {n}', true_: 'True', false_: 'False',
    // home
    home_title: 'Ready to play?', teacher: "I'm a Teacher", teacher_sub: 'Host a game on the big screen',
    student: "I'm a Student", student_sub: 'Join with a game PIN',
    pin_label: 'Game PIN', pin_ph: '6-digit PIN', join: 'Join', pin_invalid: 'The PIN has 6 digits.',
    pin_notfound: 'No game with this PIN. Check the screen and try again.', pin_ended: 'This game has already finished.',
    // play
    play_title: 'Join a game', nick_title: 'What is your name?', nick_label: 'Nickname', nick_ph: 'e.g. Aisyah',
    nick_hint: 'Up to 20 letters. Your teacher will see it.', go: "Let's go!", nick_taken: 'That name is taken. Try another one.',
    nick_empty: 'Please type a name.', too_many: 'Too many tries. Wait a few seconds and try again.',
    in_title: "You're in!", in_sub: 'Look at the big screen. The game starts soon.',
    game_pin: 'PIN {pin}', change_name: 'Change name', rename_title: 'Change your name', rename_locked: 'Your teacher turned off name changes.',
    renamed: 'Name changed to {name}.',
    get_ready: 'Get ready…', answer_sent: 'Answer sent!', answer_wait: 'Look at the screen. Results come after this question.',
    no_answer: 'No answer this time', no_answer_sub: "That's OK — get ready for the next one!",
    too_late: 'Too late for this question. Get ready for the next one!',
    q_unsupported: 'This question type is not supported. Wait for the next question.',
    result_points: '+{n} points', result_now: "You're #{rank} with {score} points",
    lb_title: 'Live leaderboard', lb_gap: '{n} pts behind {name}', lb_top: "You're in first place!",
    lb_open: 'Rank #{rank} · {score} pts — open leaderboard', lb_none: 'No scores yet.',
    wait_next: 'Waiting for the next question…', final_title: 'Game over!', final_rank: 'You finished #{rank}',
    final_score: '{score} points', thanks: 'Thanks for playing!', play_again: 'Join another game',
    kicked_title: 'You left the game', kicked_sub: 'Your teacher removed you from this game. You can join again with a new name.',
    game_gone: 'This game is no longer available.', choose: 'Choose your answer',
    // host
    host_title: 'Host a game', create_title: 'Create a game', game_title: 'Game title (optional)',
    game_title_ph: 'e.g. Class 5A quiz', pick_pack: 'Pick a topic', all_packs: 'All topics', all_packs_desc: 'Mix questions from every topic.',
    topic_ai: 'AI', topic_general: 'General', why_teach: 'Why teach this?', n_questions: '{n} quiz questions',
    how_many: 'How many questions?', results_mode: 'When do students see results?',
    instant_on: 'Show results instantly', instant_on_sub: 'Right after answering (recommended)',
    instant_off: 'Reveal after each question', instant_off_sub: 'Kahoot-style suspense',
    allow_rename: 'Allow name changes', more_details: 'More details (optional)', teacher_name: 'Teacher name',
    school: 'School', program: 'Program', create: 'Create game', creating: 'Creating…',
    back_home: 'Back to home', leave_game: 'Leave game', leave_title: 'Leave the game?', leave_sub: 'You can rejoin with the same PIN.', leave: 'Leave',
    lobby_leave_title: 'Leave the lobby? This ends the game for everyone.', discard_title: 'Discard your changes to this question?', discard: 'Discard', keep_editing: 'Keep editing',
    your_school: 'Your school', change: 'Change',
    school_ph: 'e.g. SK Taman Megah', school_saved: 'Saved on this device.', err_school: 'Enter your school.',
    err_school_card: 'Fill in your school at the top first.',
    no_devices: 'No student devices? Play on one screen (teams)', not_enough: 'Not enough questions in this topic. Pick fewer questions or another topic.',
    resume: 'Continue game {pin}', new_game: 'New game',
    lobby_join_at: 'Join at', lobby_enter_pin: 'and enter the PIN', lobby_steps: 'On a phone, tablet or computer: open the link, type the PIN, choose a name.',
    players_n: '{n} players', waiting_players: 'Waiting for players…', start: 'Start', start_hint: 'Start when everyone is in.',
    kick: 'Remove {name}', rename: 'Rename {name}', rename_player: 'Rename player', removed: '{name} was removed.',
    answered_n: '{n} / {m} answered', skip_timer: 'Show answer', next: 'Next', see_leaderboard: 'Leaderboard',
    next_question: 'Next question', finish: 'See the winners', end_game: 'End game', end_confirm: 'End the game now for everyone?',
    reveal_title: 'The answer', top3: 'Fastest correct', nobody_correct: 'Nobody got it this time — explain it together!',
    podium_title: 'Winners!', summary_line: '{j} students joined · {a} answered at least once',
    csv: 'Download results (CSV)', settings: 'Settings', mute: 'Mute sounds', unmute: 'Turn sounds on',
    music_on: 'Play lobby music', music_off: 'Stop lobby music', fullscreen: 'Full screen (F)',
    live_lb: 'Live ranking', lb_after: 'Scores update after the answer.', dist_great: 'Correct', dist_retry: 'Wrong',
    dist_no: 'No answer', tips: 'Tips for game master', keys_hint: 'Space / Enter = Next · F = full screen',
    q_unsupported_host: 'This question type is not supported. Press Show answer to move on.',
    settings_saved: 'Settings saved.',
    settings_unavailable: 'This server cannot change settings yet.', joined_toast: '{name} joined',
    tip_create: 'Pick a topic your class knows a little about. 10 questions take about 10 minutes. “Show results instantly” keeps every student busy.',
    tip_lobby: 'Read the link and PIN out loud. Walk around and help. Unkind names? Tap ✕ to remove or ✎ to rename. Start when most are in — late students can still join.',
    tip_question: 'Read the question out loud for everyone. Watch “answered”. When all have answered, the answer shows by itself.',
    tip_reveal: 'Ask one student why this answer is right. Praise effort, not only speed.',
    tip_leaderboard: 'Celebrate big jumps, not only #1. Then press Next.',
    tip_podium: 'Clap for the top 3 and for everyone who tried. Download the CSV for your report.',
  },
  ms: {
    lang_label: 'Bahasa', brand_tag: 'Belajar bersama, bermain bersama',
    reconnecting: 'Menyambung semula…', connected: 'Bersambung', error_generic: 'Ada masalah. Sila cuba lagi.',
    offline: 'Tiada sambungan ke pelayan. Semak Wi-Fi.', close: 'Tutup', cancel: 'Batal', save: 'Simpan',
    pts: 'mata', points_n: '{n} mata', rank_n: 'Tempat #{n}', of_n: '{n} daripada {m}',
    q_of: 'Soalan {n} daripada {m}', sec_left: '{n} saat lagi', time_up: 'Masa tamat!',
    correct: 'Betul!', incorrect: 'Belum tepat', correct_answer: 'Jawapan betul', your_answer: 'Jawapan kamu',
    shape_0: 'segi tiga', shape_1: 'berlian', shape_2: 'bulatan', shape_3: 'segi empat',
    option_label: '{shape}: {text}', leaderboard: 'Papan markah', you: 'kamu',
    streak_n: '🔥 {n} berturut-turut', rank_up: 'naik {n}', rank_down: 'turun {n}', true_: 'Betul', false_: 'Salah',
    home_title: 'Sedia untuk bermain?', teacher: 'Saya Guru', teacher_sub: 'Anjurkan permainan di skrin besar',
    student: 'Saya Murid', student_sub: 'Sertai dengan PIN permainan',
    pin_label: 'PIN Permainan', pin_ph: 'PIN 6 digit', join: 'Sertai', pin_invalid: 'PIN ada 6 digit.',
    pin_notfound: 'Tiada permainan dengan PIN ini. Semak skrin dan cuba lagi.', pin_ended: 'Permainan ini sudah tamat.',
    play_title: 'Sertai permainan', nick_title: 'Siapa nama kamu?', nick_label: 'Nama panggilan', nick_ph: 'cth. Aisyah',
    nick_hint: 'Hingga 20 huruf. Guru kamu akan nampak.', go: 'Jom!', nick_taken: 'Nama itu sudah diambil. Cuba nama lain.',
    nick_empty: 'Sila taip nama.', too_many: 'Terlalu banyak cubaan. Tunggu beberapa saat dan cuba lagi.',
    in_title: 'Kamu sudah masuk!', in_sub: 'Lihat skrin besar. Permainan akan bermula.',
    game_pin: 'PIN {pin}', change_name: 'Tukar nama', rename_title: 'Tukar nama kamu', rename_locked: 'Guru kamu telah menutup pertukaran nama.',
    renamed: 'Nama ditukar kepada {name}.',
    get_ready: 'Bersedia…', answer_sent: 'Jawapan dihantar!', answer_wait: 'Lihat skrin. Keputusan selepas soalan ini.',
    no_answer: 'Tiada jawapan kali ini', no_answer_sub: 'Tidak mengapa — bersedia untuk soalan seterusnya!',
    too_late: 'Sudah terlambat untuk soalan ini. Bersedia untuk soalan seterusnya!',
    q_unsupported: 'Jenis soalan ini tidak disokong. Tunggu soalan seterusnya.',
    result_points: '+{n} mata', result_now: 'Kamu di tempat #{rank} dengan {score} mata',
    lb_title: 'Papan markah langsung', lb_gap: '{n} mata di belakang {name}', lb_top: 'Kamu di tempat pertama!',
    lb_open: 'Tempat #{rank} · {score} mata — buka papan markah', lb_none: 'Belum ada markah.',
    wait_next: 'Menunggu soalan seterusnya…', final_title: 'Permainan tamat!', final_rank: 'Kamu di tempat #{rank}',
    final_score: '{score} mata', thanks: 'Terima kasih kerana bermain!', play_again: 'Sertai permainan lain',
    kicked_title: 'Kamu telah keluar', kicked_sub: 'Guru kamu mengeluarkan kamu daripada permainan ini. Kamu boleh sertai semula dengan nama baharu.',
    game_gone: 'Permainan ini tidak lagi tersedia.', choose: 'Pilih jawapan kamu',
    host_title: 'Anjurkan permainan', create_title: 'Cipta permainan', game_title: 'Tajuk permainan (pilihan)',
    game_title_ph: 'cth. Kuiz Kelas 5A', pick_pack: 'Pilih topik', all_packs: 'Semua topik', all_packs_desc: 'Campur soalan daripada semua topik.',
    topic_ai: 'AI', topic_general: 'Umum', why_teach: 'Kenapa ajar ini?', n_questions: '{n} soalan kuiz',
    how_many: 'Berapa soalan?', results_mode: 'Bila murid melihat keputusan?',
    instant_on: 'Tunjuk keputusan serta-merta', instant_on_sub: 'Sejurus selepas menjawab (disyorkan)',
    instant_off: 'Dedahkan selepas setiap soalan', instant_off_sub: 'Saspens gaya Kahoot',
    allow_rename: 'Benarkan tukar nama', more_details: 'Butiran lain (pilihan)', teacher_name: 'Nama guru',
    school: 'Sekolah', program: 'Program', create: 'Cipta permainan', creating: 'Sedang mencipta…',
    back_home: 'Kembali ke laman utama', leave_game: 'Keluar permainan', leave_title: 'Keluar dari permainan?', leave_sub: 'Kamu boleh masuk semula dengan PIN yang sama.', leave: 'Keluar',
    lobby_leave_title: 'Keluar dari lobi? Ini menamatkan permainan untuk semua.', discard_title: 'Buang perubahan pada soalan ini?', discard: 'Buang', keep_editing: 'Terus sunting',
    your_school: 'Sekolah anda', change: 'Tukar',
    school_ph: 'cth. SK Taman Megah', school_saved: 'Disimpan pada peranti ini.', err_school: 'Masukkan nama sekolah.',
    err_school_card: 'Isi nama sekolah di bahagian atas dahulu.',
    no_devices: 'Murid tiada peranti? Main di satu skrin (pasukan)', not_enough: 'Soalan tidak cukup dalam topik ini. Pilih kurang soalan atau topik lain.',
    resume: 'Teruskan permainan {pin}', new_game: 'Permainan baharu',
    lobby_join_at: 'Sertai di', lobby_enter_pin: 'dan masukkan PIN', lobby_steps: 'Di telefon, tablet atau komputer: buka pautan, taip PIN, pilih nama.',
    players_n: '{n} pemain', waiting_players: 'Menunggu pemain…', start: 'Mula', start_hint: 'Mula apabila semua sudah masuk.',
    kick: 'Keluarkan {name}', rename: 'Tukar nama {name}', rename_player: 'Tukar nama pemain', removed: '{name} telah dikeluarkan.',
    answered_n: '{n} / {m} sudah jawab', skip_timer: 'Tunjuk jawapan', next: 'Seterusnya', see_leaderboard: 'Papan markah',
    next_question: 'Soalan seterusnya', finish: 'Lihat pemenang', end_game: 'Tamatkan', end_confirm: 'Tamatkan permainan sekarang untuk semua?',
    reveal_title: 'Jawapannya', top3: 'Paling pantas & betul', nobody_correct: 'Tiada yang betul kali ini — terangkan bersama!',
    podium_title: 'Pemenang!', summary_line: '{j} murid menyertai · {a} menjawab sekurang-kurangnya sekali',
    csv: 'Muat turun keputusan (CSV)', settings: 'Tetapan', mute: 'Senyapkan bunyi', unmute: 'Hidupkan bunyi',
    music_on: 'Mainkan muzik lobi', music_off: 'Hentikan muzik lobi', fullscreen: 'Skrin penuh (F)',
    live_lb: 'Kedudukan langsung', lb_after: 'Markah dikemas kini selepas jawapan.', dist_great: 'Betul', dist_retry: 'Salah',
    dist_no: 'Tiada jawapan', tips: 'Tip untuk pengacara', keys_hint: 'Space / Enter = Seterusnya · F = skrin penuh',
    q_unsupported_host: 'Jenis soalan ini tidak disokong. Tekan Tunjuk jawapan untuk teruskan.',
    settings_saved: 'Tetapan disimpan.',
    settings_unavailable: 'Pelayan ini belum boleh menukar tetapan.', joined_toast: '{name} menyertai',
    tip_create: 'Pilih topik yang murid sedikit tahu. 10 soalan ambil kira-kira 10 minit. “Tunjuk keputusan serta-merta” membuat semua murid sibuk.',
    tip_lobby: 'Baca pautan dan PIN dengan kuat. Berjalan dan bantu murid. Nama tidak sopan? Tekan ✕ untuk keluarkan atau ✎ untuk tukar. Mula apabila ramai sudah masuk — yang lewat masih boleh sertai.',
    tip_question: 'Baca soalan dengan kuat untuk semua. Perhatikan “sudah jawab”. Apabila semua sudah jawab, jawapan keluar sendiri.',
    tip_reveal: 'Tanya seorang murid kenapa jawapan ini betul. Puji usaha, bukan hanya kepantasan.',
    tip_leaderboard: 'Raikan lonjakan besar, bukan hanya #1. Kemudian tekan Seterusnya.',
    tip_podium: 'Tepuk tangan untuk 3 teratas dan semua yang mencuba. Muat turun CSV untuk laporan.',
  },
  id: {
    lang_label: 'Bahasa', brand_tag: 'Belajar bersama, bermain bersama',
    reconnecting: 'Menyambung ulang…', connected: 'Tersambung', error_generic: 'Ada masalah. Coba lagi.',
    offline: 'Tidak ada koneksi ke server. Cek Wi-Fi.', close: 'Tutup', cancel: 'Batal', save: 'Simpan',
    pts: 'poin', points_n: '{n} poin', rank_n: 'Peringkat #{n}', of_n: '{n} dari {m}',
    q_of: 'Soal {n} dari {m}', sec_left: '{n} detik lagi', time_up: 'Waktu habis!',
    correct: 'Benar!', incorrect: 'Belum tepat', correct_answer: 'Jawaban benar', your_answer: 'Jawabanmu',
    shape_0: 'segitiga', shape_1: 'belah ketupat', shape_2: 'lingkaran', shape_3: 'persegi',
    option_label: '{shape}: {text}', leaderboard: 'Papan skor', you: 'kamu',
    streak_n: '🔥 {n} beruntun', rank_up: 'naik {n}', rank_down: 'turun {n}', true_: 'Benar', false_: 'Salah',
    home_title: 'Siap bermain?', teacher: 'Saya Guru', teacher_sub: 'Pandu permainan di layar besar',
    student: 'Saya Siswa', student_sub: 'Gabung dengan PIN permainan',
    pin_label: 'PIN Permainan', pin_ph: 'PIN 6 angka', join: 'Gabung', pin_invalid: 'PIN terdiri dari 6 angka.',
    pin_notfound: 'Tidak ada permainan dengan PIN ini. Cek layar lalu coba lagi.', pin_ended: 'Permainan ini sudah selesai.',
    play_title: 'Gabung permainan', nick_title: 'Siapa namamu?', nick_label: 'Nama panggilan', nick_ph: 'mis. Aisyah',
    nick_hint: 'Maksimal 20 huruf. Gurumu akan melihatnya.', go: 'Ayo!', nick_taken: 'Nama itu sudah dipakai. Coba nama lain.',
    nick_empty: 'Ketik namamu dulu.', too_many: 'Terlalu banyak percobaan. Tunggu sebentar lalu coba lagi.',
    in_title: 'Kamu sudah masuk!', in_sub: 'Lihat layar besar. Permainan segera dimulai.',
    game_pin: 'PIN {pin}', change_name: 'Ganti nama', rename_title: 'Ganti namamu', rename_locked: 'Gurumu mematikan ganti nama.',
    renamed: 'Nama diganti menjadi {name}.',
    get_ready: 'Bersiap…', answer_sent: 'Jawaban terkirim!', answer_wait: 'Lihat layar. Hasil muncul setelah soal ini.',
    no_answer: 'Tidak ada jawaban kali ini', no_answer_sub: 'Tidak apa-apa — bersiap untuk soal berikutnya!',
    too_late: 'Sudah terlambat untuk soal ini. Bersiap untuk soal berikutnya!',
    q_unsupported: 'Jenis soal ini tidak didukung. Tunggu soal berikutnya.',
    result_points: '+{n} poin', result_now: 'Kamu di peringkat #{rank} dengan {score} poin',
    lb_title: 'Papan skor langsung', lb_gap: '{n} poin di belakang {name}', lb_top: 'Kamu di peringkat pertama!',
    lb_open: 'Peringkat #{rank} · {score} poin — buka papan skor', lb_none: 'Belum ada skor.',
    wait_next: 'Menunggu soal berikutnya…', final_title: 'Permainan selesai!', final_rank: 'Kamu di peringkat #{rank}',
    final_score: '{score} poin', thanks: 'Terima kasih sudah bermain!', play_again: 'Gabung permainan lain',
    kicked_title: 'Kamu keluar dari permainan', kicked_sub: 'Gurumu mengeluarkanmu dari permainan ini. Kamu bisa gabung lagi dengan nama baru.',
    game_gone: 'Permainan ini sudah tidak tersedia.', choose: 'Pilih jawabanmu',
    host_title: 'Pandu permainan', create_title: 'Buat permainan', game_title: 'Judul permainan (opsional)',
    game_title_ph: 'mis. Kuis Kelas 5A', pick_pack: 'Pilih topik', all_packs: 'Semua topik', all_packs_desc: 'Campur soal dari semua topik.',
    topic_ai: 'AI', topic_general: 'Umum', why_teach: 'Kenapa diajarkan?', n_questions: '{n} soal kuis',
    how_many: 'Berapa soal?', results_mode: 'Kapan siswa melihat hasil?',
    instant_on: 'Tampilkan hasil langsung', instant_on_sub: 'Tepat setelah menjawab (disarankan)',
    instant_off: 'Tampilkan setelah tiap soal', instant_off_sub: 'Tegang ala Kahoot',
    allow_rename: 'Izinkan ganti nama', more_details: 'Detail lain (opsional)', teacher_name: 'Nama guru',
    school: 'Sekolah', program: 'Program', create: 'Buat permainan', creating: 'Membuat…',
    back_home: 'Kembali ke beranda', leave_game: 'Keluar permainan', leave_title: 'Keluar dari permainan?', leave_sub: 'Kamu bisa masuk lagi dengan PIN yang sama.', leave: 'Keluar',
    lobby_leave_title: 'Keluar dari lobi? Ini mengakhiri permainan untuk semua.', discard_title: 'Buang perubahan pada soal ini?', discard: 'Buang', keep_editing: 'Lanjut edit',
    your_school: 'Sekolah Anda', change: 'Ubah',
    school_ph: 'mis. SDN 1 Menteng', school_saved: 'Tersimpan di perangkat ini.', err_school: 'Isi nama sekolah.',
    err_school_card: 'Isi nama sekolah di bagian atas dulu.',
    no_devices: 'Siswa tidak punya perangkat? Main di satu layar (tim)', not_enough: 'Soal di topik ini tidak cukup. Pilih lebih sedikit soal atau topik lain.',
    resume: 'Lanjutkan permainan {pin}', new_game: 'Permainan baru',
    lobby_join_at: 'Gabung di', lobby_enter_pin: 'lalu masukkan PIN', lobby_steps: 'Di HP, tablet, atau komputer: buka tautan, ketik PIN, pilih nama.',
    players_n: '{n} pemain', waiting_players: 'Menunggu pemain…', start: 'Mulai', start_hint: 'Mulai saat semua sudah masuk.',
    kick: 'Keluarkan {name}', rename: 'Ganti nama {name}', rename_player: 'Ganti nama pemain', removed: '{name} sudah dikeluarkan.',
    answered_n: '{n} / {m} sudah menjawab', skip_timer: 'Tampilkan jawaban', next: 'Lanjut', see_leaderboard: 'Papan skor',
    next_question: 'Soal berikutnya', finish: 'Lihat pemenang', end_game: 'Akhiri', end_confirm: 'Akhiri permainan sekarang untuk semua?',
    reveal_title: 'Jawabannya', top3: 'Tercepat & benar', nobody_correct: 'Belum ada yang benar — bahas bersama!',
    podium_title: 'Pemenang!', summary_line: '{j} siswa bergabung · {a} menjawab minimal sekali',
    csv: 'Unduh hasil (CSV)', settings: 'Pengaturan', mute: 'Matikan suara', unmute: 'Nyalakan suara',
    music_on: 'Putar musik lobi', music_off: 'Hentikan musik lobi', fullscreen: 'Layar penuh (F)',
    live_lb: 'Peringkat langsung', lb_after: 'Skor diperbarui setelah jawaban.', dist_great: 'Benar', dist_retry: 'Salah',
    dist_no: 'Tidak menjawab', tips: 'Tips untuk pemandu', keys_hint: 'Spasi / Enter = Lanjut · F = layar penuh',
    q_unsupported_host: 'Jenis soal ini tidak didukung. Tekan Tampilkan jawaban untuk lanjut.',
    settings_saved: 'Pengaturan disimpan.',
    settings_unavailable: 'Server ini belum bisa mengubah pengaturan.', joined_toast: '{name} bergabung',
    tip_create: 'Pilih topik yang sedikit dikenal kelasmu. 10 soal kira-kira 10 menit. “Tampilkan hasil langsung” membuat semua siswa tetap aktif.',
    tip_lobby: 'Bacakan tautan dan PIN. Berkeliling dan bantu. Nama tidak sopan? Tekan ✕ untuk mengeluarkan atau ✎ untuk mengganti. Mulai saat sebagian besar sudah masuk — yang terlambat tetap bisa gabung.',
    tip_question: 'Bacakan soal untuk semua. Perhatikan “sudah menjawab”. Kalau semua sudah menjawab, jawaban muncul sendiri.',
    tip_reveal: 'Tanya satu siswa kenapa jawaban ini benar. Puji usahanya, bukan hanya kecepatan.',
    tip_leaderboard: 'Rayakan lompatan besar, bukan hanya #1. Lalu tekan Lanjut.',
    tip_podium: 'Tepuk tangan untuk 3 teratas dan semua yang sudah mencoba. Unduh CSV untuk laporan.',
  },
};

// Teacher quiz editor + create tabs (merged into the tables above).
const EXTRA = {
  en: {
    skip: 'Skip to content', tab_ready: 'Ready-made quizzes', tab_mine: 'My quizzes', new_quiz: 'New quiz',
    mine_hint: 'Quizzes you make are remembered on this device.', mine_empty: 'No quizzes yet. Make your own in a few minutes!',
    setup_title: 'Game settings', playing_quiz: 'Quiz: {name}', back: 'Back', copy_link: 'Copy edit link', use: 'Use',
    duplicate_edit: 'Duplicate & edit', edit: 'Edit', delete: 'Delete', edit_quiz: 'Edit quiz',
    saved_device: 'This quiz is saved on this device. To edit it on another laptop, use “Copy edit link” and keep the link private.',
    quiz_name: 'Quiz name', add_question: 'Add question', no_questions: 'No questions yet. Press “Add question”.',
    q_count_n: '{n} questions', q_text: 'Question', answers: 'Answers (2–4)', tf_preset: 'True / False', add_answer: 'Add answer',
    time_limit: 'Time limit', points: 'Points', standard: 'Standard', double: 'Double', seconds_n: '{n} s',
    preview: 'Student preview', save_question: 'Save question', new_question: 'New question', edit_question: 'Edit question {n}',
    move_up: 'Move question {n} up', move_down: 'Move question {n} down', edit_n: 'Edit question {n}', delete_n: 'Delete question {n}',
    answer_n: 'Answer {n} ({shape})', remove_answer: 'Remove answer {n}', correct_label: 'Correct', correct_for: 'Answer {n} is correct',
    err_prompt: 'Type the question.', err_opts_min: 'Add at least 2 answers.', err_opt_empty: 'Fill in every answer (or remove the empty one).',
    err_opt_dup: 'Two answers are the same.', err_correct: 'Choose the correct answer.', err_name: 'Give your quiz a name.',
    copied: 'Edit link copied.', copy_fail: 'Copy this link: {url}', deleted: 'Question deleted.', archived: 'Question removed from the quiz (kept in past reports).',
    delete_confirm: 'Delete question {n}?', quiz_saved: 'Saved.', quizzes_unavailable: 'Quiz editing is not available on this server yet.',
    use_this: 'Use this quiz', selected: 'Selected', need_questions: 'Add at least 1 question before you use this quiz.',
    all_n: 'All ({n})', edit_link_bad: 'This edit link is not valid.', untitled: 'My quiz', ready_hint: 'Pick a quiz to play now.',
  },
  ms: {
    skip: 'Langkau ke kandungan', tab_ready: 'Kuiz sedia ada', tab_mine: 'Kuiz saya', new_quiz: 'Kuiz baharu',
    mine_hint: 'Kuiz yang anda buat disimpan pada peranti ini.', mine_empty: 'Belum ada kuiz. Buat kuiz sendiri dalam beberapa minit!',
    setup_title: 'Tetapan permainan', playing_quiz: 'Kuiz: {name}', back: 'Kembali', copy_link: 'Salin pautan edit', use: 'Guna',
    duplicate_edit: 'Salin & edit', edit: 'Edit', delete: 'Padam', edit_quiz: 'Edit kuiz',
    saved_device: 'Kuiz ini disimpan pada peranti ini. Untuk edit di komputer lain, guna “Salin pautan edit” dan simpan pautan itu secara peribadi.',
    quiz_name: 'Nama kuiz', add_question: 'Tambah soalan', no_questions: 'Belum ada soalan. Tekan “Tambah soalan”.',
    q_count_n: '{n} soalan', q_text: 'Soalan', answers: 'Jawapan (2–4)', tf_preset: 'Betul / Salah', add_answer: 'Tambah jawapan',
    time_limit: 'Had masa', points: 'Mata', standard: 'Biasa', double: 'Berganda', seconds_n: '{n} s',
    preview: 'Pratonton murid', save_question: 'Simpan soalan', new_question: 'Soalan baharu', edit_question: 'Edit soalan {n}',
    move_up: 'Naikkan soalan {n}', move_down: 'Turunkan soalan {n}', edit_n: 'Edit soalan {n}', delete_n: 'Padam soalan {n}',
    answer_n: 'Jawapan {n} ({shape})', remove_answer: 'Buang jawapan {n}', correct_label: 'Betul', correct_for: 'Jawapan {n} betul',
    err_prompt: 'Taip soalan.', err_opts_min: 'Tambah sekurang-kurangnya 2 jawapan.', err_opt_empty: 'Isi setiap jawapan (atau buang yang kosong).',
    err_opt_dup: 'Dua jawapan sama.', err_correct: 'Pilih jawapan yang betul.', err_name: 'Beri nama kuiz anda.',
    copied: 'Pautan edit disalin.', copy_fail: 'Salin pautan ini: {url}', deleted: 'Soalan dipadam.', archived: 'Soalan dikeluarkan daripada kuiz (disimpan dalam laporan lama).',
    delete_confirm: 'Padam soalan {n}?', quiz_saved: 'Disimpan.', quizzes_unavailable: 'Edit kuiz belum tersedia pada pelayan ini.',
    use_this: 'Guna kuiz ini', selected: 'Dipilih', need_questions: 'Tambah sekurang-kurangnya 1 soalan sebelum menggunakan kuiz ini.',
    all_n: 'Semua ({n})', edit_link_bad: 'Pautan edit ini tidak sah.', untitled: 'Kuiz saya', ready_hint: 'Pilih kuiz untuk dimainkan sekarang.',
  },
  id: {
    skip: 'Lewati ke konten', tab_ready: 'Kuis siap pakai', tab_mine: 'Kuis saya', new_quiz: 'Kuis baru',
    mine_hint: 'Kuis buatanmu disimpan di perangkat ini.', mine_empty: 'Belum ada kuis. Buat kuismu sendiri dalam beberapa menit!',
    setup_title: 'Pengaturan permainan', playing_quiz: 'Kuis: {name}', back: 'Kembali', copy_link: 'Salin tautan edit', use: 'Pakai',
    duplicate_edit: 'Duplikat & edit', edit: 'Edit', delete: 'Hapus', edit_quiz: 'Edit kuis',
    saved_device: 'Kuis ini tersimpan di perangkat ini. Untuk mengedit di laptop lain, pakai “Salin tautan edit” dan jaga tautannya tetap pribadi.',
    quiz_name: 'Nama kuis', add_question: 'Tambah soal', no_questions: 'Belum ada soal. Tekan “Tambah soal”.',
    q_count_n: '{n} soal', q_text: 'Soal', answers: 'Jawaban (2–4)', tf_preset: 'Benar / Salah', add_answer: 'Tambah jawaban',
    time_limit: 'Batas waktu', points: 'Poin', standard: 'Standar', double: 'Ganda', seconds_n: '{n} dtk',
    preview: 'Pratinjau siswa', save_question: 'Simpan soal', new_question: 'Soal baru', edit_question: 'Edit soal {n}',
    move_up: 'Naikkan soal {n}', move_down: 'Turunkan soal {n}', edit_n: 'Edit soal {n}', delete_n: 'Hapus soal {n}',
    answer_n: 'Jawaban {n} ({shape})', remove_answer: 'Hapus jawaban {n}', correct_label: 'Benar', correct_for: 'Jawaban {n} benar',
    err_prompt: 'Ketik soalnya.', err_opts_min: 'Tambahkan minimal 2 jawaban.', err_opt_empty: 'Isi semua jawaban (atau hapus yang kosong).',
    err_opt_dup: 'Ada dua jawaban yang sama.', err_correct: 'Pilih jawaban yang benar.', err_name: 'Beri nama kuismu.',
    copied: 'Tautan edit disalin.', copy_fail: 'Salin tautan ini: {url}', deleted: 'Soal dihapus.', archived: 'Soal dikeluarkan dari kuis (tetap ada di laporan lama).',
    delete_confirm: 'Hapus soal {n}?', quiz_saved: 'Tersimpan.', quizzes_unavailable: 'Edit kuis belum tersedia di server ini.',
    use_this: 'Pakai kuis ini', selected: 'Dipilih', need_questions: 'Tambahkan minimal 1 soal sebelum memakai kuis ini.',
    all_n: 'Semua ({n})', edit_link_bad: 'Tautan edit ini tidak valid.', untitled: 'Kuis saya', ready_hint: 'Pilih kuis untuk dimainkan sekarang.',
  },
};
for (const code of Object.keys(EXTRA)) Object.assign(S[code], EXTRA[code]);

// /reports (program team). Keys prefixed rp_. ID falls back to EN.
const REPORTS = {
  en: {
    rp_title: 'Program reports', rp_gate_title: 'Program reports', rp_gate_sub: 'For the program team. Enter the reports access code.',
    rp_code: 'Reports access code', rp_open: 'Open reports', rp_code_wrong: 'That access code is not right.',
    rp_not_configured: 'Reports are not set up on this server yet (REPORTS_KEY is missing). Ask the person who runs PlayClass to set it.',
    rp_code_empty: 'Please type the access code.', rp_code_expired: 'Your access code is no longer valid. Enter it again.',
    rp_too_many: 'Too many wrong codes. Wait a few minutes and try again.', rp_sign_out: 'Sign out',
    rp_filters: 'Filters', rp_program: 'Program', rp_all_programs: 'All programs', rp_mode: 'Game type', rp_all_modes: 'All types',
    rp_mode_live: 'Live (PIN)', rp_mode_homework: 'Homework', rp_mode_one: 'One-screen (teams)', rp_school_search: 'School',
    rp_school_ph: 'Search schools', rp_from: 'From', rp_to: 'To', rp_apply: 'Apply', rp_reset: 'Reset',
    rp_overview: 'Overview', rp_breadcrumb: 'Breadcrumb', rp_program_overview: 'All schools',
    rp_kpi_sessions: 'Sessions', rp_kpi_sessions_sub: '{live} live · {hw} homework · {cls} one-screen',
    rp_kpi_schools: 'Schools', rp_kpi_schools_sub: '{n} sessions without a school',
    rp_kpi_participants: 'Participants', rp_kpi_participants_sub: 'Unique players and present students',
    rp_kpi_participation: 'Participation', rp_kpi_participation_sub: '{n} answered at least once',
    rp_kpi_completion: 'Completion', rp_kpi_completion_sub: '{n} of {m} session attendances completed',
    rp_kpi_score: 'Average score', rp_kpi_score_sub: 'Average accuracy of answers',
    rp_kpi_range: 'Date range', rp_no_data: 'No data for these filters.',
    rp_funnel: 'Funnel', rp_funnel_sub: 'Per session attended', rp_step_joined: 'Joined', rp_step_answered: 'Answered at least once',
    rp_step_completed: 'Completed', rp_by_program: 'By program', rp_schools: 'Schools', rp_school: 'School',
    rp_sessions: 'Sessions', rp_participants: 'Participants', rp_participated: 'Participated', rp_participation_pct: 'Participation %',
    rp_completion_pct: 'Completion %', rp_avg_score: 'Avg score %', rp_last_session: 'Last session', rp_download: 'Download CSV',
    rp_sort_by: 'Sort by {col}', rp_prev: 'Previous', rp_next: 'Next', rp_page: '{from}–{to} of {n}',
    rp_tab_sessions: 'Sessions', rp_tab_progress: 'Students progress', rp_type: 'Type', rp_session: 'Session',
    rp_date: 'Date', rp_teacher: 'Teacher', rp_class_csv: 'Class CSV', rp_type_live: 'Live', rp_type_homework: 'Homework',
    rp_type_one: 'One-screen', rp_students: 'Students', rp_name: 'Name', rp_present: 'Present', rp_answered: 'Answered',
    rp_correct: 'Correct', rp_accuracy: 'Accuracy %', rp_score: 'Score', rp_rank: 'Rank', rp_completed: 'Completed',
    rp_progress: 'Progress', rp_yes: 'Yes', rp_no: 'No', rp_absent: 'Absent', rp_loading: 'Loading…',
    rp_loaded: 'Loaded.', rp_downloaded: 'Download started: {name}', rp_error: 'Could not load the report. Try again.',
    rp_match_note: 'Matched by name, approximate: players are anonymous nicknames, so the same name in one school is treated as one student.',
    rp_sessions_attended: 'Sessions attended', rp_scores: 'Score % per session (date order)', rp_first: 'First',
    rp_last: 'Last', rp_improvement: 'Improvement', rp_not_scored: 'no answers', rp_session_of: 'Session',
    rp_questions: 'Questions', rp_footer: 'PlayClass 2026', rp_skip: 'Skip to content',
    rp_school_not_set: '(not set)', rp_kpi_totals: 'Totals', rp_individuals: 'individuals', rp_view_sessions: 'Sessions of {name}', rp_view_students: 'Students of {name}',
  },
  ms: {
    rp_title: 'Laporan program', rp_gate_title: 'Laporan program', rp_gate_sub: 'Untuk pasukan program. Masukkan kod akses laporan.',
    rp_code: 'Kod akses laporan', rp_open: 'Buka laporan', rp_code_wrong: 'Kod akses itu tidak betul.',
    rp_not_configured: 'Laporan belum disediakan pada pelayan ini (REPORTS_KEY tiada). Minta orang yang menjalankan PlayClass menetapkannya.',
    rp_code_empty: 'Sila taip kod akses.', rp_code_expired: 'Kod akses anda tidak lagi sah. Masukkan semula.',
    rp_too_many: 'Terlalu banyak kod salah. Tunggu beberapa minit dan cuba lagi.', rp_sign_out: 'Log keluar',
    rp_filters: 'Penapis', rp_program: 'Program', rp_all_programs: 'Semua program', rp_mode: 'Jenis permainan', rp_all_modes: 'Semua jenis',
    rp_mode_live: 'Langsung (PIN)', rp_mode_homework: 'Kerja rumah', rp_mode_one: 'Satu skrin (pasukan)', rp_school_search: 'Sekolah',
    rp_school_ph: 'Cari sekolah', rp_from: 'Dari', rp_to: 'Hingga', rp_apply: 'Guna', rp_reset: 'Set semula',
    rp_overview: 'Ringkasan', rp_program_overview: 'Semua sekolah', rp_kpi_sessions: 'Sesi', rp_kpi_schools: 'Sekolah',
    rp_kpi_participants: 'Peserta', rp_kpi_participation: 'Penyertaan', rp_kpi_completion: 'Penyelesaian',
    rp_kpi_score: 'Skor purata', rp_kpi_range: 'Julat tarikh', rp_no_data: 'Tiada data untuk penapis ini.',
    rp_funnel: 'Corong', rp_funnel_sub: 'Bagi setiap sesi yang dihadiri', rp_step_joined: 'Menyertai',
    rp_step_answered: 'Menjawab sekurang-kurangnya sekali', rp_step_completed: 'Selesai', rp_by_program: 'Mengikut program',
    rp_schools: 'Sekolah', rp_school: 'Sekolah', rp_sessions: 'Sesi', rp_participants: 'Peserta', rp_participated: 'Menyertai aktif',
    rp_participation_pct: '% penyertaan', rp_completion_pct: '% selesai', rp_avg_score: '% skor purata', rp_last_session: 'Sesi terakhir',
    rp_download: 'Muat turun CSV', rp_prev: 'Sebelumnya', rp_next: 'Seterusnya', rp_tab_sessions: 'Sesi',
    rp_tab_progress: 'Kemajuan murid', rp_type: 'Jenis', rp_session: 'Sesi', rp_date: 'Tarikh', rp_teacher: 'Guru',
    rp_students: 'Murid', rp_name: 'Nama', rp_present: 'Hadir', rp_answered: 'Dijawab', rp_correct: 'Betul',
    rp_accuracy: '% ketepatan', rp_score: 'Skor', rp_rank: 'Kedudukan', rp_completed: 'Selesai', rp_progress: 'Kemajuan',
    rp_yes: 'Ya', rp_no: 'Tidak', rp_absent: 'Tidak hadir', rp_loading: 'Memuatkan…', rp_error: 'Laporan tidak dapat dimuatkan. Cuba lagi.',
    rp_match_note: 'Dipadankan mengikut nama, anggaran: pemain menggunakan nama samaran, jadi nama yang sama dalam satu sekolah dianggap seorang murid.',
    rp_sessions_attended: 'Sesi dihadiri', rp_scores: '% skor setiap sesi (ikut tarikh)', rp_first: 'Pertama', rp_last: 'Terakhir',
    rp_improvement: 'Peningkatan', rp_kpi_totals: 'Jumlah', rp_individuals: 'individu', rp_not_scored: 'tiada jawapan', rp_questions: 'Soalan', rp_skip: 'Langkau ke kandungan',
  },
};
for (const code of Object.keys(REPORTS)) Object.assign(S[code], REPORTS[code]);

// "How will students play?" + Homework (self-paced) host monitor + student flow. Keys hw_ / mode_ / mg_ / dl_.
const HOMEWORK = {
  en: {
    how_play: 'How will students play?',
    mode_live: 'On their own devices', mode_live_sub: 'A live game with a PIN — everyone plays together now.',
    mode_hw: 'Homework', mode_hw_sub: 'Students play on their own time, before a deadline.',
    mode_present: 'Teacher presents', mode_present_tag: 'No student devices', mode_present_sub: 'You show the quiz on one screen and tap in the answers.',
    grouping_label: 'Who answers?', grp_individual: 'Individuals', grp_individual_sub: 'Each student scores for themselves',
    grp_teams: 'Groups', grp_teams_sub: 'Students play in teams',
    setup_title_hw: 'Homework settings', setup_title_present: 'Presenter settings',
    create_hw: 'Create homework', open_presenter: 'Open the presenter',
    present_hint: 'You add the students’ names in the next step.',
    deadline: 'Deadline', dl_tomorrow: 'Tomorrow', dl_3d: '3 days', dl_1w: '1 week', dl_none: 'No deadline',
    dl_date: 'Date', dl_time: 'Time', dl_hint: 'Students can play until then (at most 30 days).',
    err_deadline_past: 'Pick a time in the future.', err_deadline_far: 'The deadline can be at most 30 days away.',
    err_deadline_empty: 'Pick a date and a time, or choose “No deadline”.',
    speed_bonus: 'Count answer speed', speed_bonus_sub: 'Faster answers earn more points. Off: only correct answers count.',
    shuffle: 'Shuffle questions per student', shuffle_sub: 'Each student gets the questions in a different order.',
    hw_share_title: 'Your homework is ready!', hw_share_sub: 'Share the link and the PIN with your students.',
    hw_link: 'Join link', copy_join: 'Copy link', link_copied: 'Link copied.',
    hw_board: 'For the whiteboard', hw_board_text: 'Go to {url} · PIN {pin} · before {when}', hw_board_text_nodl: 'Go to {url} · PIN {pin}',
    copy_text: 'Copy text', text_copied: 'Text copied.', print: 'Print', open_monitor: 'Open the monitor',
    hw_keeps_running: 'The homework keeps running. Find it under “My games”.',
    hw_monitor: 'Homework monitor', hw_status_open: 'Open', hw_status_paused: 'Paused', hw_status_closed: 'Closed',
    closes_at: 'Closes {when}', no_deadline: 'No deadline',
    hw_progress: 'Progress', prog_joined: 'Joined', prog_in_progress: 'In progress', prog_finished: 'Finished',
    prog_not_started: 'Not started', prog_bar: '{f} of {j} students finished · {p} in progress',
    students: 'Students', col_name: 'Name', col_progress: 'Progress', col_score: 'Score', col_finished: 'Finished',
    col_last: 'Last active', col_actions: 'Actions', no_students: 'No students yet. Share the link and the PIN.',
    per_question: 'Questions', col_q: 'Question', col_answered: 'Answered', col_correct: 'Correct',
    pause: 'Pause', resume_game: 'Resume',
    pause_warn: 'Pause stops joining, starting and answering. A running question’s clock keeps going.',
    change_deadline: 'Change deadline', end_now: 'End now', hw_end_confirm: 'End this homework now? Students can no longer play.',
    share: 'Share', remove: 'Remove', remove_confirm: 'Remove {name} from this game?',
    paused_toast: 'Homework paused.', resumed_toast: 'Homework resumed.', deadline_saved: 'Deadline saved.', hw_ended_toast: 'Homework ended.',
    ago_now: 'just now',
    my_games: 'My games', my_games_hint: 'Games made on this device. Come back any time to check on them.',
    mg_live: 'Live', mg_hw: 'Homework', mg_monitor: 'Monitor', mg_results: 'Results', mg_continue: 'Continue',
    mg_forget: 'Remove {title} from this list', mg_loading: 'Checking…', mg_progress: '{f} of {j} finished',
    mg_lobby: 'In the lobby', mg_running: 'Running',
    hw_eyebrow: 'Homework', hw_intro_q: '{n} questions', hw_due: 'Due {when}', hw_no_due: 'No deadline',
    hw_no_rush: 'No rush — each question has its own timer once you start it.', hw_start: 'Start', hw_continue: 'Continue',
    hw_welcome_back: 'Welcome back! You are on question {n} of {m}.',
    hw_next: 'Next question', hw_see_result: 'See my result',
    hw_timeout: 'Time ran out on that one — moving on', hw_timeout_sub: 'No points for that question. The next one is ready when you are.',
    hw_paused_title: 'Your teacher paused this game', hw_paused_sub: 'Wait here. It carries on by itself when your teacher resumes.',
    hw_done_title: 'All done!', hw_close_page: 'You can close this page.',
    hw_closed_title: 'This homework is closed', hw_closed_sub: 'The deadline has passed or your teacher ended it.',
    hw_prog: 'Question {n} of {m}', hw_prog_done: 'All {m} questions done',
    hw_leave_sub: 'Your progress is saved. Come back before the deadline with the same PIN.',
    pin_paused: 'Your teacher has paused this game. Try again a bit later.',
  },
  ms: {
    how_play: 'Bagaimana murid akan bermain?',
    mode_live: 'Pada peranti sendiri', mode_live_sub: 'Permainan langsung dengan PIN — semua bermain bersama sekarang.',
    mode_hw: 'Kerja rumah', mode_hw_sub: 'Murid bermain pada masa sendiri, sebelum tarikh akhir.',
    mode_present: 'Guru membentangkan', mode_present_tag: 'Tiada peranti murid', mode_present_sub: 'Anda paparkan kuiz pada satu skrin dan masukkan jawapan.',
    grouping_label: 'Siapa yang menjawab?', grp_individual: 'Individu', grp_individual_sub: 'Setiap murid mengumpul mata sendiri',
    grp_teams: 'Kumpulan', grp_teams_sub: 'Murid bermain dalam pasukan',
    setup_title_hw: 'Tetapan kerja rumah', setup_title_present: 'Tetapan pembentang',
    create_hw: 'Cipta kerja rumah', open_presenter: 'Buka pembentang',
    present_hint: 'Anda masukkan nama murid pada langkah seterusnya.',
    deadline: 'Tarikh akhir', dl_tomorrow: 'Esok', dl_3d: '3 hari', dl_1w: '1 minggu', dl_none: 'Tiada tarikh akhir',
    dl_date: 'Tarikh', dl_time: 'Masa', dl_hint: 'Murid boleh bermain sehingga masa itu (paling lama 30 hari).',
    err_deadline_past: 'Pilih masa pada masa hadapan.', err_deadline_far: 'Tarikh akhir paling lama 30 hari lagi.',
    err_deadline_empty: 'Pilih tarikh dan masa, atau pilih “Tiada tarikh akhir”.',
    speed_bonus: 'Kira kelajuan menjawab', speed_bonus_sub: 'Jawapan lebih cepat dapat lebih banyak mata. Tutup: hanya jawapan betul dikira.',
    shuffle: 'Kocok soalan bagi setiap murid', shuffle_sub: 'Setiap murid mendapat soalan dalam susunan berbeza.',
    hw_share_title: 'Kerja rumah anda sudah sedia!', hw_share_sub: 'Kongsi pautan dan PIN dengan murid anda.',
    hw_link: 'Pautan sertai', copy_join: 'Salin pautan', link_copied: 'Pautan disalin.',
    hw_board: 'Untuk papan putih', hw_board_text: 'Pergi ke {url} · PIN {pin} · sebelum {when}', hw_board_text_nodl: 'Pergi ke {url} · PIN {pin}',
    copy_text: 'Salin teks', text_copied: 'Teks disalin.', print: 'Cetak', open_monitor: 'Buka pemantau',
    hw_keeps_running: 'Kerja rumah terus berjalan. Cari di bawah “Permainan saya”.',
    hw_monitor: 'Pemantau kerja rumah', hw_status_open: 'Dibuka', hw_status_paused: 'Dijeda', hw_status_closed: 'Ditutup',
    closes_at: 'Ditutup {when}', no_deadline: 'Tiada tarikh akhir',
    hw_progress: 'Kemajuan', prog_joined: 'Menyertai', prog_in_progress: 'Sedang bermain', prog_finished: 'Selesai',
    prog_not_started: 'Belum mula', prog_bar: '{f} daripada {j} murid selesai · {p} sedang bermain',
    students: 'Murid', col_name: 'Nama', col_progress: 'Kemajuan', col_score: 'Skor', col_finished: 'Selesai',
    col_last: 'Aktif terakhir', col_actions: 'Tindakan', no_students: 'Belum ada murid. Kongsi pautan dan PIN.',
    per_question: 'Soalan', col_q: 'Soalan', col_answered: 'Dijawab', col_correct: 'Betul',
    pause: 'Jeda', resume_game: 'Sambung',
    pause_warn: 'Jeda menghentikan sertai, mula dan jawab. Jam soalan yang sedang berjalan tetap berjalan.',
    change_deadline: 'Tukar tarikh akhir', end_now: 'Tamatkan sekarang', hw_end_confirm: 'Tamatkan kerja rumah ini sekarang? Murid tidak boleh bermain lagi.',
    share: 'Kongsi', remove: 'Keluarkan', remove_confirm: 'Keluarkan {name} daripada permainan ini?',
    paused_toast: 'Kerja rumah dijeda.', resumed_toast: 'Kerja rumah disambung.', deadline_saved: 'Tarikh akhir disimpan.', hw_ended_toast: 'Kerja rumah ditamatkan.',
    ago_now: 'baru sahaja',
    my_games: 'Permainan saya', my_games_hint: 'Permainan yang dibuat pada peranti ini. Kembali bila-bila masa untuk menyemak.',
    mg_live: 'Langsung', mg_hw: 'Kerja rumah', mg_monitor: 'Pantau', mg_results: 'Keputusan', mg_continue: 'Teruskan',
    mg_forget: 'Buang {title} daripada senarai ini', mg_loading: 'Menyemak…', mg_progress: '{f} daripada {j} selesai',
    mg_lobby: 'Di lobi', mg_running: 'Sedang berjalan',
    hw_eyebrow: 'Kerja rumah', hw_intro_q: '{n} soalan', hw_due: 'Hantar sebelum {when}', hw_no_due: 'Tiada tarikh akhir',
    hw_no_rush: 'Tak perlu tergesa-gesa — setiap soalan ada pemasanya sendiri sebaik anda mulakannya.', hw_start: 'Mula', hw_continue: 'Teruskan',
    hw_welcome_back: 'Selamat kembali! Anda di soalan {n} daripada {m}.',
    hw_next: 'Soalan seterusnya', hw_see_result: 'Lihat keputusan saya',
    hw_timeout: 'Masa tamat untuk soalan itu — teruskan', hw_timeout_sub: 'Tiada mata untuk soalan itu. Soalan seterusnya sedia bila anda sedia.',
    hw_paused_title: 'Guru anda menjeda permainan ini', hw_paused_sub: 'Tunggu di sini. Ia bersambung sendiri apabila guru anda menyambungnya.',
    hw_done_title: 'Semua selesai!', hw_close_page: 'Anda boleh tutup halaman ini.',
    hw_closed_title: 'Kerja rumah ini sudah ditutup', hw_closed_sub: 'Tarikh akhir sudah lepas atau guru anda telah menamatkannya.',
    hw_prog: 'Soalan {n} daripada {m}', hw_prog_done: 'Semua {m} soalan selesai',
    hw_leave_sub: 'Kemajuan anda disimpan. Kembali sebelum tarikh akhir dengan PIN yang sama.',
    pin_paused: 'Guru anda telah menjeda permainan ini. Cuba lagi sebentar nanti.',
  },
  id: {
    how_play: 'Bagaimana siswa akan bermain?',
    mode_live: 'Di perangkat masing-masing', mode_live_sub: 'Permainan langsung dengan PIN — semua bermain bersama sekarang.',
    mode_hw: 'PR', mode_hw_sub: 'Siswa bermain kapan saja, sebelum tenggat.',
    mode_present: 'Guru mempresentasikan', mode_present_tag: 'Tanpa perangkat siswa', mode_present_sub: 'Kamu tampilkan kuis di satu layar dan memasukkan jawabannya.',
    grouping_label: 'Siapa yang menjawab?', grp_individual: 'Perorangan', grp_individual_sub: 'Setiap siswa mengumpulkan poin sendiri',
    grp_teams: 'Kelompok', grp_teams_sub: 'Siswa bermain dalam tim',
    setup_title_hw: 'Pengaturan PR', setup_title_present: 'Pengaturan presentasi',
    create_hw: 'Buat PR', open_presenter: 'Buka presentasi',
    present_hint: 'Nama siswa diisi di langkah berikutnya.',
    deadline: 'Tenggat', dl_tomorrow: 'Besok', dl_3d: '3 hari', dl_1w: '1 minggu', dl_none: 'Tanpa tenggat',
    dl_date: 'Tanggal', dl_time: 'Jam', dl_hint: 'Siswa bisa bermain sampai saat itu (paling lama 30 hari).',
    err_deadline_past: 'Pilih waktu di masa depan.', err_deadline_far: 'Tenggat paling lama 30 hari lagi.',
    err_deadline_empty: 'Pilih tanggal dan jam, atau pilih “Tanpa tenggat”.',
    speed_bonus: 'Hitung kecepatan menjawab', speed_bonus_sub: 'Jawaban lebih cepat dapat poin lebih banyak. Mati: hanya jawaban benar yang dihitung.',
    shuffle: 'Acak soal untuk tiap siswa', shuffle_sub: 'Setiap siswa mendapat urutan soal yang berbeda.',
    hw_share_title: 'PR-mu sudah siap!', hw_share_sub: 'Bagikan tautan dan PIN ke siswa.',
    hw_link: 'Tautan gabung', copy_join: 'Salin tautan', link_copied: 'Tautan disalin.',
    hw_board: 'Untuk papan tulis', hw_board_text: 'Buka {url} · PIN {pin} · sebelum {when}', hw_board_text_nodl: 'Buka {url} · PIN {pin}',
    copy_text: 'Salin teks', text_copied: 'Teks disalin.', print: 'Cetak', open_monitor: 'Buka pemantau',
    hw_keeps_running: 'PR tetap berjalan. Temukan di “Permainan saya”.',
    hw_monitor: 'Pemantau PR', hw_status_open: 'Dibuka', hw_status_paused: 'Dijeda', hw_status_closed: 'Ditutup',
    closes_at: 'Ditutup {when}', no_deadline: 'Tanpa tenggat',
    hw_progress: 'Kemajuan', prog_joined: 'Bergabung', prog_in_progress: 'Sedang mengerjakan', prog_finished: 'Selesai',
    prog_not_started: 'Belum mulai', prog_bar: '{f} dari {j} siswa selesai · {p} sedang mengerjakan',
    students: 'Siswa', col_name: 'Nama', col_progress: 'Kemajuan', col_score: 'Skor', col_finished: 'Selesai',
    col_last: 'Terakhir aktif', col_actions: 'Tindakan', no_students: 'Belum ada siswa. Bagikan tautan dan PIN.',
    per_question: 'Soal', col_q: 'Soal', col_answered: 'Dijawab', col_correct: 'Benar',
    pause: 'Jeda', resume_game: 'Lanjutkan',
    pause_warn: 'Jeda menghentikan bergabung, memulai dan menjawab. Waktu soal yang sedang berjalan tetap berjalan.',
    change_deadline: 'Ubah tenggat', end_now: 'Akhiri sekarang', hw_end_confirm: 'Akhiri PR ini sekarang? Siswa tidak bisa bermain lagi.',
    share: 'Bagikan', remove: 'Keluarkan', remove_confirm: 'Keluarkan {name} dari permainan ini?',
    paused_toast: 'PR dijeda.', resumed_toast: 'PR dilanjutkan.', deadline_saved: 'Tenggat disimpan.', hw_ended_toast: 'PR diakhiri.',
    ago_now: 'baru saja',
    my_games: 'Permainan saya', my_games_hint: 'Permainan yang dibuat di perangkat ini. Kembali kapan saja untuk memantau.',
    mg_live: 'Langsung', mg_hw: 'PR', mg_monitor: 'Pantau', mg_results: 'Hasil', mg_continue: 'Lanjutkan',
    mg_forget: 'Hapus {title} dari daftar ini', mg_loading: 'Memeriksa…', mg_progress: '{f} dari {j} selesai',
    mg_lobby: 'Di lobi', mg_running: 'Sedang berjalan',
    hw_eyebrow: 'PR', hw_intro_q: '{n} soal', hw_due: 'Tenggat {when}', hw_no_due: 'Tanpa tenggat',
    hw_no_rush: 'Santai saja — setiap soal punya waktunya sendiri setelah kamu memulainya.', hw_start: 'Mulai', hw_continue: 'Lanjutkan',
    hw_welcome_back: 'Selamat datang kembali! Kamu di soal {n} dari {m}.',
    hw_next: 'Soal berikutnya', hw_see_result: 'Lihat hasilku',
    hw_timeout: 'Waktu soal itu habis — lanjut', hw_timeout_sub: 'Tidak ada poin untuk soal itu. Soal berikutnya siap kapan pun kamu siap.',
    hw_paused_title: 'Gurumu menjeda permainan ini', hw_paused_sub: 'Tunggu di sini. Permainan lanjut sendiri saat gurumu melanjutkannya.',
    hw_done_title: 'Selesai semua!', hw_close_page: 'Kamu boleh menutup halaman ini.',
    hw_closed_title: 'PR ini sudah ditutup', hw_closed_sub: 'Tenggat sudah lewat atau gurumu sudah mengakhirinya.',
    hw_prog: 'Soal {n} dari {m}', hw_prog_done: 'Semua {m} soal selesai',
    hw_leave_sub: 'Kemajuanmu tersimpan. Kembali sebelum tenggat dengan PIN yang sama.',
    pin_paused: 'Gurumu sedang menjeda permainan ini. Coba lagi sebentar lagi.',
  },
};
for (const code of Object.keys(HOMEWORK)) Object.assign(S[code], HOMEWORK[code]);

// localStorage can throw (private mode, blocked storage). Log it once with context, then carry on without it:
// the language falls back to English and a new pick lasts for this page only.
const warned = new Set();
function warnOnce(context, err) {
  if (warned.has(context)) return;
  warned.add(context);
  console.warn(`[i18n] ${context}`, err);
}
function lsGet(k) {
  try { return window.localStorage.getItem(k); } catch (err) { warnOnce(`localStorage read failed (${k}); using English`, err); return null; }
}
function lsSet(k, v) { try { window.localStorage.setItem(k, v); } catch (err) { warnOnce(`localStorage write failed (${k}); language not remembered`, err); } }

function initialLang() {
  // English is the primary language; BM / ID only when the user picked them in the switcher.
  const saved = lsGet(LS_LANG);
  return saved && S[saved] ? saved : 'en';
}

let lang = initialLang();
const listeners = new Set();

export const getLang = () => lang;
export const locale = () => ({ en: 'en-GB', ms: 'ms-MY', id: 'id-ID' }[lang] || 'en-GB');
export const fmtInt = (n) => Number(n || 0).toLocaleString(locale());

export function t(key, vars) {
  let s = (S[lang] && S[lang][key]) ?? S.en[key] ?? key;
  if (vars) s = s.replace(/\{(\w+)\}/g, (m, k) => (vars[k] !== undefined ? String(vars[k]) : m));
  return s;
}

export function applyI18n(root = document) {
  document.documentElement.lang = (LANGS.find((l) => l.code === lang) || LANGS[0]).html;
  root.querySelectorAll('[data-i18n]').forEach((el) => { el.textContent = t(el.dataset.i18n); });
  root.querySelectorAll('[data-i18n-aria]').forEach((el) => { el.setAttribute('aria-label', t(el.dataset.i18nAria)); });
  root.querySelectorAll('[data-i18n-ph]').forEach((el) => { el.setAttribute('placeholder', t(el.dataset.i18nPh)); });
  root.querySelectorAll('[data-i18n-title]').forEach((el) => { el.setAttribute('title', t(el.dataset.i18nTitle)); });
  root.querySelectorAll('[data-brand]').forEach((el) => { el.textContent = BRAND[el.dataset.brand] || BRAND.name; });
}

export function setLang(code) {
  if (!S[code] || code === lang) return;
  lang = code;
  lsSet(LS_LANG, code);
  applyI18n();
  listeners.forEach((fn) => { try { fn(code); } catch { /* ignore */ } });
}
export function onLangChange(fn) { listeners.add(fn); return () => listeners.delete(fn); }

/** Render a compact EN/BM/ID segmented switch into `el` (a role=group element). */
export function mountLangSwitch(el) {
  el.setAttribute('role', 'group');
  const render = () => {
    el.setAttribute('aria-label', t('lang_label'));
    el.replaceChildren(...LANGS.map((l) => {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'lv-lang-btn';
      b.textContent = l.label;
      b.lang = l.html;
      b.setAttribute('aria-label', l.name);
      b.setAttribute('aria-pressed', String(l.code === lang));
      b.addEventListener('click', () => setLang(l.code));
      return b;
    }));
  };
  render();
  onLangChange(render);
}
