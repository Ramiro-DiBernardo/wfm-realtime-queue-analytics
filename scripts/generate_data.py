"""Generate a synthetic 24/7 support operation (fixed seed, so every number in the docs is reproducible).

Outputs (data/raw/):
  acd_interval.csv   15-minute queue statistics, the kind of export an ACD / omnichannel router produces
  wfm_staffing.csv   15-minute forecast, scheduled and staffed (productive) agents per queue
  agents.csv         agent roster
  schedules.csv      scheduled shifts (last 2 weeks)
  agent_status.csv   agent state changes (last 2 weeks) used for the forensic audit

Planted events the analysis must find:
  2026-10-12  unforecasted chat spike (app release issue)        Professionals - Chat, 07:00-12:00
  2026-10-20  telephony outage, then rebound                      both voice queues, 13:00-16:30
  2026-10-27  high absenteeism                                    Facilities - Voice, whole day
  5 agents with status irregularities (hold abuse, long ACW, micro-breaks, late login / early logout)

Run:  python scripts/generate_data.py
"""
import csv
import math
import random
from datetime import date, datetime, timedelta
from pathlib import Path

from erlang import required_agents, service_level

random.seed(11)
ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
RAW.mkdir(parents=True, exist_ok=True)

START, DAYS = date(2026, 10, 5), 28            # Mon 5 Oct - Sun 1 Nov 2026
STATUS_FROM = date(2026, 10, 19)               # agent-level data for the last 2 weeks

QUEUES = {  # name: channel, daily volume, AHT s, SLA target s, concurrency, intraday profile
    "Professionals - Chat": ("Chat", 1450, 540, 120, 2.0, "pro"),
    "Professionals - Voice": ("Voice", 900, 420, 60, 1.0, "pro"),
    "Facilities - Voice": ("Voice", 460, 480, 60, 1.0, "fac"),
    "Payments - Chat": ("Chat", 520, 600, 120, 2.0, "pay"),
}
WEEKDAY = [1.15, 1.05, 1.0, 1.0, 0.98, 0.78, 0.74]


def intraday(hour: float, profile: str) -> float:
    """Relative arrival rate by hour of day (US Central). Healthcare staffing never sleeps,
    but professionals peak around shift starts (6-8 am, 2-3 pm) and facilities follow office hours."""
    base = 0.25
    if profile == "pro":
        return base + 1.3 * math.exp(-((hour - 7) ** 2) / 4) + 0.9 * math.exp(-((hour - 14.5) ** 2) / 5) + 0.35 * math.exp(-((hour - 21) ** 2) / 6)
    if profile == "fac":
        return 0.12 + 1.4 * math.exp(-((hour - 10.5) ** 2) / 9) + 0.6 * math.exp(-((hour - 16) ** 2) / 5)
    return 0.2 + 1.0 * math.exp(-((hour - 11) ** 2) / 12) + 0.4 * math.exp(-((hour - 18) ** 2) / 8)


profile_sum = {p: sum(intraday(h / 4, p) for h in range(96)) for p in ("pro", "fac", "pay")}


def poisson(lam: float) -> int:
    if lam < 30:
        l, k, p = math.exp(-lam), 0, 1.0
        while True:
            p *= random.random()
            if p <= l:
                return k
            k += 1
    return max(0, round(random.gauss(lam, math.sqrt(lam))))


acd, wfm = [], []
for d in range(DAYS):
    day = START + timedelta(days=d)
    day_shock = random.gauss(1, 0.05)
    for slot in range(96):
        ts = datetime(day.year, day.month, day.day) + timedelta(minutes=15 * slot)
        hour = slot / 4
        for q, (channel, vol, aht, target, conc, prof) in QUEUES.items():
            expected = vol * WEEKDAY[day.weekday()] * intraday(hour, prof) / profile_sum[prof]
            forecast = expected * random.gauss(1, 0.04)
            actual_rate = expected * day_shock
            # ---- planted events ----
            if day == date(2026, 10, 12) and q == "Professionals - Chat" and 7 <= hour < 12:
                actual_rate *= 1.6
            outage = day == date(2026, 10, 20) and channel == "Voice" and 13 <= hour < 14.75
            if outage:
                actual_rate *= 0.12
            if day == date(2026, 10, 20) and channel == "Voice" and 14.75 <= hour < 16.5:
                actual_rate *= 1.7
            offered = poisson(actual_rate)
            aht_actual = aht * random.gauss(1, 0.06)
            req_plan = required_agents(forecast, aht, target, concurrency=conc)
            scheduled = math.ceil(req_plan / 0.68) if req_plan else 1          # 32% planned shrinkage
            # schedules cover the plan with a small buffer, except a chronic Monday-morning gap
            cover = 0.9 if day.weekday() == 0 and 6 <= hour < 10 else 1.16
            staffed = max(2, round(req_plan * random.gauss(cover, 0.05))) if req_plan else 2
            if day == date(2026, 10, 27) and q == "Facilities - Voice":
                staffed = max(1, round(staffed * 0.72))
            if day == date(2026, 10, 20) and channel == "Voice" and 14.75 <= hour < 16.5:
                staffed = max(1, staffed + random.choice([0, 1]))          # a little help pulled in
            sl = service_level(staffed, offered, aht_actual, target, concurrency=conc)
            abandon_rate = min(0.6, max(0.005, (1 - sl) * 0.33 * random.gauss(1, 0.15)))
            abandoned = sum(1 for _ in range(offered) if random.random() < abandon_rate)
            answered = offered - abandoned
            in_sla = sum(1 for _ in range(offered) if random.random() < sl)   # SL measured on offered
            acd.append({"interval_start": ts.strftime("%Y-%m-%d %H:%M"), "queue": q, "channel": channel,
                        "offered": offered, "answered": answered, "abandoned": abandoned,
                        "answered_in_sla": min(in_sla, answered), "sla_target_sec": target,
                        "aht_sec": round(aht_actual) if answered else ""})
            wfm.append({"interval_start": ts.strftime("%Y-%m-%d %H:%M"), "queue": q,
                        "forecast_contacts": round(forecast, 1), "forecast_aht_sec": aht,
                        "scheduled_agents": scheduled, "staffed_agents": staffed})

# ---------------- agents, schedules and status log ----------------
TEAMS = [("Professionals", 25), ("Facilities", 10), ("Payments", 10)]
SHIFTS = [(6, 14), (9, 17), (13, 21), (21, 29)]
AHT_TEAM = {"Professionals": 480, "Facilities": 480, "Payments": 600}
agents, n = [], 0
for team, size in TEAMS:
    for _ in range(size):
        n += 1
        s = SHIFTS[n % 4]
        off = n % 7
        agents.append({"agent_id": f"AG-{n:03d}", "team": team, "shift_start_hour": s[0], "shift_end_hour": s[1],
                       "days_off": f"{off},{(off + 1) % 7}", "tenure_months": random.randint(2, 40)})
# irregular behaviour (the audit should flag exactly these)
HOLD_ABUSE = {"AG-017": (0.55, 240, 720), "AG-031": (0.40, 180, 480)}
LONG_ACW = {"AG-008"}
MICRO_BREAKS = {"AG-042"}
ADHERENCE = {"AG-024"}

schedules, status = [], []


def add(agent, st, t0, t1):
    status.append({"agent_id": agent, "status": st, "start_time": t0.strftime("%Y-%m-%d %H:%M:%S"),
                   "end_time": t1.strftime("%Y-%m-%d %H:%M:%S"), "duration_sec": int((t1 - t0).total_seconds())})


for a in agents:
    aid = a["agent_id"]
    offs = {int(x) for x in a["days_off"].split(",")}
    for d in range((START + timedelta(days=DAYS) - STATUS_FROM).days):
        day = STATUS_FROM + timedelta(days=d)
        if day.weekday() in offs:
            continue
        s0 = datetime(day.year, day.month, day.day) + timedelta(hours=a["shift_start_hour"])
        s1 = s0 + timedelta(hours=8)
        schedules.append({"agent_id": aid, "shift_date": day.isoformat(),
                          "scheduled_start": s0.strftime("%Y-%m-%d %H:%M"), "scheduled_end": s1.strftime("%Y-%m-%d %H:%M")})
        late = random.uniform(15, 40) * 60 if aid in ADHERENCE and random.random() < 0.6 else random.uniform(0, 150)
        early = random.uniform(20, 45) * 60 if aid in ADHERENCE and random.random() < 0.5 else random.uniform(-120, 60)
        t, end = s0 + timedelta(seconds=late), s1 - timedelta(seconds=early)
        planned = [(s0 + timedelta(hours=2), "Break", 900), (s0 + timedelta(hours=4), "Lunch", 1800),
                   (s0 + timedelta(hours=6), "Break", 900)]
        if day.weekday() == 2:
            planned.append((s0 + timedelta(hours=3), "Meeting", 1800))
        planned.sort()
        next_micro = t + timedelta(minutes=random.uniform(15, 30))
        while t < end:
            if planned and t >= planned[0][0]:
                _, st, dur = planned.pop(0)
                t1 = t + timedelta(seconds=dur + random.gauss(60, 90))
                add(aid, st, t, t1)
                t = t1
                continue
            if aid in MICRO_BREAKS and t >= next_micro:
                t1 = t + timedelta(seconds=random.uniform(120, 330))
                add(aid, "Not Ready", t, t1)
                t, next_micro = t1, t1 + timedelta(minutes=random.uniform(12, 25))
                continue
            t1 = t + timedelta(seconds=random.expovariate(1 / 75))
            add(aid, "Available", t, t1)
            t = t1
            handle = max(60, random.lognormvariate(math.log(AHT_TEAM[a["team"]]), 0.35))
            p_hold, h_lo, h_hi = HOLD_ABUSE.get(aid, (0.14, 40, 170))
            if random.random() < p_hold:
                first = handle * random.uniform(0.3, 0.7)
                t1 = t + timedelta(seconds=first)
                add(aid, "Handling", t, t1)
                t2 = t1 + timedelta(seconds=random.uniform(h_lo, h_hi))
                add(aid, "On Hold", t1, t2)
                t3 = t2 + timedelta(seconds=handle - first)
                add(aid, "Handling", t2, t3)
                t = t3
            else:
                t1 = t + timedelta(seconds=handle)
                add(aid, "Handling", t, t1)
                t = t1
            acw = random.uniform(240, 540) if aid in LONG_ACW else random.lognormvariate(math.log(55), 0.4)
            t1 = t + timedelta(seconds=acw)
            add(aid, "After Call Work", t, t1)
            t = t1
        add(aid, "Offline", t, t + timedelta(seconds=1))


def write(name, rows):
    with open(RAW / name, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"{name}: {len(rows):,} rows")


write("acd_interval.csv", acd)
write("wfm_staffing.csv", wfm)
write("agents.csv", agents)
write("schedules.csv", schedules)
write("agent_status.csv", status)
