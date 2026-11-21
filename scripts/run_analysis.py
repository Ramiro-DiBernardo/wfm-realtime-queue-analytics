"""Run the whole analysis: raw CSVs -> SQLite -> SQL in sql/ -> results/*.csv.

Run:  python scripts/run_analysis.py
Then: python scripts/build_outputs.py   (charts, Google Sheets workbook, written reports)
"""
import csv
import sqlite3
from pathlib import Path

from erlang import required_agents

ROOT = Path(__file__).resolve().parent.parent
RAW, RESULTS = ROOT / "data" / "raw", ROOT / "results"
DB = ROOT / "data" / "wfm.db"
RESULTS.mkdir(exist_ok=True)
CONCURRENCY = {"Chat": 2.0, "Voice": 1.0}

EXPORT = ["rt_queue_board", "daily_sla", "sl_heatmap", "chronic_gaps", "anomaly_episodes",
          "forecast_accuracy", "staffing_cost", "agent_audit", "incident_timeline"]


def load_raw(con):
    for f in sorted(RAW.glob("*.csv")):
        with open(f, newline="", encoding="utf-8") as fh:
            rows = list(csv.reader(fh))
        t = "raw_" + f.stem
        con.execute(f"DROP TABLE IF EXISTS {t}")
        con.execute(f"CREATE TABLE {t} ({', '.join(c + ' TEXT' for c in rows[0])})")
        con.executemany(f"INSERT INTO {t} VALUES ({', '.join('?' * len(rows[0]))})", rows[1:])
        print(f"loaded {t:<22} {len(rows) - 1:>7,}")
    con.execute("CREATE INDEX ix_status ON raw_agent_status(agent_id, start_time)")


def erlang_requirement(con):
    """Productive agents the arrived contacts actually needed (80% target, Erlang C)."""
    rows = con.execute("""SELECT interval_start, queue, channel, CAST(offered AS INTEGER),
                                 CAST(NULLIF(aht_sec, '') AS REAL), CAST(sla_target_sec AS INTEGER)
                          FROM raw_acd_interval""").fetchall()
    out = [(ts, q, required_agents(off, aht or 0, tgt, concurrency=CONCURRENCY[ch]) if off and aht else 0)
           for ts, q, ch, off, aht, tgt in rows]
    con.execute("DROP TABLE IF EXISTS interval_required")
    con.execute("CREATE TABLE interval_required (interval_start TEXT, queue TEXT, required_agents INTEGER)")
    con.executemany("INSERT INTO interval_required VALUES (?, ?, ?)", out)
    print(f"Erlang C requirement for {len(out):,} intervals")


def main():
    if DB.exists():
        DB.unlink()
    con = sqlite3.connect(DB)
    load_raw(con)
    erlang_requirement(con)
    for f in sorted((ROOT / "sql").glob("*.sql")):
        con.executescript(f.read_text(encoding="utf-8"))
        print("ran", f.name)
    con.commit()
    for t in EXPORT:
        cur = con.execute(f"SELECT * FROM {t}")
        with open(RESULTS / f"{t}.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow([c[0] for c in cur.description])
            rows = cur.fetchall()
            w.writerows(rows)
        print(f"exported {t:<20} {len(rows):>6,} rows")
    con.close()


if __name__ == "__main__":
    main()
