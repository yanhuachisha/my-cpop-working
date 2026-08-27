CREATE TABLE IF NOT EXISTS agent_memory (
  id CHAR(36) PRIMARY KEY,
  tenant_id VARCHAR(80) NOT NULL,
  user_id VARCHAR(80) NOT NULL,
  memory_key CHAR(64) NOT NULL,
  memory_type VARCHAR(40) NOT NULL,
  active_version INT NOT NULL DEFAULT 0,
  created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY uk_memory_identity (tenant_id, user_id, memory_key),
  KEY idx_memory_user_updated (tenant_id, user_id, updated_at)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS memory_version (
  memory_id CHAR(36) NOT NULL,
  version INT NOT NULL,
  subject VARCHAR(200) NOT NULL,
  predicate VARCHAR(100) NOT NULL,
  object_value TEXT NOT NULL,
  confidence DECIMAL(5,4) NOT NULL,
  valid_from TIMESTAMP(6) NULL,
  expires_at TIMESTAMP(6) NULL,
  active BOOLEAN NOT NULL,
  trace_id VARCHAR(64),
  created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (memory_id, version),
  KEY idx_memory_version_active (memory_id, active),
  CONSTRAINT fk_version_memory FOREIGN KEY (memory_id) REFERENCES agent_memory(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS memory_source_relation (
  memory_id CHAR(36) NOT NULL,
  version INT NOT NULL,
  source_message_id VARCHAR(100) NOT NULL,
  PRIMARY KEY (memory_id, version, source_message_id),
  CONSTRAINT fk_source_version FOREIGN KEY (memory_id, version) REFERENCES memory_version(memory_id, version)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS outbox_event (
  id CHAR(36) PRIMARY KEY,
  aggregate_type VARCHAR(40) NOT NULL,
  aggregate_id CHAR(36) NOT NULL,
  aggregate_version INT NOT NULL,
  event_type VARCHAR(100) NOT NULL,
  payload JSON NOT NULL,
  trace_id VARCHAR(64),
  occurred_at TIMESTAMP(6) NOT NULL,
  KEY idx_outbox_aggregate (aggregate_type, aggregate_id, aggregate_version),
  KEY idx_outbox_occurred (occurred_at)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS idempotency_record (
  idempotency_key VARCHAR(160) PRIMARY KEY,
  resource_id CHAR(36) NOT NULL,
  resource_version INT NOT NULL,
  created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS agent_session (
  id VARCHAR(80) PRIMARY KEY, tenant_id VARCHAR(80) NOT NULL, user_id VARCHAR(80) NOT NULL,
  title VARCHAR(120), created_at TIMESTAMP(6) NOT NULL, updated_at TIMESTAMP(6) NOT NULL,
  KEY idx_session_user (tenant_id, user_id, updated_at)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS agent_message (
  id VARCHAR(100) PRIMARY KEY, session_id VARCHAR(80) NOT NULL, role VARCHAR(20) NOT NULL,
  content MEDIUMTEXT NOT NULL, token_count INT NOT NULL DEFAULT 0, created_at TIMESTAMP(6) NOT NULL,
  KEY idx_message_session (session_id, created_at),
  CONSTRAINT fk_message_session FOREIGN KEY (session_id) REFERENCES agent_session(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS user_action (
  action_id CHAR(36) PRIMARY KEY,
  tenant_id VARCHAR(80) NOT NULL,
  user_id VARCHAR(80) NOT NULL,
  action_type VARCHAR(40) NOT NULL,
  payload JSON NOT NULL,
  idempotency_key VARCHAR(160) NOT NULL,
  created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  UNIQUE KEY uk_user_action_idempotency (idempotency_key),
  KEY idx_user_action_user_time (tenant_id, user_id, created_at)
) ENGINE=InnoDB;
