-- 01_realtime_queue_board.sql
-- What a real-time analyst looks at every 15 minutes: the latest interval per queue, the trend over the
-- last hour, and the lever to pull. In Metabase, {{as_of}} becomes a variable; here it is a one-row CTE.

DROP TABLE IF EXISTS rt_queue_board;
CREATE TABLE rt_queue_board AS
WITH params AS (SELECT '2026-10-20 15:00' AS as_of),          -- {{as_of}} in Metabase
last_hour AS (
    SELECT v.*
    FROM v_interval v, params p
    WHERE v.interval_start >  DATETIME(p.as_of, '-60 minutes')
      AND v.interval_start <= p.as_of
),
rollup AS (
    SELECT queue,
           SUM(offered)                                          AS offered_1h,
           ROUND(SUM(forecast_contacts), 0)                      AS forecast_1h,
           1.0 * SUM(answered_in_sla) / NULLIF(SUM(offered), 0)  AS sl_1h,
           1.0 * SUM(abandoned) / NULLIF(SUM(offered), 0)        AS abandon_1h
    FROM last_hour
    GROUP BY queue
),
latest AS (
    SELECT v.* FROM v_interval v, params p WHERE v.interval_start = p.as_of
)
SELECT
    l.queue,
    l.interval_start                                AS as_of,
    l.offered                                       AS offered_now,
    ROUND(l.forecast_contacts, 0)                   AS forecast_now,
    ROUND(l.service_level, 3)                       AS sl_now,
    ROUND(r.sl_1h, 3)                               AS sl_last_hour,
    ROUND(r.abandon_1h, 3)                          AS abandon_last_hour,
    ROUND(1.0 * (r.offered_1h - r.forecast_1h) / NULLIF(r.forecast_1h, 0), 3) AS volume_vs_forecast_1h,
    l.staffed_agents,
    l.required_agents,
    l.staffing_gap,
    l.rag_status,
    CASE
        WHEN l.rag_status = 'Red'   AND l.staffing_gap < 0 AND r.offered_1h > 1.2 * r.forecast_1h
            THEN 'Unplanned volume: pull cross-skilled agents, move off-phone work, offer voluntary OT'
        WHEN l.rag_status = 'Red'   AND l.staffing_gap < 0
            THEN 'Under-staffed vs plan: cancel off-phone activities (meetings, coaching), check absences'
        WHEN l.rag_status = 'Amber' AND l.staffing_gap < 0
            THEN 'Slipping and under-staffed: cancel off-phone work before it turns red'
        WHEN l.rag_status IN ('Red', 'Amber') AND l.staffing_gap >= 0
            THEN 'Staffed to need but missing SL: audit AHT, holds and agent states'
        WHEN l.rag_status = 'Green' AND l.staffing_gap >= 3
            THEN 'Surplus capacity: release to training / back-office or lend to another queue'
        ELSE 'No action'
    END                                             AS recommended_lever
FROM latest l
JOIN rollup r ON r.queue = l.queue
ORDER BY l.service_level;
