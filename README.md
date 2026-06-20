# bulletLedger

A small web app for tracking home poker games. It keeps a running active game, records buy-ins and cash-outs by player, calculates profit, and rolls finished sessions into a leaderboard-style ledger.

## Setup


Install dependencies:

```bash
pip install -r requirements.txt
```

Run the app directly:

```bash
python app.py
```

## Data

The SQLite database is created automatically at:

```text
poker_ledger.sqlite3
```

The schema includes:

- `players`: unique player names
- `games`: session metadata and status
- `game_entries`: per-player buy-ins, cash-outs, and profit

Delete `poker_ledger.sqlite3` if you want to reset all local data.


## License

MIT License. See [LICENSE](LICENSE).
