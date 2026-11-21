-- 03_anomaly_islands.sql
-- Detects incidents automatically: intervals where arrivals deviate strongly from forecast,
-- grouped into continuous episodes with the "gaps and islands" pattern (window functions).

DROP TABLE IF EXISTS anomaly_episodes;
CREATE TABLE anomaly_episodes AS
WITH flagged AS (
    SELECT interval_start, queue, offered, forecast_contacts, service_level, abandoned,
           CASE
               WHEN offered < 0.4 * forecast_contacts AND forecast_contacts >= 5 THEN 'Volume drop'
               WHEN offered > 1.3 * forecast_contacts AND offered - forecast_contacts >= 6 THEN 'Volume spike'
           END AS anomaly
    FROM v_interval
),
numbered AS (
    SELECT f.*,
           -- consecutive anomalous intervals of the same type share the same island id
           ROW_NUMBER() OVER (PARTITION BY queue ORDER BY interval_start)
         - ROW_NUMBER() OVER (PARTITION BY queue, anomaly ORDER BY interval_start) AS island
    FROM flagged f
)
SELECT
    queue,
    anomaly,
    MIN(interval_start)                                       AS episode_start,
    DATETIME(MAX(interval_start), '+15 minutes')              AS episode_end,
    COUNT(*)                                                  AS intervals,
    SUM(offered)                                              AS offered,
    ROUND(SUM(forecast_contacts), 0)                          AS forecast,
    ROUND(1.0 * SUM(offered) / SUM(forecast_contacts) - 1, 3) AS variance,
    SUM(abandoned)                                            AS abandoned
FROM numbered
WHERE anomaly IS NOT NULL
GROUP BY queue, anomaly, island
HAVING COUNT(*) >= 3                    -- ignore single noisy intervals: 45 min or more
ORDER BY episode_start;
