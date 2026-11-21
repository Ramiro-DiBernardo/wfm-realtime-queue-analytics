-- 05_agent_state_audit.sql
-- Forensic audit of agent states (last 2 weeks): hidden capacity drains such as excessive "On Hold",
-- long after-call work, micro "Not Ready" breaks and schedule adherence.
-- Each agent is compared with the peers of the same team (z-score), so team-level AHT differences
-- do not create false positives.

DROP TABLE IF EXISTS agent_shift_adherence;
CREATE TABLE agent_shift_adherence AS
SELECT
    s.agent_id,
    s.shift_date,
    (JULIANDAY(MIN(st.start_time)) - JULIANDAY(s.scheduled_start)) * 1440  AS login_delay_min,
    (JULIANDAY(s.scheduled_end) - JULIANDAY(MAX(st.end_time))) * 1440      AS early_logout_min
FROM raw_schedules s
JOIN raw_agent_status st
  ON st.agent_id = s.agent_id
 AND st.start_time >= DATETIME(s.scheduled_start, '-2 hours')
 AND st.start_time <  DATETIME(s.scheduled_end, '+2 hours')
GROUP BY s.agent_id, s.shift_date;

DROP TABLE IF EXISTS agent_audit;
CREATE TABLE agent_audit AS
WITH per_agent AS (
    SELECT
        a.agent_id,
        a.team,
        COUNT(DISTINCT DATE(st.start_time))                                              AS shifts,
        -- contacts = handling segments that do not resume after a hold
        SUM(CASE WHEN st.status = 'After Call Work' THEN 1 ELSE 0 END)                   AS contacts,
        SUM(CASE WHEN st.status = 'On Hold' THEN 1 ELSE 0 END)                           AS holds,
        SUM(CASE WHEN st.status = 'On Hold' THEN st.duration_sec ELSE 0 END)             AS hold_sec,
        SUM(CASE WHEN st.status = 'Handling' THEN st.duration_sec ELSE 0 END)            AS handle_sec,
        SUM(CASE WHEN st.status = 'After Call Work' THEN st.duration_sec ELSE 0 END)     AS acw_sec,
        SUM(CASE WHEN st.status = 'Not Ready' THEN 1 ELSE 0 END)                         AS not_ready_events,
        SUM(CASE WHEN st.status = 'Not Ready' THEN st.duration_sec ELSE 0 END)           AS not_ready_sec,
        SUM(CASE WHEN st.status <> 'Offline' THEN st.duration_sec ELSE 0 END)            AS logged_sec
    FROM raw_agents a
    JOIN raw_agent_status st ON st.agent_id = a.agent_id
    GROUP BY a.agent_id, a.team
),
metrics AS (
    SELECT p.*,
           1.0 * holds / contacts                                AS hold_rate,
           1.0 * hold_sec / NULLIF(holds, 0)                     AS avg_hold_sec,
           1.0 * acw_sec / contacts                              AS avg_acw_sec,
           1.0 * not_ready_sec / logged_sec                      AS not_ready_share,
           1.0 * (handle_sec + hold_sec + acw_sec) / contacts    AS aht_sec,
           (SELECT AVG(login_delay_min)  FROM agent_shift_adherence h WHERE h.agent_id = p.agent_id) AS avg_login_delay_min,
           (SELECT AVG(early_logout_min) FROM agent_shift_adherence h WHERE h.agent_id = p.agent_id) AS avg_early_logout_min
    FROM per_agent p
),
team_stats AS (
    SELECT team,
           AVG(hold_rate) AS m_hold, SQRT(AVG(hold_rate * hold_rate) - AVG(hold_rate) * AVG(hold_rate)) AS s_hold,
           AVG(avg_hold_sec) AS m_hlen, SQRT(AVG(avg_hold_sec * avg_hold_sec) - AVG(avg_hold_sec) * AVG(avg_hold_sec)) AS s_hlen,
           AVG(avg_acw_sec) AS m_acw, SQRT(AVG(avg_acw_sec * avg_acw_sec) - AVG(avg_acw_sec) * AVG(avg_acw_sec)) AS s_acw,
           AVG(not_ready_share) AS m_nr, SQRT(AVG(not_ready_share * not_ready_share) - AVG(not_ready_share) * AVG(not_ready_share)) AS s_nr,
           AVG(avg_login_delay_min + avg_early_logout_min) AS m_adh,
           SQRT(AVG((avg_login_delay_min + avg_early_logout_min) * (avg_login_delay_min + avg_early_logout_min))
                - AVG(avg_login_delay_min + avg_early_logout_min) * AVG(avg_login_delay_min + avg_early_logout_min)) AS s_adh
    FROM metrics
    GROUP BY team
)
SELECT
    m.agent_id, m.team, m.shifts, m.contacts,
    ROUND(m.hold_rate, 3)              AS hold_rate,
    ROUND(m.avg_hold_sec, 0)           AS avg_hold_sec,
    ROUND(m.avg_acw_sec, 0)            AS avg_acw_sec,
    m.not_ready_events,
    ROUND(m.not_ready_share, 3)        AS not_ready_share,
    ROUND(m.aht_sec, 0)                AS aht_sec,
    ROUND(m.avg_login_delay_min, 1)    AS avg_login_delay_min,
    ROUND(m.avg_early_logout_min, 1)   AS avg_early_logout_min,
    ROUND((m.hold_rate - t.m_hold) / NULLIF(t.s_hold, 0), 1)       AS z_hold_rate,
    ROUND((m.avg_hold_sec - t.m_hlen) / NULLIF(t.s_hlen, 0), 1)    AS z_hold_length,
    ROUND((m.avg_acw_sec - t.m_acw) / NULLIF(t.s_acw, 0), 1)       AS z_acw,
    ROUND((m.not_ready_share - t.m_nr) / NULLIF(t.s_nr, 0), 1)     AS z_not_ready,
    ROUND((m.avg_login_delay_min + m.avg_early_logout_min - t.m_adh) / NULLIF(t.s_adh, 0), 1) AS z_adherence,
    TRIM(
        CASE WHEN (m.hold_rate - t.m_hold) / t.s_hold > 2.5 OR (m.avg_hold_sec - t.m_hlen) / t.s_hlen > 2.5 THEN 'Hold pattern; ' ELSE '' END ||
        CASE WHEN (m.avg_acw_sec - t.m_acw) / t.s_acw > 2.5 THEN 'Long ACW; ' ELSE '' END ||
        CASE WHEN (m.not_ready_share - t.m_nr) / NULLIF(t.s_nr, 0) > 2.5 THEN 'Not Ready drain; ' ELSE '' END ||
        CASE WHEN (m.avg_login_delay_min + m.avg_early_logout_min - t.m_adh) / t.s_adh > 2.5 THEN 'Adherence; ' ELSE '' END
    , '; ')                            AS audit_flag,
    -- productive minutes lost per shift compared with the team average (the "hidden capacity drain")
    ROUND((MAX(m.hold_rate * m.avg_hold_sec - t.m_hold * t.m_hlen, 0) * m.contacts
           + MAX(m.avg_acw_sec - t.m_acw, 0) * m.contacts
           + MAX(m.not_ready_share - t.m_nr, 0) * 8 * 3600 * m.shifts
           + MAX(m.avg_login_delay_min + m.avg_early_logout_min - t.m_adh, 0) * 60 * m.shifts) / 60.0 / m.shifts, 0)
                                       AS excess_min_per_shift
FROM metrics m
JOIN team_stats t ON t.team = m.team
ORDER BY excess_min_per_shift DESC;
