-- 04_forecast_and_staffing_cost.sql
-- Forecast accuracy, and the money side of protecting SLA: how many paid agent-hours sat idle above
-- the Erlang C requirement, and how many hours we were short (where SL and abandonment suffer).
-- Cost assumption: USD 14 per fully loaded agent-hour (set in the params CTE).

DROP TABLE IF EXISTS forecast_accuracy;
CREATE TABLE forecast_accuracy AS
SELECT
    queue,
    ROUND(SUM(ABS(offered - forecast_contacts)) / SUM(offered), 3)  AS interval_wape,
    ROUND((SUM(offered) - SUM(forecast_contacts)) / SUM(forecast_contacts), 3) AS bias,
    (SELECT ROUND(SUM(ABS(d.offered - d.forecast)) / SUM(d.offered), 3)
     FROM (SELECT interval_date, SUM(offered) AS offered, SUM(forecast_contacts) AS forecast
           FROM v_interval v2 WHERE v2.queue = v.queue GROUP BY interval_date) d) AS daily_wape
FROM v_interval v
GROUP BY queue;

DROP TABLE IF EXISTS staffing_cost;
CREATE TABLE staffing_cost AS
WITH params AS (SELECT 14.0 AS cost_per_agent_hour),
gaps AS (
    SELECT queue, interval_date,
           SUM(CASE WHEN staffing_gap > 0 THEN staffing_gap ELSE 0 END) * 0.25  AS surplus_hours,
           SUM(CASE WHEN staffing_gap < 0 THEN -staffing_gap ELSE 0 END) * 0.25 AS shortfall_hours,
           SUM(staffed_agents) * 0.25                                         AS staffed_hours,
           SUM(CASE WHEN staffing_gap < 0 THEN abandoned ELSE 0 END)           AS abandons_when_short
    FROM v_interval
    GROUP BY queue, interval_date
)
SELECT
    g.queue,
    ROUND(SUM(g.staffed_hours), 0)                                AS staffed_hours,
    ROUND(SUM(g.surplus_hours), 0)                                AS surplus_hours,
    ROUND(SUM(g.shortfall_hours), 0)                              AS shortfall_hours,
    ROUND(SUM(g.surplus_hours) / SUM(g.staffed_hours), 3)         AS surplus_share,
    ROUND(SUM(g.surplus_hours) * p.cost_per_agent_hour, 0)        AS surplus_cost_usd,
    SUM(g.abandons_when_short)                                    AS abandons_when_short
FROM gaps g, params p
GROUP BY g.queue;
