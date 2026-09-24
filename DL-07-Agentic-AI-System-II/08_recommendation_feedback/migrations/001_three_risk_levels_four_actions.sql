-- Migration for databases created BEFORE the alignment with Contract Register v3.
-- db_schema.sql only runs on the first container start, so an existing pgdata
-- volume needs this script:
--   docker compose exec -T postgres psql -U reco_user -d reco_db < migrations/001_three_risk_levels_four_actions.sql
-- (In dev you can instead run `docker compose down -v` to start from scratch.)
--
--   risk_level : MODERATE -> MEDIUM, CRITICAL -> HIGH   (CRITICAL is removed)
--   action_code: EMERGENCY_INSTRUCTIONS -> AVOID_TRAVEL  (emergency content is
--                carried by emergency_instructions / official_contacts)
-- The JSON payload is rewritten too, because it embeds the same values
-- (top level and inside route options). The replace matches whole JSON
-- string values only ("MODERATE" with quotes).

BEGIN;

ALTER TABLE recommendation_log DROP CONSTRAINT IF EXISTS recommendation_log_risk_level_check;
ALTER TABLE recommendation_log DROP CONSTRAINT IF EXISTS recommendation_log_action_code_check;

UPDATE recommendation_log
SET risk_level = CASE risk_level WHEN 'MODERATE' THEN 'MEDIUM' WHEN 'CRITICAL' THEN 'HIGH' END
WHERE risk_level IN ('MODERATE', 'CRITICAL');

UPDATE recommendation_log
SET action_code = 'AVOID_TRAVEL'
WHERE action_code = 'EMERGENCY_INSTRUCTIONS';

UPDATE recommendation_log
SET payload = replace(replace(replace(payload::text,
        '"MODERATE"', '"MEDIUM"'),
        '"CRITICAL"', '"HIGH"'),
        '"EMERGENCY_INSTRUCTIONS"', '"AVOID_TRAVEL"')::jsonb
WHERE payload::text ~ '"(MODERATE|CRITICAL|EMERGENCY_INSTRUCTIONS)"';

ALTER TABLE recommendation_log
    ADD CONSTRAINT recommendation_log_risk_level_check
    CHECK (risk_level IN ('LOW','MEDIUM','HIGH'));
ALTER TABLE recommendation_log
    ADD CONSTRAINT recommendation_log_action_code_check
    CHECK (action_code IN ('TRAVEL_NORMALLY','CHANGE_ROUTE','DELAY_TRAVEL','AVOID_TRAVEL'));

COMMIT;
