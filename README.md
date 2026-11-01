# Arb Scanner

Checks every US sportsbook (DraftKings, FanDuel, BetMGM, Caesars, ESPN BET, Fanatics, BetRivers…) for arbitrage: games where the best prices across books add up to a guaranteed profit. Sends the exact bet split to your phone.

## Setup (5 min, all from your phone)
1. Get a free key at https://the-odds-api.com
2. Install the **ntfy** app, subscribe to a made-up private topic name (e.g. `shlomo-arbs-7x92`)
3. In this repo: **Settings → Secrets and variables → Actions** → add secrets `ODDS_API_KEY` and `NTFY_TOPIC`
4. Optional variables: `BANKROLL` (default 100), `MIN_PROFIT` % (default 0.5)
5. **Actions → Scan for arbs → Run workflow** to test

## Example alert
```
1.95% ARB — Jets @ Bills (NFL, h2h)
  $46.34 on Buffalo Bills @ 2.2 — FanDuel
  $53.66 on New York Jets @ 1.9 — DraftKings
  Bet $100 → get back $101.95 no matter who wins
```

## Read before betting
- Arbs last seconds to minutes. Confirm both prices are still live before placing either bet.
- Place the worse-odds / more volatile side first.
- Books limit or ban accounts that arb often. Bet round-ish amounts and mix in normal bets.
- Free key = 500 requests/month (1 per sport per scan). More scans = paid plan ($30/mo for 20k).
