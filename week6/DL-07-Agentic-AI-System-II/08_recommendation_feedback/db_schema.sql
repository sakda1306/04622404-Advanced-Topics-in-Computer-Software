-- Module: 08_recommendation_feedback
-- Runs automatically on first Postgres container start
-- (mounted via docker-entrypoint-initdb.d in docker-compose.yml).

CREATE TABLE IF NOT EXISTS recommendation_log (
    request_id            TEXT PRIMARY KEY,
    schema_version         TEXT NOT NULL,
    -- Same 4 action codes / 3 risk levels as 02, 06, 07 (Contract Register v3).
    action_code             TEXT NOT NULL
                                 CONSTRAINT recommendation_log_action_code_check
                                 CHECK (action_code IN ('TRAVEL_NORMALLY','CHANGE_ROUTE',
                                                        'DELAY_TRAVEL','AVOID_TRAVEL')),
    risk_level              TEXT NOT NULL
                                 CONSTRAINT recommendation_log_risk_level_check
                                 CHECK (risk_level IN ('LOW','MEDIUM','HIGH')),
    -- Nullable: Module 07 currently emits confidence as LOW/MEDIUM/HIGH
    -- (see confidence_level below), not a 0-1 number. See README.
    confidence              NUMERIC(4,3) CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
    confidence_level        TEXT CHECK (confidence_level IS NULL OR confidence_level IN ('LOW','MEDIUM','HIGH')),
    short_summary           TEXT NOT NULL,
    observed_at             TIMESTAMPTZ NOT NULL,
    fetched_at              TIMESTAMPTZ NOT NULL,
    expires_at              TIMESTAMPTZ NOT NULL,
    pseudonymous_user_id    TEXT NOT NULL,
    payload                 JSONB NOT NULL,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_recommendation_log_user
    ON recommendation_log (pseudonymous_user_id);

CREATE INDEX IF NOT EXISTS idx_recommendation_log_created_at
    ON recommendation_log (created_at);


CREATE TABLE IF NOT EXISTS user_feedback (
    feedback_id             BIGSERIAL PRIMARY KEY,
    request_id              TEXT NOT NULL REFERENCES recommendation_log(request_id),
    pseudonymous_user_id    TEXT NOT NULL,
    category                TEXT NOT NULL CHECK (
                                 category IN ('HELPFUL','INCORRECT','STALE',
                                              'UNSAFE','ROUTE_ISSUE','SOURCE_ISSUE')
                             ),
    comment                 TEXT,
    submitted_at            TIMESTAMPTZ NOT NULL,
    escalated_to_safety     BOOLEAN NOT NULL DEFAULT FALSE,
    reviewed                BOOLEAN NOT NULL DEFAULT FALSE,
    reviewed_at             TIMESTAMPTZ,
    reviewed_by             TEXT,
    approved_for_training   BOOLEAN NOT NULL DEFAULT FALSE,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_user_feedback_request
    ON user_feedback (request_id);

CREATE INDEX IF NOT EXISTS idx_user_feedback_unreviewed
    ON user_feedback (reviewed) WHERE reviewed = FALSE;

-- Retention: rows older than FEEDBACK_RETENTION_DAYS (see .env) should be
-- purged/anonymized by a scheduled job, e.g.:
-- DELETE FROM recommendation_log WHERE created_at < now() - INTERVAL '180 days';
