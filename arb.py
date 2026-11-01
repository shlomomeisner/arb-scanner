"""
Arb Scanner — checks every US sportsbook for guaranteed-profit (arbitrage) bets.

How it works: for each game, take the BEST price for each side across all books.
If 1/oddsA + 1/oddsB (+ 1/oddsDraw) < 1, betting every side wins money no matter
who wins. The script prints the bet split and pushes an alert to your phone.

Odds come from The Odds API (the-odds-api.com). Free key = 500 requests/month.
"""
import json, os, sys, urllib.request, urllib.parse
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import calendar

API_KEY   = os.environ.get("ODDS_API_KEY", "")
NTFY      = os.environ.get("NTFY_TOPIC", "")          # phone alerts via ntfy.sh app
BANKROLL  = float(os.environ.get("BANKROLL", "100"))  # total $ per arb
MIN_PROFIT= float(os.environ.get("MIN_PROFIT", "0.5"))# only alert at >= this %
REGIONS   = os.environ.get("REGIONS", "us")
MARKETS   = os.environ.get("MARKETS", "h2h,spreads,totals")  # moneyline, spread, over/under
SPORTS    = os.environ.get("SPORTS",
    "americanfootball_nfl,basketball_nba,icehockey_nhl,americanfootball_ncaaf").split(",")
BOOKS     = [b for b in os.environ.get("BOOKS", "").split(",") if b]  # empty = all

def get(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        left = r.headers.get("x-requests-remaining")
        return json.load(r), left

SCAN_HOURS_ET = [11, 14, 17, 20]   # must match the workflow schedule
LOOKAHEAD_HRS = 8

def upcoming(sport):
    """Free call (no quota): are there games starting in the next few hours?"""
    now = datetime.now(timezone.utc)
    q = urllib.parse.urlencode({"apiKey": API_KEY,
        "commenceTimeFrom": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "commenceTimeTo": (now + timedelta(hours=LOOKAHEAD_HRS)).strftime("%Y-%m-%dT%H:%M:%SZ")})
    events, left = get(f"https://api.the-odds-api.com/v4/sports/{sport}/events?{q}")
    return len(events), left

def budget(remaining):
    """Credits this scan may spend so the monthly quota lasts to month end."""
    et = datetime.now(ZoneInfo("America/New_York"))
    days_left = calendar.monthrange(et.year, et.month)[1] - et.day
    scans_today = max(1, sum(h >= et.hour for h in SCAN_HOURS_ET))
    total_scans = scans_today + days_left * len(SCAN_HOURS_ET)
    return int(remaining) // total_scans

def pick_markets(n_sports, allowance):
    wanted = [m for m in MARKETS.split(",") if m]
    while wanted and n_sports * len(wanted) * len(REGIONS.split(",")) > allowance:
        wanted.pop()  # drop totals first, then spreads
    return ",".join(wanted)

def fetch(sport, markets):
    q = urllib.parse.urlencode({"apiKey": API_KEY, "regions": REGIONS,
        "markets": markets, "oddsFormat": "decimal"})
    return get(f"https://api.the-odds-api.com/v4/sports/{sport}/odds/?{q}")

def find_arbs(games):
    out = []
    now = datetime.now(timezone.utc)
    for g in games:
        if datetime.fromisoformat(g["commence_time"].replace("Z", "+00:00")) < now:
            continue  # skip live games: lines move too fast
        for mkt in {m["key"] for b in g["bookmakers"] for m in b["markets"]}:
            groups = {}  # line -> {outcome -> (price, book)}
            for b in g["bookmakers"]:
                if BOOKS and b["key"] not in BOOKS:
                    continue
                for m in b["markets"]:
                    if m["key"] != mkt: continue
                    for o in m["outcomes"]:
                        pt = o.get("point")
                        if pt is None: line, name = None, o["name"]
                        elif mkt == "totals": line, name = pt, f"{o['name']} {pt:g}"
                        else:  # spreads: both sides of the same line share home's number
                            line = pt if o["name"] == g["home_team"] else -pt
                            name = f"{o['name']} {pt:+g}"
                        best = groups.setdefault(line, {})
                        if name not in best or o["price"] > best[name][0]:
                            best[name] = (o["price"], b["title"])
            for best in groups.values():
                if len(best) < 2: continue
                implied = sum(1 / p for p, _ in best.values())
                if implied >= 1: continue
                profit = (1 / implied - 1) * 100
                if profit < MIN_PROFIT: continue
                bets = [(n, bk, p, BANKROLL * (1 / p) / implied) for n, (p, bk) in best.items()]
                label = {"h2h": "moneyline", "spreads": "spread", "totals": "over/under"}.get(mkt, mkt)
                out.append({"game": f"{g['away_team']} @ {g['home_team']}", "sport": g["sport_title"],
                            "start": g["commence_time"], "market": label, "profit": profit,
                            "payout": BANKROLL / implied, "bets": bets})
    return out

def fmt(a):
    lines = [f"{a['profit']:.2f}% ARB — {a['game']} ({a['sport']}, {a['market']})"]
    for n, bk, p, stake in a["bets"]:
        lines.append(f"  ${stake:,.2f} on {n} @ {p} — {bk}")
    lines.append(f"  Bet ${BANKROLL:,.0f} → get back ${a['payout']:,.2f} no matter who wins")
    return "\n".join(lines)

def notify(text):
    if not NTFY: return
    req = urllib.request.Request(f"https://ntfy.sh/{NTFY}", data=text.encode(),
        headers={"Title": "Arb found", "Priority": "high"})
    urllib.request.urlopen(req, timeout=15)

def main():
    if not API_KEY:
        sys.exit("Set ODDS_API_KEY (free at the-odds-api.com)")
    arbs, left, active = [], None, []
    for sp in [x.strip() for x in SPORTS]:
        try:
            n, l = upcoming(sp)
            left = l or left
            if n: active.append(sp)
        except Exception as e:
            print(f"{sp}: {e}")
    if not active:
        print("No games in the next few hours. Nothing to scan."); return
    allowance = budget(left) if left and left.isdigit() else 999
    # if even moneylines don't fit, keep the sports listed first
    while active and len(active) * len(REGIONS.split(",")) > allowance:
        active.pop()
    markets = pick_markets(len(active), allowance)
    if not markets:
        print(f"Quota too low this scan ({left} left). Skipping."); return
    print(f"Credits left: {left}. Budget this scan: {allowance}. Scanning {active} for {markets}.")
    for sp in active:
        try:
            games, left = fetch(sp, markets)
            arbs += find_arbs(games)
        except Exception as e:
            print(f"{sp}: {e}")
    arbs.sort(key=lambda a: -a["profit"])
    print(f"Done. Credits left this month: {left}")
    if not arbs:
        print("No arbs right now."); return
    for a in arbs:
        print(fmt(a) + "\n")
    notify("\n\n".join(fmt(a) for a in arbs[:5]))

if __name__ == "__main__":
    main()
