-- Back up and select the target database before applying, then deploy.
-- Nullable additions preserve existing answers. Safe to repeat after partial DDL.
SET @answer_condition_ddl = (
    SELECT IF(COUNT(*) = 0,
        'ALTER TABLE w5_answers ADD COLUMN `condition` VARCHAR(200) NULL',
        'SELECT 1')
    FROM information_schema.columns
    WHERE table_schema = DATABASE() AND table_name = 'w5_answers' AND column_name = 'condition'
);
PREPARE answer_condition_stmt FROM @answer_condition_ddl;
EXECUTE answer_condition_stmt;
DEALLOCATE PREPARE answer_condition_stmt;

SET @answer_reason_text_ddl = (
    SELECT IF(COUNT(*) = 0,
        'ALTER TABLE w5_answers ADD COLUMN reason_text VARCHAR(500) NULL',
        'SELECT 1')
    FROM information_schema.columns
    WHERE table_schema = DATABASE() AND table_name = 'w5_answers' AND column_name = 'reason_text'
);
PREPARE answer_reason_text_stmt FROM @answer_reason_text_ddl;
EXECUTE answer_reason_text_stmt;
DEALLOCATE PREPARE answer_reason_text_stmt;

SET @answer_evidence_turns_ddl = (
    SELECT IF(COUNT(*) = 0,
        'ALTER TABLE w5_answers ADD COLUMN evidence_turns JSON NULL',
        'SELECT 1')
    FROM information_schema.columns
    WHERE table_schema = DATABASE() AND table_name = 'w5_answers' AND column_name = 'evidence_turns'
);
PREPARE answer_evidence_turns_stmt FROM @answer_evidence_turns_ddl;
EXECUTE answer_evidence_turns_stmt;
DEALLOCATE PREPARE answer_evidence_turns_stmt;