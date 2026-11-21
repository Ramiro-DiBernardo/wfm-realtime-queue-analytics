-- 02_daily_sla_and_heatmap.sql
-- Daily service level per queue, and a weekday x hour heatmap to separate one-off incidents
-- from chronic gaps in the schedule.

DROP TABLE IF EXISTS daily_sla;
CREATE TABLE daily_sla AS
SELECT
    interval_date,
    weekday,
    queue,
    SUM(offered)                                             AS offered,
    SUM(abandoned)                                           AS abandoned,
    ROUND(1.0 * SUM(answered_in_sla) / SUM(offered), 3)      AS service_level,
    ROUND(1.0 * SUM(abandoned) / SUM(offered), 3)            AS abandon_rate,
    SUM(CASE WHEN rag_status = 'Red' THEN 1 ELSE 0 END)      AS red_intervals,
    ROUND(SUM(aht_sec * answered) / SUM(answered), 0)        AS aht_sec
FROM v_interval
GROUP BY interval_date, weekday, queue;

DROP TABLE IF EXISTS sl_heatmap;
CREATE TABLE sl_heatmap AS
SELECT
    queue,
    weekday_num,
    weekday,
    hour,
    SUM(offered)                                             AS offered,
    ROUND(1.0 * SUM(answered_in_sla) / NULLIF(SUM(offered), 0), 3) AS service_level,
    ROUND(AVG(staffing_gap), 2)                              AS avg_staffing_gap
FROM v_interval
-- leave out the days with a known one-off incident so the heatmap shows structural patterns only
WHERE interval_date NOT IN ('2026-10-12', '2026-10-20', '2026-10-27')
GROUP BY queue, weekday_num, weekday, hour;

-- chronic gaps: weekday-hour cells below target on most of the weeks
DROP TABLE IF EXISTS chronic_gaps;
CREATE TABLE chronic_gaps AS
WITH weekly AS (
    SELECT queue, weekday, hour, STRFTIME('%W', interval_date) AS week,
           1.0 * SUM(answered_in_sla) / NULLIF(SUM(offered), 0) AS sl,
           SUM(offered) AS offered
    FROM v_interval
    WHERE interval_date NOT IN ('2026-10-12', '2026-10-20', '2026-10-27') AND offered > 0
    GROUP BY queue, weekday, hour, week
)
SELECT queue, weekday, hour,
       COUNT(*)                                    AS weeks_observed,
       SUM(CASE WHEN sl < 0.80 THEN 1 ELSE 0 END)  AS weeks_below_target,
       ROUND(AVG(sl), 3)                           AS avg_service_level
FROM weekly
GROUP BY queue, weekday, hour
HAVING weeks_below_target >= 3 AND AVG(sl) < 0.75 AND AVG(offered) >= 40   -- ignore thin overnight cells
ORDER BY avg_service_level;
