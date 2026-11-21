-- 00_model.sql
-- One clean interval table that every other query reads from.
-- Inputs (loaded by scripts/run_analysis.py): raw_acd_interval, raw_wfm_staffing, interval_required
-- interval_required holds the Erlang C requirement for the contacts that actually arrived (computed in Python).
-- Dialect: SQLite. The same logic runs on PostgreSQL (Metabase) by swapping strftime() for EXTRACT()/TO_CHAR().

DROP TABLE IF EXISTS fact_interval;
CREATE TABLE fact_interval AS
SELECT
    a.interval_start,
    DATE(a.interval_start)                                  AS interval_date,
    CAST(STRFTIME('%H', a.interval_start) AS INTEGER)       AS hour,
    STRFTIME('%H:%M', a.interval_start)                     AS time_of_day,
    CAST(STRFTIME('%w', a.interval_start) AS INTEGER)       AS weekday_num,   -- 0 = Sunday
    CASE CAST(STRFTIME('%w', a.interval_start) AS INTEGER)
        WHEN 0 THEN 'Sun' WHEN 1 THEN 'Mon' WHEN 2 THEN 'Tue' WHEN 3 THEN 'Wed'
        WHEN 4 THEN 'Thu' WHEN 5 THEN 'Fri' ELSE 'Sat' END  AS weekday,
    a.queue,
    a.channel,
    CAST(w.forecast_contacts AS REAL)   AS forecast_contacts,
    CAST(a.offered AS INTEGER)          AS offered,
    CAST(a.answered AS INTEGER)         AS answered,
    CAST(a.abandoned AS INTEGER)        AS abandoned,
    CAST(a.answered_in_sla AS INTEGER)  AS answered_in_sla,
    CAST(a.sla_target_sec AS INTEGER)   AS sla_target_sec,
    CAST(NULLIF(a.aht_sec, '') AS REAL) AS aht_sec,
    CAST(w.forecast_aht_sec AS REAL)    AS forecast_aht_sec,
    CAST(w.scheduled_agents AS INTEGER) AS scheduled_agents,
    CAST(w.staffed_agents AS INTEGER)   AS staffed_agents,
    r.required_agents
FROM raw_acd_interval a
JOIN raw_wfm_staffing w ON w.interval_start = a.interval_start AND w.queue = a.queue
JOIN interval_required r ON r.interval_start = a.interval_start AND r.queue = a.queue;

-- derived metrics in a view, so the base table stays additive (sum-able) like a Metabase model
DROP VIEW IF EXISTS v_interval;
CREATE VIEW v_interval AS
SELECT
    f.*,
    1.0 * answered_in_sla / NULLIF(offered, 0)                         AS service_level,
    1.0 * abandoned / NULLIF(offered, 0)                               AS abandon_rate,
    1.0 * (offered - forecast_contacts) / NULLIF(forecast_contacts, 0) AS forecast_variance,
    staffed_agents - required_agents                                   AS staffing_gap,
    CASE
        WHEN offered = 0 THEN 'No volume'
        WHEN 1.0 * answered_in_sla / offered >= 0.80 THEN 'Green'
        WHEN 1.0 * answered_in_sla / offered >= 0.65 THEN 'Amber'
        ELSE 'Red'
    END                                                                AS rag_status
FROM fact_interval f;
