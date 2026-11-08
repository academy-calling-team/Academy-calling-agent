-- 학원 설정 스키마 적용. 대상 DB 선택 및 백업 후 배포 전에 실행.
-- DDL 자동 커밋. 중간 실패 시 완료된 문장을 건너뛰고 다시 실행 가능.
CREATE TABLE IF NOT EXISTS w5_academy_classes (
	id VARCHAR(36) NOT NULL,
	academy_id VARCHAR(36) NOT NULL,
	grade_code VARCHAR(10) NOT NULL,
	subject_code VARCHAR(10) NOT NULL,
	level_code VARCHAR(10),
	created_at DATETIME NOT NULL,
	updated_at DATETIME NOT NULL,
	PRIMARY KEY (id),
	KEY ix_w5_academy_classes_academy_id (academy_id),
	FOREIGN KEY(academy_id) REFERENCES w5_academies (id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin;

CREATE TABLE IF NOT EXISTS w5_academy_call_hours (
	id INTEGER NOT NULL AUTO_INCREMENT,
	academy_id VARCHAR(36) NOT NULL,
	day_of_week INTEGER NOT NULL,
	start_time TIME NOT NULL,
	end_time TIME NOT NULL,
	created_at DATETIME NOT NULL,
	PRIMARY KEY (id),
	KEY ix_w5_academy_call_hours_academy_id (academy_id),
	FOREIGN KEY(academy_id) REFERENCES w5_academies (id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin;

CREATE TABLE IF NOT EXISTS w5_academy_setting_states (
	academy_id VARCHAR(36) NOT NULL,
	is_class_configured BOOL NOT NULL,
	is_call_hours_configured BOOL NOT NULL,
	last_modified_at DATETIME NOT NULL,
	version INTEGER NOT NULL,
	PRIMARY KEY (academy_id),
	FOREIGN KEY(academy_id) REFERENCES w5_academies (id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin;

-- 초기 초안 적용 DB의 필수 수준 열 보완.
SET @academy_priority_ddl = IF(
    EXISTS (
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'w5_academy_classes'
          AND COLUMN_NAME = 'level_code'
          AND IS_NULLABLE = 'NO'
    ),
    'ALTER TABLE w5_academy_classes MODIFY COLUMN level_code VARCHAR(10) NULL',
    'SELECT 1'
);
PREPARE academy_priority_stmt FROM @academy_priority_ddl;
EXECUTE academy_priority_stmt;
DEALLOCATE PREPARE academy_priority_stmt;

-- Preserve rows from the earlier PR draft and allow inserts without its retired field.
SET @academy_priority_ddl = IF(
    EXISTS (
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'w5_academy_classes'
          AND COLUMN_NAME = 'status'
          AND IS_NULLABLE = 'NO'
    ),
    'ALTER TABLE w5_academy_classes MODIFY COLUMN status VARCHAR(20) NULL',
    'SELECT 1'
);
PREPARE academy_priority_stmt FROM @academy_priority_ddl;
EXECUTE academy_priority_stmt;
DEALLOCATE PREPARE academy_priority_stmt;
