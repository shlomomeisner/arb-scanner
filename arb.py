"""
Arb Scanner — checks every US sportsbook for guaranteed-profit (arbitrage) bets.

How it works: for each game, take the BEST price for each side across all books.
If 1/oddsA + 1/oddsB (+ 1/oddsDraw) < 1, betting every side wins money no matter
who wins. The script prints the bet split and pushes an alert to your phone.

Odds come from The Odds API (the-odds-api.com). Free key = 500 requests/month.
"""
import json, os, sys, urllib.request, urllib.parse
from datetime import datetime, timezone

API_KEY   = os.environ.get("ODDS_API_KEY", "")
NTFY      = os.environ.get("NTFY_TOPIC", "")          # phone alerts via ntfy.sh app
BANKROLL  = float(os.environ.get("BANKROLL", "100"))  # total $ per arb
MIN_PROFIT= float(os.environ.get("MIN_PROFIT", "0.5"))# only alert at >= this %
REGIONS   = os.environ.get("REGIONS", "us,us2")
MARKETS   = os.environ.get("MARKETS", "h2h")          # h2h = moneyline
SPORTS    = os.environ.get("SPORTS",
    "americanfootball_nfl,basketball_nba,icehockey_nhl,americanfootball_ncaaf,soccer_epl").split(",")
BOOKS     = [b for b in os.environ.get("BOOKS", "").split(",") if b]  # empty = all

def get(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        left = r.headers.get("x-requests-remaining")
        return json.load(r), left

def fetch(sport):
    q = urllib.parse.urlencode({"apiKey": API_KEY, "regions": REGIONS,
        "markets": MARKETS, "oddsFormat": "decimal"})
    return get(f"https://api.the-odds-api.com/v4/sports/{sport}/odds/?{q}")

def find_arbs(games):
    out = []
    now = datetime.now(timezone.utc)
    for g in games:
        if datetime.fromisoformat(g["commence_time"].replace("Z", "+00:00")) < now:
            continue  # skip live games: lines move too fast
        for mkt in {m["key"] for b in g["bookmakers"] for m in b["markets"]}:
            best = {}  # outcome -> (price, book)
            for b in g["bookmakers"]:
                if BOOKS and b["key"] not in BOOKS:
                    continue
                for m in b["markets"]:
                    if m["key"] != mkt: continue
                    for o in m["outcomes"]:
                        name = o["name"] + (f" {o['point']:+g}" if "point" in o else "")
                        if name not in best or o["price"] > best[name][0]:
                            best[name] = (o["price"], b["title"])
            if len(best) < 2: continue
            implied = sum(1 / p for p, _ in best.values())
            if implied >= 1: continue
            profit = (1 / implied - 1) * 100
            if profit < MIN_PROFIT: continue
            bets = [(n, bk, p, BANKROLL * (1 / p) / implied) for n, (p, bk) in best.items()]
            out.append({"game": f"{g['away_team']} @ {g['home_team']}", "sport": g["sport_title"],
                        "start": g["commence_time"], "market": mkt, "profit": profit,
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
    arbs, left = [], "?"
    for s in SPORTS:
        try:
            games, left = fetch(s.strip())
            arbs += find_arbs(games)
        except Exception as e:
            print(f"{s}: {e}")
    arbs.sort(key=lambda a: -a["profit"])
    print(f"Checked {len(SPORTS)} sports. API requests left this month: {left}")
    if not arbs:
        print("No arbs right now."); return
    for a in arbs:
        print(fmt(a) + "\n")
    notify("\n\n".join(fmt(a) for a in arbs[:5]))

if __name__ == "__main__":
    main()
