-- Back up and select the target database before applying, then deploy.
-- Nullable additions preserve existing questions. Safe to repeat after partial DDL.
SET @question_location_kind_ddl = (
    SELECT IF(COUNT(*) = 0,
        'ALTER TABLE w5_questions ADD COLUMN location_kind VARCHAR(20) NULL',
        'SELECT 1')
    FROM information_schema.columns
    WHERE table_schema = DATABASE() AND table_name = 'w5_questions' AND column_name = 'location_kind'
);
PREPARE question_location_kind_stmt FROM @question_location_kind_ddl;
EXECUTE question_location_kind_stmt;
DEALLOCATE PREPARE question_location_kind_stmt;

SET @question_location_name_ddl = (
    SELECT IF(COUNT(*) = 0,
        'ALTER TABLE w5_questions ADD COLUMN location_name VARCHAR(100) NULL',
        'SELECT 1')
    FROM information_schema.columns
    WHERE table_schema = DATABASE() AND table_name = 'w5_questions' AND column_name = 'location_name'
);
PREPARE question_location_name_stmt FROM @question_location_name_ddl;
EXECUTE question_location_name_stmt;
DEALLOCATE PREPARE question_location_name_stmt;
