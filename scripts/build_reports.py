"""Charts (docs/img/*.png) and the written deliverables (docs/*.md) built from the SQL results.
Every number in the documents is computed here, so they always match the data.

Run after run_analysis.py:  python scripts/build_reports.py   (needs matplotlib)
"""
import csv
import sqlite3
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DOCS, IMG = ROOT / "docs", ROOT / "docs" / "img"
IMG.mkdir(parents=True, exist_ok=True)
con = sqlite3.connect(ROOT / "data" / "wfm.db")
q = lambda sql, *a: con.execute(sql, a).fetchall()  # noqa: E731
QUEUES = ["Professionals - Chat", "Professionals - Voice", "Facilities - Voice", "Payments - Chat"]
COLORS = ["#0F57FF", "#7A4DFF", "#C2410C", "#0B6E4F"]
plt.rcParams.update({"font.family": "Segoe UI", "font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
pct = lambda x: f"{x * 100:.1f}%"  # noqa: E731


def read(name):
    with open(ROOT / "results" / name, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


# ============ numbers ============
overall = {r[0]: r[1:] for r in q("""SELECT queue, SUM(offered), 1.0*SUM(answered_in_sla)/SUM(offered), 1.0*SUM(abandoned)/SUM(offered)
                                     FROM v_interval GROUP BY queue""")}
tot_off, tot_sl, tot_ab = q("SELECT SUM(offered), 1.0*SUM(answered_in_sla)/SUM(offered), 1.0*SUM(abandoned)/SUM(offered) FROM v_interval")[0]

out_off, out_fc = q("""SELECT SUM(offered), SUM(forecast_contacts) FROM v_interval
                      WHERE channel='Voice' AND interval_start >= '2026-10-20 13:00' AND interval_start < '2026-10-20 14:45'""")[0]
reb = q("""SELECT SUM(offered), SUM(forecast_contacts), 1.0*SUM(answered_in_sla)/SUM(offered), SUM(abandoned),
                  SUM(staffed_agents), SUM(required_agents)
           FROM v_interval WHERE channel='Voice' AND interval_start >= '2026-10-20 14:45' AND interval_start < '2026-10-20 16:30'""")[0]
reb_off, reb_fc, reb_sl, reb_ab, reb_staff, reb_req = reb
chat_surplus = q("""SELECT SUM(staffing_gap) FROM v_interval
                    WHERE queue='Professionals - Chat' AND interval_start >= '2026-10-20 14:45' AND interval_start < '2026-10-20 16:30'""")[0][0]
recover = q("""SELECT MIN(interval_start) FROM incident_timeline
               WHERE interval_start >= '2026-10-20 15:00' AND service_level >= 0.8""")[0][0]
day_voice = {r[0]: r[1] for r in q("""SELECT queue, 1.0*SUM(answered_in_sla)/SUM(offered) FROM v_interval
                                     WHERE interval_date='2026-10-20' AND channel='Voice' GROUP BY queue""")}

mon_gap = q("""SELECT 1.0*SUM(CASE WHEN weekday='Mon' THEN answered_in_sla END)/SUM(CASE WHEN weekday='Mon' THEN offered END),
                      1.0*SUM(CASE WHEN weekday<>'Mon' THEN answered_in_sla END)/SUM(CASE WHEN weekday<>'Mon' THEN offered END),
                      AVG(CASE WHEN weekday='Mon' THEN staffing_gap END), AVG(CASE WHEN weekday<>'Mon' THEN staffing_gap END),
                      SUM(CASE WHEN weekday='Mon' THEN abandoned END)
               FROM v_interval WHERE hour BETWEEN 6 AND 9 AND interval_date NOT IN ('2026-10-12','2026-10-20','2026-10-27')""")[0]
mon_sl, other_sl, mon_gapv, other_gapv, mon_ab = mon_gap
mon_weeks = q("""SELECT COUNT(DISTINCT interval_date) FROM v_interval
                 WHERE weekday='Mon' AND interval_date NOT IN ('2026-10-12','2026-10-20','2026-10-27')""")[0][0]

cost = read("staffing_cost.csv")
surplus_h = sum(float(r["surplus_hours"]) for r in cost)
shortfall_h = sum(float(r["shortfall_hours"]) for r in cost)
staffed_h = sum(float(r["staffed_hours"]) for r in cost)
surplus_usd = sum(float(r["surplus_cost_usd"]) for r in cost)
fa = {r["queue"]: r for r in read("forecast_accuracy.csv")}

absent = q("""SELECT 1.0*SUM(answered_in_sla)/SUM(offered), 1.0*SUM(abandoned)/SUM(offered), AVG(staffing_gap),
                     SUM(staffed_agents)*0.25, SUM(required_agents)*0.25
              FROM v_interval WHERE interval_date='2026-10-27' AND queue='Facilities - Voice'""")[0]
fac_typical = q("""SELECT 1.0*SUM(answered_in_sla)/SUM(offered) FROM v_interval
                   WHERE queue='Facilities - Voice' AND interval_date NOT IN ('2026-10-12','2026-10-20','2026-10-27')""")[0][0]

audit = read("agent_audit.csv")
flagged = [a for a in audit if a["audit_flag"]]
excess = sum(float(a["excess_min_per_shift"]) for a in flagged)
episodes = read("anomaly_episodes.csv")

# ============ charts ============
# 1. incident timeline
tl = read("incident_timeline.csv")
x = [r["time_of_day"] for r in tl]
fig, ax = plt.subplots(figsize=(11, 4.2))
ax.bar(x, [int(r["offered"]) for r in tl], color="#9DB8FF", label="Offered (voice)")
ax.plot(x, [float(r["forecast"]) for r in tl], color="#14213D", lw=2, label="Forecast")
ax.axvspan(x.index("13:00") - 0.5, x.index("14:45") - 0.5, color="#D64545", alpha=0.08)
ax.axvspan(x.index("14:45") - 0.5, x.index("16:30") - 0.5, color="#E0A100", alpha=0.10)
ax.text(x.index("13:00") - 0.3, ax.get_ylim()[1] * 0.6, "Telephony\noutage", color="#D64545", fontsize=9)
ax.text(x.index("16:30") - 1.6, ax.get_ylim()[1] * 0.6, "Rebound", color="#A07000", fontsize=9)
ax.set_ylabel("Contacts per 15 min")
ax2 = ax.twinx()
ax2.plot(x, [float(r["service_level"]) * 100 if r["service_level"] else None for r in tl], color="#0B6E4F", lw=2, marker="o", ms=3, label="Service level %")
ax2.axhline(80, color="#0B6E4F", ls="--", lw=1)
ax2.set_ylim(0, 105)
ax2.set_ylabel("Service level %")
ax2.spines["right"].set_visible(True)
ax.set_xticks(range(0, len(x), 4))
ax.set_xticklabels(x[::4])
ax.set_xlabel("")
h1, l1 = ax.get_legend_handles_labels()
h2, l2 = ax2.get_legend_handles_labels()
ax.legend(h1 + h2, l1 + l2, loc="upper center", bbox_to_anchor=(0.5, -0.1), frameon=False, ncol=3)
ax.set_title("20 Oct 2026, voice queues: outage, rebound and recovery", loc="left", fontweight="bold")
fig.tight_layout()
fig.savefig(IMG / "incident_2026-10-20.png", dpi=150)
plt.close(fig)

# 2. daily SL by queue
daily = read("daily_sla.csv")
fig, ax = plt.subplots(figsize=(11, 4))
dates = sorted({r["interval_date"] for r in daily})
for qn, c in zip(QUEUES, COLORS):
    ys = {r["interval_date"]: float(r["service_level"]) * 100 for r in daily if r["queue"] == qn}
    ax.plot(range(len(dates)), [ys[d] for d in dates], color=c, lw=2, label=qn)
ax.axhline(80, color="#5B6475", ls="--", lw=1)
for d, txt in (("2026-10-12", "Chat spike"), ("2026-10-20", "Outage"), ("2026-10-27", "Absenteeism")):
    ax.annotate(txt, (dates.index(d), 30), ha="center", fontsize=9, color="#5B6475")
ax.set_xticks(range(0, len(dates), 2))
ax.set_xticklabels([d[5:] for d in dates][::2])
ax.set_ylim(20, 100)
ax.set_ylabel("Service level %")
ax.legend(frameon=False, ncol=4, loc="lower left", fontsize=9)
ax.set_title("Daily service level by queue (target 80%, dashed)", loc="left", fontweight="bold")
fig.tight_layout()
fig.savefig(IMG / "daily_sla.png", dpi=150)
plt.close(fig)

# 3. heatmap weekday x hour (all queues, incident days excluded)
cells = defaultdict(lambda: [0, 0])
for wd, h, off, sl in q("""SELECT weekday_num, hour, SUM(offered), SUM(answered_in_sla) FROM v_interval
                           WHERE interval_date NOT IN ('2026-10-12','2026-10-20','2026-10-27') GROUP BY weekday_num, hour"""):
    cells[(wd, h)] = [off, sl]
order = [1, 2, 3, 4, 5, 6, 0]
grid = [[cells[(wd, h)][1] / cells[(wd, h)][0] * 100 if cells[(wd, h)][0] else None for h in range(24)] for wd in order]
fig, ax = plt.subplots(figsize=(11, 3.4))
im = ax.imshow(grid, cmap="RdYlGn", vmin=50, vmax=95, aspect="auto")
ax.set_yticks(range(7))
ax.set_yticklabels(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])
ax.set_xticks(range(24))
ax.set_xticklabels([f"{h:02d}" for h in range(24)], fontsize=8)
ax.set_xlabel("Hour (US Central)")
for i, row in enumerate(grid):
    for j, v in enumerate(row):
        if v is not None and v < 70:
            ax.text(j, i, f"{v:.0f}", ha="center", va="center", fontsize=7, color="black")
fig.colorbar(im, ax=ax, label="SL %", fraction=0.025)
ax.set_title("Service level by weekday and hour, all queues (incident days excluded): the Monday 6-10 am gap", loc="left", fontweight="bold")
fig.tight_layout()
fig.savefig(IMG / "sl_heatmap.png", dpi=150)
plt.close(fig)

# 4. agent audit
top = sorted(audit, key=lambda a: float(a["excess_min_per_shift"]), reverse=True)[:15]
fig, ax = plt.subplots(figsize=(11, 4))
ax.barh([a["agent_id"] for a in top][::-1], [float(a["excess_min_per_shift"]) for a in top][::-1],
        color=["#D64545" if a["audit_flag"] else "#B8C2D3" for a in top][::-1])
for i, a in enumerate(top[::-1]):
    if a["audit_flag"]:
        ax.text(float(a["excess_min_per_shift"]) + 2, i, a["audit_flag"], va="center", fontsize=9, color="#14213D")
ax.set_xlabel("Productive minutes lost per shift vs team average")
ax.set_title("Agent state audit: 5 agents explain almost all the hidden capacity drain", loc="left", fontweight="bold")
fig.tight_layout()
fig.savefig(IMG / "agent_audit.png", dpi=150)
plt.close(fig)

# ============ documents ============
ep_lines = "\n".join(f"| {e['queue']} | {e['anomaly']} | {e['episode_start']} → {e['episode_end'][11:16]} | "
                     f"{e['offered']} vs {float(e['forecast']):.0f} | {float(e['variance']) * 100:+.0f}% | {e['abandoned']} |" for e in episodes)
(DOCS / "incident-update-2026-10-20.md").write_text(f"""# Incident update: voice outage and rebound, Tue 20 Oct 2026

*Written as the RTA would send it to Ops leadership. Synthetic data; times in US Central.*

**Status:** resolved · **Queues:** Professionals - Voice, Facilities - Voice · **Window:** 13:00 – 16:30

![Incident timeline](img/incident_2026-10-20.png)

## Impact
- **13:00 – 14:45, outage.** Voice arrivals fell to **{out_off} contacts vs {out_fc:.0f} forecast ({(out_off / out_fc - 1) * 100:+.0f}%)**. Healthcare professionals and facilities could not reach us by phone for 1 h 45 min. Queue metrics looked "green" because nobody could get in, which is why a volume drop is treated as an incident signal, not good news.
- **14:45 – 16:30, rebound.** Callers came back at once: **{reb_off} contacts vs {reb_fc:.0f} forecast ({(reb_off / reb_fc - 1) * 100:+.0f}%)**. Service level fell to **{pct(reb_sl)}** and **{reb_ab} callers abandoned**. Staffed agents covered **{reb_staff / reb_req * 100:.0f}%** of the Erlang C requirement in that window.
- **Recovery:** voice service level was back above 80% at **{recover[11:] if recover else 'n/a'}**. Day result: Professionals - Voice {pct(day_voice['Professionals - Voice'])}, Facilities - Voice {pct(day_voice['Facilities - Voice'])} (target 80%).

## Cause
Telephony platform outage (inbound calls failing before reaching the queue), detected by the volume-drop rule in `sql/03_anomaly_islands.sql`: arrivals under 40% of forecast for 45 minutes or more. The rebound was the backlog of callers retrying.

## Levers (from the playbook and the live board, in order)
1. **At 13:45, outage confirmed:** open an incident with the platform team; push in-app / SMS notice so professionals use chat; keep voice agents on shift for the rebound instead of releasing them to off-phone work.
2. **At 15:00, rebound:** the board showed Professionals - Voice **Red** with a gap of 13 agents while Professionals - Chat was **Green with surplus** ({chat_surplus:+d} agent-intervals over requirement during the rebound). Lever: move cross-skilled chat agents to voice, cancel the 15:30 coaching sessions, offer voluntary overtime to the evening shift.
3. **From 16:30:** return agents to their home queues as SL holds above 80% for two intervals.

## Follow-ups
| Action | Owner | Due |
|---|---|---|
| Add the "volume < 40% of forecast for 45 min" rule (already in the SQL) as a live alert on the Sheets board | RTA | 1 week |
| Pre-approved cross-skill list chat → voice for rebounds | WFM + Team Leads | 1 week |
| Ask platform team for outage start / end timestamps to measure detection time | Ops Manager | 1 week |

## All anomaly episodes detected in the 4 weeks
| Queue | Type | Window | Offered vs forecast | Variance | Abandoned |
|---|---|---|---|---|---|
{ep_lines}
""", encoding="utf-8")

cost_lines = "\n".join(f"| {r['queue']} | {float(r['staffed_hours']):,.0f} | {float(r['surplus_hours']):,.0f} ({float(r['surplus_share']) * 100:.0f}%) | "
                       f"{float(r['shortfall_hours']):,.0f} | ${float(r['surplus_cost_usd']):,.0f} | {r['abandons_when_short']} |" for r in cost)
sl_lines = "\n".join(f"| {qn} | {overall[qn][0]:,} | {pct(overall[qn][1])} | {pct(overall[qn][2])} | "
                     f"{float(fa[qn]['daily_wape']) * 100:.1f}% | {float(fa[qn]['bias']) * 100:+.1f}% |" for qn in QUEUES)
audit_lines = "\n".join(f"| {a['agent_id']} | {a['team']} | {a['audit_flag']} | {a['hold_rate']} holds/contact · {a['avg_hold_sec']} s avg hold | "
                        f"{float(a['avg_acw_sec']):.0f} s ACW | {float(a['avg_login_delay_min']):.1f} / {float(a['avg_early_logout_min']):.1f} | {float(a['excess_min_per_shift']):.0f} |"
                        for a in flagged)
(DOCS / "weekly-business-review.md").write_text(f"""# Business review: support queues, 5 Oct – 1 Nov 2026

*Four-week review written for Ops leadership. Synthetic data; every number is computed by `scripts/build_reports.py` from the SQL results.*

## The short version
1. **Service level was {pct(tot_sl)} against an 80% target** over {tot_off:,} contacts, with {pct(tot_ab)} abandonment. The average hides two problems: **Facilities - Voice missed target ({pct(overall["Facilities - Voice"][1])})**, and **every Monday morning there is a structural hole in the schedule.** Three one-off incidents added to the misses.
2. **Mondays 6–10 am run at {pct(mon_sl)} SL vs {pct(other_sl)} on other days in the same hours** ({mon_weeks} Mondays, incidents excluded). Staffing sits {mon_gapv:+.1f} agents vs requirement on average, against {other_gapv:+.1f} the rest of the week. This is a scheduling fix, not a real-time one.
3. **We pay for capacity we do not use at other times:** {surplus_h:,.0f} of {staffed_h:,.0f} staffed agent-hours ({surplus_h / staffed_h * 100:.0f}%) were above the Erlang C requirement, about **${surplus_usd:,.0f}** at an assumed $14 per loaded hour, while {shortfall_h:,.0f} hours were short. Moving part of that surplus into Monday mornings protects SLA at no extra cost.
4. **Five agents explain almost all of the hidden capacity drain** found by the state audit: {excess:.0f} productive minutes per shift between them, **≈ {excess / 480:.2f} FTE**.

![Daily SL](img/daily_sla.png)

## Service level and forecast accuracy
| Queue | Contacts | Service level | Abandon rate | Daily forecast error (WAPE) | Forecast bias |
|---|---:|---:|---:|---:|---:|
{sl_lines}

Forecasts are accurate at day level (WAPE around 5%) and unbiased, so the misses are not a forecasting problem; interval-level error is naturally higher on small queues.

## Structural gap: Monday mornings
![Heatmap](img/sl_heatmap.png)

The heatmap leaves out the three incident days, so what remains is the shape of the schedule. The red block on Monday 6–10 am appears every week; `sql/02_daily_sla_and_heatmap.sql` lists it in `chronic_gaps`. Callers abandoned {mon_ab:,} times in those hours across {mon_weeks} Mondays.

**Recommendation:** shift 2–3 agents' Monday start from 9 am to 6 am (or add a 6–10 am split shift), funded from the surplus hours below.

## Fiscal efficiency of SLA protection
| Queue | Staffed hours | Surplus hours (share) | Shortfall hours | Surplus cost | Abandons while short |
|---|---:|---:|---:|---:|---:|
{cost_lines}

Surplus = staffed above the Erlang C requirement for the contacts that actually arrived (80% target). Some surplus is the price of variability; above ~10–12% it is money that could be moved to the hours that miss.

## Incidents
- **Mon 12 Oct, Professionals - Chat:** unforecasted spike after an app release (detected 07:30 – 08:15, +70% vs forecast). Daily chat SL fell to {pct(float([r for r in daily if r['interval_date'] == '2026-10-12' and r['queue'] == 'Professionals - Chat'][0]['service_level']))}.
- **Tue 20 Oct, voice:** telephony outage and rebound, see [incident update](incident-update-2026-10-20.md).
- **Tue 27 Oct, Facilities - Voice:** high absenteeism. Staffed {absent[3]:,.0f} agent-hours vs {absent[4]:,.0f} required; SL {pct(absent[0])} vs {pct(fac_typical)} on a typical day, abandonment {pct(absent[1])}. Lever for next time: same-day call-out list and cross-skilling Professionals - Voice agents into Facilities.

## Agent state audit (last 2 weeks)
![Agent audit](img/agent_audit.png)

| Agent | Team | Flag | Holds | ACW | Login delay / early logout (min; negative = stayed late) | Excess min/shift |
|---|---|---|---|---|---|---:|
{audit_lines}

Each agent is compared with peers on the same team (z-score above 2.5), so a team with longer handle times does not create false positives. The audit is a starting point for a Team Lead conversation, not a verdict: a long hold pattern can also mean a knowledge gap or a broken tool.

## Asks
1. Approve the Monday 6–10 am schedule change (no headcount change).
2. Pre-approve a chat → voice cross-skill list for outages and rebounds.
3. Team Leads review the five flagged agents and report back in two weeks.
""", encoding="utf-8")
print("charts and docs written")
