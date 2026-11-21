-- 06_incident_timeline.sql
-- Interval-by-interval view of the voice queues on 20 Oct 2026 (telephony outage and rebound),
-- the raw material for the stakeholder incident update in docs/.

DROP TABLE IF EXISTS incident_timeline;
CREATE TABLE incident_timeline AS
SELECT
    interval_start,
    time_of_day,
    SUM(offered)                                              AS offered,
    ROUND(SUM(forecast_contacts), 0)                          AS forecast,
    SUM(abandoned)                                            AS abandoned,
    ROUND(1.0 * SUM(answered_in_sla) / NULLIF(SUM(offered), 0), 3) AS service_level,
    SUM(staffed_agents)                                       AS staffed_agents,
    SUM(required_agents)                                      AS required_agents
FROM v_interval
WHERE channel = 'Voice'
  AND interval_start >= '2026-10-20 11:00' AND interval_start < '2026-10-20 19:00'
GROUP BY interval_start, time_of_day
ORDER BY interval_start;
