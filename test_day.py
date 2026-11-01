"""One-day test: scan every INTERVAL minutes until END_UTC, spending the
remaining credits evenly, then send a summary to the phone."""
import os, time, json
from datetime import datetime, timezone
import arb

INTERVAL = int(os.environ.get("INTERVAL_MIN", "20")) * 60
END = datetime.fromisoformat(os.environ["END_UTC"]).replace(tzinfo=timezone.utc)
STOP_AT = time.time() + float(os.environ.get("MAX_MIN", "345")) * 60
FINAL = os.environ.get("FINAL") == "1"

def scans_left():
    t = min(END.timestamp(), STOP_AT) - time.time()
    return max(1, int(t // INTERVAL) + 1)

seen, found, scans, log = set(), [], 0, []

while time.time() < min(END.timestamp(), STOP_AT):
    scans += 1
    now = datetime.now(timezone.utc).strftime("%H:%M UTC")
    print(f"\n=== Scan {scans} at {now} ===", flush=True)
    try:
        r = arb.main(allowance_override=lambda left: left // scans_left(), seen=seen)
    except SystemExit as e:
        print(e); break
    except Exception as e:
        print("error:", e); r = []
    for a in r or []:
        found.append({"t": now, "game": a["game"], "market": a["market"], "profit": round(a["profit"], 2),
                      "bets": [f"{n} @ {p} ({bk})" for n, bk, p, _ in a["bets"]]})
    if time.time() + INTERVAL > min(END.timestamp(), STOP_AT): break
    time.sleep(INTERVAL)

uniq = {(f["game"], f["market"], tuple(f["bets"])): f for f in found}
summary = os.environ.get("GITHUB_STEP_SUMMARY")
lines = [f"## Test results: {scans} scans, {len(uniq)} unique arbs\n"]
for f in sorted(uniq.values(), key=lambda f: -f["profit"]):
    lines.append(f"- **{f['profit']}%** {f['game']} ({f['market']}) at {f['t']}: " + " / ".join(f["bets"]))
if summary:
    open(summary, "a").write("\n".join(lines) + "\n")
print("\n".join(lines))
json.dump(list(uniq.values()), open("found.json", "w"))
part = "Full day" if FINAL else "First half"
best = max((f["profit"] for f in uniq.values()), default=0)
arb.notify(f"{part} of test done: {scans} scans, {len(uniq)} arbs found"
           + (f", best {best}%" if uniq else "") + ". Details on GitHub > Actions > Test day.")
