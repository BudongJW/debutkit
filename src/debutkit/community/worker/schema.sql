-- debutkit 커뮤니티 D1(SQLite) 구조. debutkit이 올릴 때와 고칠 때 차례로 실행한다(이미 있으면 그대로).
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
-- 회원. role: owner(스트리머) | mod(매니저) | viewer | banned
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  avatar TEXT NOT NULL DEFAULT '',
  role TEXT NOT NULL DEFAULT 'viewer',
  points INTEGER NOT NULL DEFAULT 0,
  streak INTEGER NOT NULL DEFAULT 0,
  last_attend TEXT NOT NULL DEFAULT '',
  created_at INTEGER NOT NULL
);
-- 연결한 계정: provider는 chzzk, soop, twitch, youtube(채팅 인증 또는 로그인), discord, google, owner(debutkit의 스트리머 접속)
CREATE TABLE IF NOT EXISTS identities (
  provider TEXT NOT NULL,
  subject TEXT NOT NULL,
  user_id INTEGER NOT NULL,
  name TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (provider, subject)
);
CREATE INDEX IF NOT EXISTS identities_user ON identities (user_id);
-- 로그인 상태: token은 쿠키 값의 SHA-256
CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, user_id INTEGER NOT NULL, expires INTEGER NOT NULL);
-- 채팅 인증과 스트리머 접속 대기: code는 채팅에 칠 숫자(또는 한 번 쓰는 접속 코드), waiter는 기다리는 브라우저의 비밀값 SHA-256
CREATE TABLE IF NOT EXISTS pending (
  code TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  waiter TEXT NOT NULL DEFAULT '',
  user_id INTEGER,
  provider TEXT NOT NULL DEFAULT '',
  subject TEXT NOT NULL DEFAULT '',
  name TEXT NOT NULL DEFAULT '',
  role TEXT NOT NULL DEFAULT '',
  expires INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS posts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  board TEXT NOT NULL,
  user_id INTEGER NOT NULL,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  image TEXT NOT NULL DEFAULT '',
  link TEXT NOT NULL DEFAULT '',
  pinned INTEGER NOT NULL DEFAULT 0,
  hidden INTEGER NOT NULL DEFAULT 0,
  likes INTEGER NOT NULL DEFAULT 0,
  comments INTEGER NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS posts_board ON posts (board, hidden, pinned, id);
CREATE INDEX IF NOT EXISTS posts_user ON posts (user_id, created_at);
CREATE TABLE IF NOT EXISTS comments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  post_id INTEGER NOT NULL,
  user_id INTEGER NOT NULL,
  body TEXT NOT NULL,
  hidden INTEGER NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS comments_post ON comments (post_id, id);
CREATE INDEX IF NOT EXISTS comments_user ON comments (user_id, created_at);
CREATE TABLE IF NOT EXISTS likes (post_id INTEGER NOT NULL, user_id INTEGER NOT NULL, PRIMARY KEY (post_id, user_id));
-- 신고: kind는 post | comment. 같은 사람이 같은 글을 두 번 신고하지 못함
CREATE TABLE IF NOT EXISTS reports (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT NOT NULL,
  target INTEGER NOT NULL,
  user_id INTEGER NOT NULL,
  reason TEXT NOT NULL,
  done INTEGER NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL,
  UNIQUE (kind, target, user_id)
);
-- 방송 일정: day 0~6(월~일)은 매주, date(YYYY-MM-DD)는 그날만. off=1은 휴방
CREATE TABLE IF NOT EXISTS schedule (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  day INTEGER NOT NULL DEFAULT -1,
  date TEXT NOT NULL DEFAULT '',
  time TEXT NOT NULL DEFAULT '',
  title TEXT NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  off INTEGER NOT NULL DEFAULT 0
);
-- 포인트 기록: day는 한국 시간 날짜(하루 한도 계산)
CREATE TABLE IF NOT EXISTS points (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  delta INTEGER NOT NULL,
  reason TEXT NOT NULL,
  day TEXT NOT NULL,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS points_user ON points (user_id, reason, day);
-- 방송에 띄울 글(스트리머, 매니저가 고름). debutkit이 가져가면 지운다
CREATE TABLE IF NOT EXISTS stage (id INTEGER PRIMARY KEY AUTOINCREMENT, post_id INTEGER NOT NULL, created_at INTEGER NOT NULL);
-- 커뮤니티에서 받은 참여 추첨 참가
CREATE TABLE IF NOT EXISTS raffle (user_id INTEGER PRIMARY KEY, name TEXT NOT NULL, created_at INTEGER NOT NULL);
