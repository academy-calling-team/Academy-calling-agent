-- Back up and select the target database before applying, then deploy.
-- Safe to repeat after a partial DDL failure.
SET @academy_account_type_ddl = (
    SELECT IF(COUNT(*) = 0,
        'ALTER TABLE w6_accounts ADD COLUMN account_type VARCHAR(16) NOT NULL DEFAULT ''parent''',
        'SELECT 1')
    FROM information_schema.columns
    WHERE table_schema = DATABASE() AND table_name = 'w6_accounts' AND column_name = 'account_type'
);
PREPARE academy_account_type_stmt FROM @academy_account_type_ddl;
EXECUTE academy_account_type_stmt;
DEALLOCATE PREPARE academy_account_type_stmt;

CREATE TABLE IF NOT EXISTS w6_academy_profiles (
    academy_id VARCHAR(36) NOT NULL,
    owner_id VARCHAR(36) NOT NULL,
    address VARCHAR(160) NOT NULL,
    PRIMARY KEY (academy_id),
    UNIQUE (owner_id),
    FOREIGN KEY (academy_id) REFERENCES w5_academies (id),
    FOREIGN KEY (owner_id) REFERENCES w6_accounts (user_id)
) ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin;
