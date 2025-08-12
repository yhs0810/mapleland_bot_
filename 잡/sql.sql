-- 1) 테이블 생성 (MySQL)
CREATE TABLE IF NOT EXISTS users (
  login_id     VARCHAR(255)   PRIMARY KEY,
  expiredate   DATETIME       NOT NULL,
  is_logined   TINYINT(1)     NOT NULL DEFAULT 0,
  is_activated TINYINT(1)     NOT NULL DEFAULT 0,
  lie_detector TINYINT(1)    NOT NULL DEFAULT 0,
  added_date   DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_login   DATETIME       DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
ALTER TABLE users
ADD COLUMN session_count INT NOT NULL DEFAULT 0 AFTER lie_detector;




2012
--1달
INSERT INTO users (login_id, expiredate, is_logined, is_activated)
VALUES ('testuser', DATE_ADD(NOW(), INTERVAL 31 DAY), 0, 1);

--업데이트
UPDATE users
SET expiredate = DATE_ADD(NOW(), INTERVAL 3 DAY)
WHERE login_id = 'testuser';

--유저삭제
DELETE FROM users
WHERE login_id = 'testuser';

ALTER TABLE users
ADD COLUMN id INT AUTO_INCREMENT UNIQUE FIRST;

INSERT INTO users_backup (id, login_id, expiredate, is_logined, is_activated, added_date, last_login)
SELECT id, login_id, expiredate, is_logined, is_activated, added_date, last_login
FROM users;
백업

INSERT INTO table_stats (table_name, row_count, collected_at)
SELECT
    'users' AS table_name,
    COUNT(*) AS row_count,
    NOW() AS collected_at
FROM mapleJP_variousby.users;
유저수보기

INSERT INTO expired_user_ids (user_id, collected_at)
SELECT id, NOW()
FROM mapleJP_variousby.users
WHERE expiredate < NOW();
만료된계정수보기




미국2021
pw78o.h.filess.io
maplestoryUSA_softlyshot
3307
maplestoryUSA_softlyshot
65eb2f76dd16d294ddd911b811a23865683d1ffb
일본
mmh7q.h.filess.io
mapleJP_variousby
mapleJP_variousby
3307

ALTER TABLE `users`
  ADD COLUMN `lie_detector` TINYINT(1) NOT NULL DEFAULT 0 AFTER `is_activated`;

