"""Build sheets/RTA_Queue_Tracker.xlsx: a live queue board driven by formulas, made to be imported into
Google Sheets (File > Import) and used with apps-script/rta_tools.gs. Only functions that behave the same
in Google Sheets and Excel are used (SUMIFS, COUNTIFS, IF, IFERROR, DATEVALUE, INDEX/MATCH, MAX/MIN).

Run after run_analysis.py:  python scripts/build_workbook.py   (needs openpyxl)
"""
import csv
from pathlib import Path

from openpyxl import Workbook
from openpyxl.formatting.rule import CellIsRule, ColorScaleRule, FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "sheets"
OUT.mkdir(exist_ok=True)
START = "2026-10-05"
QUEUES = ["Professionals - Chat", "Professionals - Voice", "Facilities - Voice", "Payments - Chat"]

NAVY, GREY, LIGHT = "14213D", "5B6475", "F4F6FA"
GREEN, AMBER, RED = "C8EED8", "FFE9A8", "F8C9C9"
H = Font(bold=True, color="FFFFFF")
HFILL = PatternFill("solid", fgColor=NAVY)
THIN = Border(bottom=Side(style="thin", color="D6DBE4"))


def header(ws, row, labels, col=1):
    for i, h in enumerate(labels):
        c = ws.cell(row=row, column=col + i, value=h)
        c.font, c.fill = H, HFILL
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)


def read(name):
    with open(ROOT / name, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


acd = read("data/raw/acd_interval.csv")
wfm = {(r["interval_start"], r["queue"]): r for r in read("data/raw/wfm_staffing.csv")}
req = {}
import sqlite3  # noqa: E402

con = sqlite3.connect(ROOT / "data" / "wfm.db")
for ts, q, n in con.execute("SELECT interval_start, queue, required_agents FROM interval_required"):
    req[(ts, q)] = n
con.close()

wb = Workbook()

# ---------------- Intervals (data) ----------------
iv = wb.active
iv.title = "Intervals"
cols = ["Interval #", "Date", "Time", "Hour", "Queue", "Forecast", "Offered", "Answered", "Abandoned",
        "In SLA", "Staffed", "Required"]
header(iv, 1, cols)
dates = []
for i, r in enumerate(acd, start=2):
    ts, q = r["interval_start"], r["queue"]
    d, t = ts.split(" ")
    if d not in dates:
        dates.append(d)
    slot = dates.index(d) * 96 + int(t[:2]) * 4 + int(t[3:]) // 15
    w = wfm[(ts, q)]
    row = [slot, d, t, int(t[:2]), q, float(w["forecast_contacts"]), int(r["offered"]), int(r["answered"]),
           int(r["abandoned"]), int(r["answered_in_sla"]), int(w["staffed_agents"]), req[(ts, q)]]
    for j, v in enumerate(row, start=1):
        iv.cell(row=i, column=j, value=v)
LAST = len(acd) + 1
iv.freeze_panes = "A2"
for c, wdt in zip("ABCDEFGHIJKL", [10, 11, 7, 6, 22, 9, 8, 9, 9, 7, 8, 9]):
    iv.column_dimensions[c].width = wdt
for r in range(2, LAST + 1):
    iv.cell(row=r, column=2).number_format = "@"
    iv.cell(row=r, column=3).number_format = "@"


def rng(col):
    return f"Intervals!${col}$2:${col}${LAST}"


# ---------------- Lists (for dropdowns) ----------------
ls = wb.create_sheet("Lists")
ls["A1"], ls["B1"] = "Dates", "Times"
for i, d in enumerate(dates, start=2):
    ls.cell(row=i, column=1, value=d).number_format = "@"
for i in range(96):
    c = ls.cell(row=i + 2, column=2, value=f"{i // 4:02d}:{(i % 4) * 15:02d}")
    c.number_format = "@"
ls.sheet_state = "hidden"

# ---------------- Live Board ----------------
lb = wb.create_sheet("Live Board", 0)
lb.sheet_view.showGridLines = False
lb["A1"] = "Real-time queue board"
lb["A1"].font = Font(bold=True, size=18, color=NAVY)
lb["A2"], lb["A3"], lb["A4"] = "Date", "Interval (start)", "Interval #"
lb["B2"], lb["B3"] = "2026-10-20", "15:00"
lb["B2"].number_format = lb["B3"].number_format = "@"
lb["B4"] = f'=(DATEVALUE($B$2)-DATEVALUE("{START}"))*96+VALUE(LEFT($B$3,2))*4+VALUE(RIGHT($B$3,2))/15'
lb["D2"] = "Pick a date and interval, or replay the day with RTA tools > Start replay (Apps Script)."
lb["D2"].font = Font(italic=True, color=GREY)
lb["D3"] = "Status: Green >= 80% SL · Amber 65-80% · Red < 65%. Gap = staffed - Erlang C requirement."
lb["D3"].font = Font(italic=True, color=GREY)
for c in ("A2", "A3", "A4"):
    lb[c].font = Font(bold=True, color=GREY)
for c in ("B2", "B3"):
    lb[c].fill = PatternFill("solid", fgColor="FFF4CC")
    lb[c].font = Font(bold=True, size=12)
dv1 = DataValidation(type="list", formula1=f"=Lists!$A$2:$A${len(dates) + 1}", allow_blank=False)
dv2 = DataValidation(type="list", formula1="=Lists!$B$2:$B$97", allow_blank=False)
lb.add_data_validation(dv1)
lb.add_data_validation(dv2)
dv1.add("B2")
dv2.add("B3")

board_cols = ["Queue", "Offered", "Forecast", "Volume vs forecast", "SL now", "SL last hour", "Abandon last hour",
              "Staffed", "Required", "Gap", "Status", "Recommended lever"]
header(lb, 6, board_cols)
lb.row_dimensions[6].height = 32
A, E, F, G, I, J, K, L = (rng(c) for c in "AEFGIJKL")
for i, q in enumerate(QUEUES):
    r = 7 + i
    now = f'{A},$B$4,{E},$A{r}'
    hour = f'{A},">"&($B$4-4),{A},"<="&$B$4,{E},$A{r}'
    lb[f"A{r}"] = q
    lb[f"B{r}"] = f"=SUMIFS({G},{now})"
    lb[f"C{r}"] = f"=ROUND(SUMIFS({F},{now}),0)"
    lb[f"D{r}"] = f'=IFERROR(SUMIFS({G},{hour})/SUMIFS({F},{hour})-1,"")'
    lb[f"E{r}"] = f'=IFERROR(SUMIFS({J},{now})/B{r},"")'
    lb[f"F{r}"] = f'=IFERROR(SUMIFS({J},{hour})/SUMIFS({G},{hour}),"")'
    lb[f"G{r}"] = f'=IFERROR(SUMIFS({rng("I")},{hour})/SUMIFS({G},{hour}),"")'
    lb[f"H{r}"] = f"=SUMIFS({K},{now})"
    lb[f"I{r}"] = f"=SUMIFS({L},{now})"
    lb[f"J{r}"] = f"=H{r}-I{r}"
    lb[f"K{r}"] = f'=IF(B{r}=0,"No volume",IF(E{r}>=0.8,"Green",IF(E{r}>=0.65,"Amber","Red")))'
    lb[f"L{r}"] = (f'=IF(AND(K{r}="Red",J{r}<0,D{r}>0.2),"Unplanned volume: pull cross-skilled agents, move off-phone work, offer OT",'
                   f'IF(AND(K{r}="Red",J{r}<0),"Under-staffed: cancel off-phone activities, check absences",'
                   f'IF(AND(K{r}="Amber",J{r}<0),"Slipping and under-staffed: cancel off-phone work before it turns red",'
                   f'IF(AND(OR(K{r}="Red",K{r}="Amber"),J{r}>=0),"Staffed to need but missing SL: audit AHT, holds, agent states",'
                   f'IF(AND(K{r}="Green",J{r}>=3),"Surplus: release to training / lend agents to a red queue","No action")))))')
    for c in "DEFG":
        lb[f"{c}{r}"].number_format = "0.0%"
    lb[f"D{r}"].number_format = "+0%;-0%;0%"
    for c in "ABCDEFGHIJKL":
        lb[f"{c}{r}"].border = THIN
    lb[f"A{r}"].font = Font(bold=True)
board = "K7:K10"
lb.conditional_formatting.add(board, CellIsRule(operator="equal", formula=['"Green"'], fill=PatternFill("solid", fgColor=GREEN)))
lb.conditional_formatting.add(board, CellIsRule(operator="equal", formula=['"Amber"'], fill=PatternFill("solid", fgColor=AMBER)))
lb.conditional_formatting.add(board, CellIsRule(operator="equal", formula=['"Red"'], fill=PatternFill("solid", fgColor=RED)))
lb.conditional_formatting.add("J7:J10", CellIsRule(operator="lessThan", formula=["0"], font=Font(color="C0392B", bold=True)))
lb.conditional_formatting.add("E7:F10", ColorScaleRule(start_type="num", start_value=0.5, start_color="F8C9C9",
                                                       mid_type="num", mid_value=0.8, mid_color="FFF4CC",
                                                       end_type="num", end_value=1, end_color="C8EED8"))

# hourly SL for the selected day
lb["A13"] = "Service level by hour, selected day (so far)"
lb["A13"].font = Font(bold=True, size=13, color=NAVY)
header(lb, 14, ["Hour"] + QUEUES + ["All queues"])
for h in range(24):
    r = 15 + h
    lb[f"A{r}"] = f"{h:02d}:00"
    for j, q in enumerate(QUEUES):
        col = get_column_letter(2 + j)
        crit = f'{rng("B")},$B$2,{rng("D")},{h},{rng("E")},"{q}",{A},"<="&$B$4'
        lb[f"{col}{r}"] = f'=IFERROR(SUMIFS({J},{crit})/SUMIFS({G},{crit}),"")'
        lb[f"{col}{r}"].number_format = "0%"
    crit = f'{rng("B")},$B$2,{rng("D")},{h},{A},"<="&$B$4'
    lb[f"F{r}"] = f'=IFERROR(SUMIFS({J},{crit})/SUMIFS({G},{crit}),"")'
    lb[f"F{r}"].number_format = "0%"
lb.conditional_formatting.add("B15:F38", ColorScaleRule(start_type="num", start_value=0.3, start_color="F8696B",
                                                        mid_type="num", mid_value=0.8, mid_color="FFEB84",
                                                        end_type="num", end_value=1, end_color="63BE7B"))
for c, wdt in zip("ABCDEFGHIJKL", [24, 10, 10, 12, 9, 11, 11, 9, 10, 7, 11, 70]):
    lb.column_dimensions[c].width = wdt
lb.freeze_panes = "A7"

# ---------------- Daily SLA ----------------
ds = wb.create_sheet("Daily SLA", 1)
ds.sheet_view.showGridLines = False
ds["A1"] = "Daily service level (answered within target / offered)"
ds["A1"].font = Font(bold=True, size=14, color=NAVY)
header(ds, 3, ["Date"] + QUEUES + ["All queues", "Abandon rate (all)", "Red intervals (all)"])
for i, d in enumerate(dates):
    r = 4 + i
    ds[f"A{r}"] = d
    ds[f"A{r}"].number_format = "@"
    for j, q in enumerate(QUEUES):
        col = get_column_letter(2 + j)
        ds[f"{col}{r}"] = f'=IFERROR(SUMIFS({J},{rng("B")},$A{r},{rng("E")},"{q}")/SUMIFS({G},{rng("B")},$A{r},{rng("E")},"{q}"),"")'
        ds[f"{col}{r}"].number_format = "0.0%"
    ds[f"F{r}"] = f'=SUMIFS({J},{rng("B")},$A{r})/SUMIFS({G},{rng("B")},$A{r})'
    ds[f"G{r}"] = f'=SUMIFS({rng("I")},{rng("B")},$A{r})/SUMIFS({G},{rng("B")},$A{r})'
    ds[f"F{r}"].number_format = ds[f"G{r}"].number_format = "0.0%"
    # red intervals = queue-intervals with volume and SL < 65%: counted with a helper column in Intervals
    ds[f"H{r}"] = f'=COUNTIFS({rng("B")},$A{r},{rng("M")},"Red")'
end = 3 + len(dates)
ds.conditional_formatting.add(f"B4:F{end}", ColorScaleRule(start_type="num", start_value=0.3, start_color="F8696B",
                                                           mid_type="num", mid_value=0.8, mid_color="FFEB84",
                                                           end_type="num", end_value=0.95, end_color="63BE7B"))
for c, wdt in zip("ABCDEFGH", [12, 20, 20, 18, 16, 12, 14, 14]):
    ds.column_dimensions[c].width = wdt
ds.freeze_panes = "B4"

# status helper column in Intervals (used by Daily SLA)
iv["M1"] = "Status"
iv["M1"].font, iv["M1"].fill = H, HFILL
for r in range(2, LAST + 1):
    iv[f"M{r}"] = f'=IF(G{r}=0,"No volume",IF(J{r}/G{r}>=0.8,"Green",IF(J{r}/G{r}>=0.65,"Amber","Red")))'

# ---------------- Agent Audit ----------------
aa = wb.create_sheet("Agent Audit", 2)
aa.sheet_view.showGridLines = False
aa["A1"] = "Agent state audit, last 2 weeks (z-score vs team peers; > 2.5 = flag)"
aa["A1"].font = Font(bold=True, size=14, color=NAVY)
audit = read("results/agent_audit.csv")
acols = ["agent_id", "team", "shifts", "contacts", "hold_rate", "avg_hold_sec", "avg_acw_sec", "not_ready_share",
         "avg_login_delay_min", "avg_early_logout_min", "z_hold_rate", "z_hold_length", "z_acw", "z_not_ready",
         "z_adherence", "audit_flag", "excess_min_per_shift"]
labels = ["Agent", "Team", "Shifts", "Contacts", "Hold rate", "Avg hold (s)", "Avg ACW (s)", "Not Ready share",
          "Login delay (min)", "Early logout (min)", "z hold rate", "z hold length", "z ACW", "z Not Ready",
          "z adherence", "Flag", "Excess min / shift"]
header(aa, 3, labels)
aa.row_dimensions[3].height = 32
for i, a in enumerate(audit):
    r = 4 + i
    for j, k in enumerate(acols, start=1):
        v = a[k]
        try:
            v = float(v) if "." in v or k.startswith("z_") else int(v)
        except ValueError:
            pass
        aa.cell(row=r, column=j, value=v)
    aa[f"E{r}"].number_format = aa[f"H{r}"].number_format = "0.0%"
end = 3 + len(audit)
aa.conditional_formatting.add(f"K4:O{end}", CellIsRule(operator="greaterThan", formula=["2.5"],
                                                       fill=PatternFill("solid", fgColor=RED), font=Font(bold=True)))
aa.conditional_formatting.add(f"P4:P{end}", FormulaRule(formula=['LEN($P4)>0'], fill=PatternFill("solid", fgColor=AMBER)))
aa[f"A{end + 2}"] = "Flagged agents"
aa[f"B{end + 2}"] = f'=COUNTIF(P4:P{end},"?*")'
aa[f"A{end + 3}"] = "Excess minutes / shift (flagged)"
aa[f"B{end + 3}"] = f'=SUMIF(P4:P{end},"?*",Q4:Q{end})'
aa[f"A{end + 4}"] = "≈ FTE recovered (8 h shifts)"
aa[f"B{end + 4}"] = f"=ROUND(B{end + 3}/480,2)"
for c in ("A",):
    for k in range(2, 5):
        aa[f"{c}{end + k}"].font = Font(bold=True)
for j in range(1, 18):
    aa.column_dimensions[get_column_letter(j)].width = 11
aa.column_dimensions["A"].width = 30
aa.column_dimensions["B"].width = 15
aa.column_dimensions["P"].width = 18
aa.freeze_panes = "B4"

# ---------------- Anomalies ----------------
an = wb.create_sheet("Anomalies", 3)
an.sheet_view.showGridLines = False
an["A1"] = "Volume anomalies found by sql/03_anomaly_islands.sql (45 min or longer)"
an["A1"].font = Font(bold=True, size=14, color=NAVY)
eps = read("results/anomaly_episodes.csv")
header(an, 3, ["Queue", "Type", "Start", "End", "Intervals", "Offered", "Forecast", "Variance", "Abandoned"])
for i, e in enumerate(eps):
    vals = [e["queue"], e["anomaly"], e["episode_start"], e["episode_end"][:16], int(e["intervals"]), int(e["offered"]),
            float(e["forecast"]), float(e["variance"]), int(e["abandoned"])]
    for j, v in enumerate(vals, start=1):
        an.cell(row=4 + i, column=j, value=v)
    an.cell(row=4 + i, column=8).number_format = "+0%;-0%"
for c, wdt in zip("ABCDEFGHI", [22, 14, 17, 17, 10, 9, 9, 9, 10]):
    an.column_dimensions[c].width = wdt

# ---------------- Playbook ----------------
pb = wb.create_sheet("Playbook", 4)
pb.sheet_view.showGridLines = False
pb["A1"] = "Real-time levers (see docs/rta-playbook.md)"
pb["A1"].font = Font(bold=True, size=14, color=NAVY)
header(pb, 3, ["Trigger", "First lever", "Escalation", "Owner", "Update cadence"])
rows = [
    ("SL < 65% for 2 intervals and gap < 0", "Cancel off-phone work (coaching, meetings) in that queue",
     "Pull cross-skilled agents from a green queue; voluntary OT", "RTA → Team Leads", "Every 15 min in channel"),
    ("Volume > forecast +20% for 45 min", "Re-forecast the rest of the day; flag to WFM planning",
     "Activate overflow routing; publish customer message if incident", "RTA → WFM / Ops Manager", "Every 30 min"),
    ("Volume < forecast -60% for 45 min", "Check telephony / routing health (possible outage)",
     "Open incident with platform team; prepare for rebound spike", "RTA → Incident channel", "Immediately, then 15 min"),
    ("SL red while gap >= 0", "Audit AHT, holds, ACW and agent states in the queue",
     "Coach individual agents; review routing skills", "RTA → Team Leads", "Same day"),
    ("Agent z-score > 2.5 on hold / ACW / Not Ready / adherence", "Review the agent's state log with the Team Lead",
     "Coaching plan; repeat audit after 2 weeks", "RTA → Team Lead", "Weekly"),
    ("Green with gap >= 3 for 1 h", "Release agents to training or back-office work",
     "Lend agents to a red queue", "RTA", "Every 30 min"),
]
for i, rr in enumerate(rows):
    for j, v in enumerate(rr, start=1):
        c = pb.cell(row=4 + i, column=j, value=v)
        c.alignment = Alignment(wrap_text=True, vertical="top")
for c, wdt in zip("ABCDE", [34, 42, 42, 22, 20]):
    pb.column_dimensions[c].width = wdt

# ---------------- Alert Log (written by Apps Script) ----------------
al = wb.create_sheet("Alert Log", 5)
header(al, 1, ["Logged at", "Interval", "Queue", "Status", "SL now", "Gap", "Recommended lever"])
for c, wdt in zip("ABCDEFG", [20, 18, 22, 10, 9, 7, 70]):
    al.column_dimensions[c].width = wdt

# ---------------- Read me ----------------
rm = wb.create_sheet("Read me", 0)
rm.sheet_view.showGridLines = False
lines = [
    ("RTA Queue Tracker", Font(bold=True, size=18, color=NAVY)),
    ("Synthetic data: 4 queues, 15-minute intervals, 5 Oct – 1 Nov 2026 (US Central).", Font(color=GREY)),
    ("", None),
    ("Live Board — pick a date and interval (yellow cells). Every number is a formula over the Intervals tab.", None),
    ("Daily SLA — service level by day and queue, colour scale against the 80% target.", None),
    ("Agent Audit — forensic state audit (holds, ACW, Not Ready, adherence) from sql/05_agent_state_audit.sql.", None),
    ("Anomalies — volume spikes and drops grouped into episodes (gaps-and-islands SQL).", None),
    ("Playbook — triggers and the lever to pull.", None),
    ("Alert Log — filled by the Apps Script (Extensions > Apps Script, paste apps-script/rta_tools.gs).", None),
    ("", None),
    ("Replay a day: RTA tools > Start replay moves the board one interval per minute and logs red/amber queues.", None),
]
for i, (t, f) in enumerate(lines, start=1):
    rm[f"A{i}"] = t
    if f:
        rm[f"A{i}"].font = f
rm.column_dimensions["A"].width = 110

wb.save(OUT / "RTA_Queue_Tracker.xlsx")
print("saved", OUT / "RTA_Queue_Tracker.xlsx")
