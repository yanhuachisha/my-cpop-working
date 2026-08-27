ALTER TABLE agent_message ADD COLUMN trace_id VARCHAR(64) NULL AFTER token_count;
ALTER TABLE user_action ADD COLUMN trace_id VARCHAR(64) NULL AFTER idempotency_key;
