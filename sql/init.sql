-- 1. 关闭外键检查，清空旧表
SET FOREIGN_KEY_CHECKS = 0;

DROP TABLE IF EXISTS plan_history;
DROP TABLE IF EXISTS consumption;
DROP TABLE IF EXISTS grades;
DROP TABLE IF EXISTS student_profile;
DROP TABLE IF EXISTS users;   -- 改成 users
DROP TABLE IF EXISTS iot;

SET FOREIGN_KEY_CHECKS = 1;

-- 2. 用户表（改名叫 users，避开关键字）
CREATE TABLE users (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    username VARCHAR(50) NOT NULL UNIQUE,
    password VARCHAR(100) NOT NULL,
    role VARCHAR(20) DEFAULT 'student',
    create_time DATETIME DEFAULT NOW()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 3. 学生信息（外键指向 users.id，类型完全一致 BIGINT）
CREATE TABLE student_profile (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id BIGINT NOT NULL,
    student_id VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(50),
    grade VARCHAR(50),
    major VARCHAR(100),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 4. 成绩
CREATE TABLE grades (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    student_id VARCHAR(50) NOT NULL,
    subject VARCHAR(50) NOT NULL,
    score FLOAT NOT NULL,
    failed INT DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 5. 消费
CREATE TABLE consumption (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    student_id VARCHAR(50) NOT NULL,
    category VARCHAR(50),
    amount FLOAT NOT NULL,
    create_time DATETIME DEFAULT NOW()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 6. 自习IoT
CREATE TABLE iot (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    floor INT,
    hour INT,
    traffic INT,
    co2 FLOAT,
    temp FLOAT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 7. 规划历史
CREATE TABLE plan_history (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    student_id VARCHAR(50) NOT NULL,
    request TEXT NOT NULL,
    plan TEXT NOT NULL,
    conflict_log TEXT,
    create_time DATETIME DEFAULT NOW()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ----------------------
-- 插入测试数据（直接可用）
-- ----------------------
-- 插入用户（users）
INSERT INTO users (username, password, role) VALUES
('stu001', '123456', 'student'),
('stu002', '123456', 'student'),
('admin', 'admin123', 'admin');

-- 插入学生信息
INSERT INTO student_profile (user_id, student_id, name, grade, major) VALUES
(1, '2026001', '张三', '2026级', '计算机科学与技术'),
(2, '2026002', '李四', '2026级', '人工智能');

-- 插入成绩
INSERT INTO grades (student_id, subject, score, failed) VALUES
('2026001', '高等数学', 88.5, 0),
('2026001', 'Java程序设计', 92.0, 0),
('2026002', '高等数学', 59.0, 1);

-- 插入消费
INSERT INTO consumption (student_id, category, amount) VALUES
('2026001', '食堂', 15.5),
('2026001', '超市', 32.0),
('2026002', '水费', 20.0);

-- 插入IoT
INSERT INTO iot (floor, hour, traffic, co2, temp) VALUES
(3, 9, 45, 420.5, 25.3),
(3, 14, 78, 510.2, 26.1),
(4, 10, 22, 380.0, 24.8);

-- 插入规划历史
INSERT INTO plan_history (student_id, request, plan, conflict_log) VALUES
('2026001', '帮我规划本周学习和自习', '周一~周五：白天上课，晚上3-4楼自习；周末上午刷题，下午休息', '无冲突');