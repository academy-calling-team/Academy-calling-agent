-- Optional source excerpt on existing question answers.
SET @voice_answer_ddl = IF(
    EXISTS (
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'w5_answers'
          AND COLUMN_NAME = 'source_text'
    ),
    'SELECT 1',
    'ALTER TABLE w5_answers ADD COLUMN source_text TEXT NULL'
);
PREPARE voice_answer_stmt FROM @voice_answer_ddl;
EXECUTE voice_answer_stmt;
DEALLOCATE PREPARE voice_answer_stmt;
