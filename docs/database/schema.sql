
CREATE TABLE w5_academies (
	id VARCHAR(36) NOT NULL,
	name VARCHAR(100) NOT NULL,
	region VARCHAR(80) NOT NULL,
	phone VARCHAR(30),
	is_mock BOOL NOT NULL,
	hours JSON NOT NULL,
	PRIMARY KEY (id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin

;


CREATE TABLE w5_control (
	id VARCHAR(36) NOT NULL,
	PRIMARY KEY (id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin

;


CREATE TABLE w5_inquirers (
	id VARCHAR(36) NOT NULL,
	token_hash VARCHAR(64) NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (token_hash)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin

;


CREATE TABLE w5_mock_worker_receipts (
	call_id VARCHAR(36) NOT NULL,
	payload_hash VARCHAR(64) NOT NULL,
	payload JSON NOT NULL,
	received_at DATETIME NOT NULL,
	PRIMARY KEY (call_id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin

;


CREATE TABLE w5_academy_policies (
	academy_id VARCHAR(36) NOT NULL,
	enabled BOOL NOT NULL,
	max_concurrent INTEGER NOT NULL,
	cooldown_seconds INTEGER NOT NULL,
	closed_dates JSON NOT NULL,
	PRIMARY KEY (academy_id),
	FOREIGN KEY(academy_id) REFERENCES w5_academies (id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin

;


CREATE TABLE w5_inquiries (
	id VARCHAR(36) NOT NULL,
	inquirer_id VARCHAR(36) NOT NULL,
	academy_id VARCHAR(36) NOT NULL,
	request_key VARCHAR(80) NOT NULL,
	payload_hash VARCHAR(64) NOT NULL,
	student JSON NOT NULL,
	status VARCHAR(20) NOT NULL,
	priority INTEGER NOT NULL,
	created_at DATETIME NOT NULL,
	next_at DATETIME NOT NULL,
	failure_reason VARCHAR(80),
	fallback_required BOOL NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT w5_uq_request UNIQUE (inquirer_id, request_key),
	CONSTRAINT w5_ck_status CHECK (status IN ('queued','calling','retry_wait','completed','failed')),
	FOREIGN KEY(inquirer_id) REFERENCES w5_inquirers (id),
	FOREIGN KEY(academy_id) REFERENCES w5_academies (id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin

;


CREATE TABLE w6_accounts (
	user_id VARCHAR(36) NOT NULL,
	login_name VARCHAR(32) NOT NULL,
	password_hash VARCHAR(500) NOT NULL,
	`role` VARCHAR(16) NOT NULL,
	enabled BOOL NOT NULL,
	failed_logins INTEGER NOT NULL,
	locked_until DATETIME,
	PRIMARY KEY (user_id),
	FOREIGN KEY(user_id) REFERENCES w5_inquirers (id),
	UNIQUE (login_name)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin

;


CREATE TABLE w5_calls (
	id VARCHAR(36) NOT NULL,
	inquiry_id VARCHAR(36) NOT NULL,
	attempt_no INTEGER NOT NULL,
	status VARCHAR(30) NOT NULL,
	outcome VARCHAR(30),
	created_at DATETIME NOT NULL,
	last_event_at DATETIME,
	deadline DATETIME NOT NULL,
	dispatch_payload JSON NOT NULL,
	delivery_count INTEGER NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT w5_uq_attempt UNIQUE (inquiry_id, attempt_no),
	CONSTRAINT w5_ck_attempt CHECK (attempt_no > 0),
	FOREIGN KEY(inquiry_id) REFERENCES w5_inquiries (id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin

;


CREATE TABLE w5_questions (
	id VARCHAR(36) NOT NULL,
	inquiry_id VARCHAR(36) NOT NULL,
	code VARCHAR(30) NOT NULL,
	position INTEGER NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT w5_uq_question_code UNIQUE (inquiry_id, code),
	CONSTRAINT w5_uq_question_position UNIQUE (inquiry_id, position),
	FOREIGN KEY(inquiry_id) REFERENCES w5_inquiries (id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin

;


CREATE TABLE w6_fallback_tasks (
	inquiry_id VARCHAR(36) NOT NULL,
	status VARCHAR(30) NOT NULL,
	failure_reason VARCHAR(80) NOT NULL,
	message TEXT,
	created_at DATETIME NOT NULL,
	reviewed_at DATETIME,
	reviewer VARCHAR(100),
	review_reason VARCHAR(1000),
	dry_run_receipt JSON,
	PRIMARY KEY (inquiry_id),
	FOREIGN KEY(inquiry_id) REFERENCES w5_inquiries (id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin

;


CREATE TABLE w6_review_actions (
	id VARCHAR(36) NOT NULL,
	inquiry_id VARCHAR(36) NOT NULL,
	actor VARCHAR(100) NOT NULL,
	action VARCHAR(30) NOT NULL,
	reason VARCHAR(1000) NOT NULL,
	payload JSON NOT NULL,
	created_at DATETIME NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(inquiry_id) REFERENCES w5_inquiries (id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin

;


CREATE TABLE w6_sessions (
	token_hash VARCHAR(64) NOT NULL,
	id VARCHAR(36) NOT NULL,
	user_id VARCHAR(36) NOT NULL,
	created_at DATETIME NOT NULL,
	expires_at DATETIME NOT NULL,
	revoked BOOL NOT NULL,
	PRIMARY KEY (token_hash),
	UNIQUE (id),
	FOREIGN KEY(user_id) REFERENCES w6_accounts (user_id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin

;


CREATE TABLE w5_answers (
	call_id VARCHAR(36) NOT NULL,
	question_id VARCHAR(36) NOT NULL,
	asked BOOL NOT NULL,
	answered BOOL NOT NULL,
	yes_no BOOL,
	reason VARCHAR(30),
	detail TEXT NOT NULL,
	PRIMARY KEY (call_id, question_id),
	FOREIGN KEY(call_id) REFERENCES w5_calls (id),
	FOREIGN KEY(question_id) REFERENCES w5_questions (id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin

;


CREATE TABLE w5_delivery_leases (
	call_id VARCHAR(36) NOT NULL,
	claim_id VARCHAR(36) NOT NULL,
	lease_until DATETIME NOT NULL,
	PRIMARY KEY (call_id),
	FOREIGN KEY(call_id) REFERENCES w5_calls (id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin

;


CREATE TABLE w5_dispatch_outbox (
	id VARCHAR(36) NOT NULL,
	call_id VARCHAR(36) NOT NULL,
	created_at DATETIME NOT NULL,
	last_published_at DATETIME,
	PRIMARY KEY (id),
	UNIQUE (call_id),
	FOREIGN KEY(call_id) REFERENCES w5_calls (id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin

;


CREATE TABLE w5_events (
	id VARCHAR(80) NOT NULL,
	call_id VARCHAR(36) NOT NULL,
	type VARCHAR(30) NOT NULL,
	occurred_at DATETIME NOT NULL,
	received_at DATETIME NOT NULL,
	payload_hash VARCHAR(64) NOT NULL,
	applied BOOL NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(call_id) REFERENCES w5_calls (id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin

;


CREATE TABLE w5_results (
	call_id VARCHAR(36) NOT NULL,
	result_id VARCHAR(80) NOT NULL,
	payload_hash VARCHAR(64) NOT NULL,
	payload JSON NOT NULL,
	received_at DATETIME NOT NULL,
	applied BOOL NOT NULL,
	PRIMARY KEY (call_id),
	FOREIGN KEY(call_id) REFERENCES w5_calls (id),
	UNIQUE (result_id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin

;


CREATE TABLE w6_provider_calls (
	call_id VARCHAR(36) NOT NULL,
	provider VARCHAR(24) NOT NULL,
	external_id VARCHAR(100) NOT NULL,
	created_at DATETIME NOT NULL,
	PRIMARY KEY (call_id),
	CONSTRAINT w6_uq_provider_call UNIQUE (provider, external_id),
	FOREIGN KEY(call_id) REFERENCES w5_calls (id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin

;


CREATE TABLE w6_provider_inbox (
	id VARCHAR(64) NOT NULL,
	call_id VARCHAR(36) NOT NULL,
	type VARCHAR(60) NOT NULL,
	payload_hash VARCHAR(64) NOT NULL,
	status VARCHAR(30) NOT NULL,
	normalized JSON NOT NULL,
	error VARCHAR(100),
	received_at DATETIME NOT NULL,
	processed_at DATETIME,
	PRIMARY KEY (id),
	FOREIGN KEY(call_id) REFERENCES w5_calls (id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin

;


CREATE TABLE w6_review_holds (
	inquiry_id VARCHAR(36) NOT NULL,
	call_id VARCHAR(36) NOT NULL,
	reason VARCHAR(80) NOT NULL,
	open BOOL NOT NULL,
	created_at DATETIME NOT NULL,
	PRIMARY KEY (inquiry_id),
	FOREIGN KEY(inquiry_id) REFERENCES w5_inquiries (id),
	FOREIGN KEY(call_id) REFERENCES w5_calls (id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin

;


CREATE TABLE w5_result_corrections (
	id VARCHAR(36) NOT NULL,
	call_id VARCHAR(36) NOT NULL,
	revision INTEGER NOT NULL,
	reviewer VARCHAR(100) NOT NULL,
	reason VARCHAR(1000) NOT NULL,
	payload JSON NOT NULL,
	created_at DATETIME NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT w5_uq_correction_revision UNIQUE (call_id, revision),
	FOREIGN KEY(call_id) REFERENCES w5_results (call_id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin

;
