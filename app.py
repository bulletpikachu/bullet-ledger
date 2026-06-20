from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path

from flask import Flask, g, jsonify, render_template, request


BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "poker_ledger.sqlite3"

app = Flask(__name__)


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_error: Exception | None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL COLLATE NOCASE UNIQUE,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS games (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            played_on TEXT NOT NULL,
            small_blind REAL NOT NULL,
            big_blind REAL NOT NULL,
            starting_stack REAL NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('active', 'finished')) DEFAULT 'active',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            finished_at TEXT
        );

        CREATE TABLE IF NOT EXISTS game_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
            player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
            buy_in_total REAL NOT NULL DEFAULT 0,
            cash_out REAL NOT NULL DEFAULT 0,
            profit REAL NOT NULL DEFAULT 0,
            settled INTEGER NOT NULL DEFAULT 0,
            UNIQUE(game_id, player_id)
        );
        """
    )

    entry_columns = [row[1] for row in db.execute("PRAGMA table_info(game_entries)").fetchall()]
    if "settled" not in entry_columns:
        db.execute("ALTER TABLE game_entries ADD COLUMN settled INTEGER NOT NULL DEFAULT 0")

    existing_columns = [row[1] for row in db.execute("PRAGMA table_info(games)").fetchall()]
    if "default_buy_in" in existing_columns:
        db.execute("PRAGMA foreign_keys = OFF")
        db.execute("BEGIN")
        db.executescript(
            """
            CREATE TABLE games_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                played_on TEXT NOT NULL,
                small_blind INTEGER NOT NULL,
                big_blind INTEGER NOT NULL,
                starting_stack INTEGER NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('active', 'finished')) DEFAULT 'active',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                finished_at TEXT
            );

            INSERT INTO games_new (id, title, played_on, small_blind, big_blind, starting_stack, status, created_at, finished_at)
            SELECT id, title, played_on, small_blind, big_blind, starting_stack, status, created_at, finished_at
            FROM games;

            DROP TABLE games;
            ALTER TABLE games_new RENAME TO games;
            """
        )
        db.execute("PRAGMA foreign_keys = ON")

    db.commit()


@app.before_request
def ensure_schema() -> None:
    init_db()


def row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


def parse_amount(value: object, field: str) -> float:
    try:
        amount = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be a numeric chip or dollar amount.") from None
    if amount < 0:
        raise ValueError(f"{field} cannot be negative.")
    return amount


def parse_int(value: object, field: str) -> int:
    try:
        amount = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be a whole number.") from None
    if amount < 0:
        raise ValueError(f"{field} cannot be negative.")
    return amount


def require_json() -> dict:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object.")
    return data


def game_payload(game_id: int) -> dict | None:
    db = get_db()
    game = db.execute("SELECT * FROM games WHERE id = ?", (game_id,)).fetchone()
    if game is None:
        return None
    entries = db.execute(
        """
        SELECT ge.id, ge.game_id, ge.player_id, p.name AS player_name,
               ge.buy_in_total, ge.cash_out, ge.profit, ge.settled
        FROM game_entries ge
        JOIN players p ON p.id = ge.player_id
        WHERE ge.game_id = ?
        ORDER BY lower(p.name)
        """,
        (game_id,),
    ).fetchall()
    payload = row_to_dict(game)
    payload["entries"] = [row_to_dict(entry) for entry in entries]
    payload["settled_count"] = sum(1 for entry in payload["entries"] if entry["settled"])
    payload["is_settled"] = bool(payload["entries"]) and payload["settled_count"] == len(payload["entries"])
    return payload


@app.errorhandler(ValueError)
def handle_value_error(error: ValueError):
    return jsonify({"error": str(error)}), 400


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/players")
def list_players():
    players = get_db().execute(
        "SELECT id, name FROM players ORDER BY lower(name)"
    ).fetchall()
    return jsonify([row_to_dict(player) for player in players])


@app.post("/api/players")
def create_player():
    data = require_json()
    name = str(data.get("name", "")).strip()
    if not name:
        raise ValueError("Player name is required.")

    db = get_db()
    try:
        cursor = db.execute("INSERT INTO players (name) VALUES (?)", (name,))
        db.commit()
        player_id = cursor.lastrowid
    except sqlite3.IntegrityError:
        player = db.execute("SELECT id FROM players WHERE lower(name) = lower(?)", (name,)).fetchone()
        if player is None:
            raise ValueError("Could not create player.") from None
        player_id = player["id"]

    player = db.execute("SELECT id, name FROM players WHERE id = ?", (player_id,)).fetchone()
    return jsonify(row_to_dict(player)), 201


@app.get("/api/games")
def list_games():
    db = get_db()
    games = db.execute(
        """
        SELECT g.*,
               COUNT(ge.id) AS player_count,
               COALESCE(SUM(ge.buy_in_total), 0) AS total_buy_in,
               COALESCE(SUM(ge.cash_out), 0) AS total_cash_out,
               COALESCE(SUM(ge.profit), 0) AS total_profit,
               COALESCE(SUM(ge.settled), 0) AS settled_count,
               CASE
                   WHEN COUNT(ge.id) > 0 AND SUM(ge.settled) = COUNT(ge.id) THEN 1
                   ELSE 0
               END AS is_settled
        FROM games g
        LEFT JOIN game_entries ge ON ge.game_id = g.id
        GROUP BY g.id
        ORDER BY g.played_on DESC, g.id DESC
        """
    ).fetchall()
    return jsonify([row_to_dict(game) for game in games])


@app.get("/api/games/active")
def active_game():
    row = get_db().execute(
        "SELECT id FROM games WHERE status = 'active' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return jsonify(game_payload(row["id"]) if row else None)


@app.get("/api/games/<int:game_id>")
def get_game(game_id: int):
    payload = game_payload(game_id)
    if payload is None:
        return jsonify({"error": "Game not found."}), 404
    return jsonify(payload)


@app.post("/api/games")
def create_game():
    data = require_json()
    title = str(data.get("title") or f"Home Game {date.today().isoformat()}").strip()
    played_on = str(data.get("played_on") or date.today().isoformat()).strip()
    try:
        datetime.strptime(played_on, "%Y-%m-%d")
    except ValueError:
        raise ValueError("Game date must use YYYY-MM-DD.") from None

    small_blind = parse_amount(data.get("small_blind"), "Small blind")
    big_blind = parse_amount(data.get("big_blind"), "Big blind")
    starting_stack = parse_amount(data.get("starting_stack"), "Starting stack")
    if small_blind == 0 or big_blind == 0 or starting_stack == 0:
        raise ValueError("Blinds and starting stack must be greater than zero.")

    db = get_db()
    cursor = db.execute(
        """
        INSERT INTO games (title, played_on, small_blind, big_blind, starting_stack)
        VALUES (?, ?, ?, ?, ?)
        """,
        (title, played_on, small_blind, big_blind, starting_stack),
    )
    db.commit()
    return jsonify(game_payload(cursor.lastrowid)), 201


@app.post("/api/games/<int:game_id>/players")
def add_game_player(game_id: int):
    data = require_json()
    player_id = data.get("player_id")
    player_name = str(data.get("name", "")).strip()
    db = get_db()

    game = db.execute("SELECT id, status, starting_stack FROM games WHERE id = ?", (game_id,)).fetchone()
    if game is None:
        return jsonify({"error": "Game not found."}), 404
    if game["status"] == "finished":
        raise ValueError("Finished games cannot be changed.")

    if player_id is None:
        if not player_name:
            raise ValueError("Choose an existing player or enter a new name.")
        try:
            cursor = db.execute("INSERT INTO players (name) VALUES (?)", (player_name,))
            player_id = cursor.lastrowid
        except sqlite3.IntegrityError:
            player = db.execute(
                "SELECT id FROM players WHERE lower(name) = lower(?)", (player_name,)
            ).fetchone()
            if player is None:
                raise ValueError("Could not find player.") from None
            player_id = player["id"]
    else:
        player_id = parse_int(player_id, "Player id")

    db.execute(
        "INSERT OR IGNORE INTO game_entries (game_id, player_id, buy_in_total) VALUES (?, ?, ?)",
        (game_id, player_id, game["starting_stack"]),
    )
    db.commit()
    return jsonify(game_payload(game_id))


@app.patch("/api/entries/<int:entry_id>")
def update_entry(entry_id: int):
    data = require_json()
    db = get_db()
    entry = db.execute(
        """
        SELECT ge.*, g.status, g.starting_stack
        FROM game_entries ge
        JOIN games g ON g.id = ge.game_id
        WHERE ge.id = ?
        """,
        (entry_id,),
    ).fetchone()
    if entry is None:
        return jsonify({"error": "Entry not found."}), 404
    if entry["status"] == "finished":
        raise ValueError("Finished games cannot be changed.")

    buy_in_total = entry["buy_in_total"]
    cash_out = entry["cash_out"]
    if "buy_in_delta" in data:
        buy_in_total += entry["starting_stack"]
    if "buy_in_total" in data:
        buy_in_total = parse_amount(data["buy_in_total"], "Buy-in total")
    if "cash_out" in data:
        cash_out = parse_amount(data["cash_out"], "Cash-out")

    db.execute(
        """
        UPDATE game_entries
        SET buy_in_total = ?, cash_out = ?, profit = ?
        WHERE id = ?
        """,
        (buy_in_total, cash_out, cash_out - buy_in_total, entry_id),
    )
    db.commit()
    return jsonify(game_payload(entry["game_id"]))


@app.patch("/api/entries/<int:entry_id>/settled")
def update_entry_settled(entry_id: int):
    data = require_json()
    db = get_db()
    entry = db.execute(
        """
        SELECT ge.game_id, g.status
        FROM game_entries ge
        JOIN games g ON g.id = ge.game_id
        WHERE ge.id = ?
        """,
        (entry_id,),
    ).fetchone()
    if entry is None:
        return jsonify({"error": "Entry not found."}), 404
    if entry["status"] != "finished":
        raise ValueError("Only finished game payouts can be marked settled.")

    db.execute(
        "UPDATE game_entries SET settled = ? WHERE id = ?",
        (1 if data.get("settled") else 0, entry_id),
    )
    db.commit()
    return jsonify(game_payload(entry["game_id"]))


@app.post("/api/games/<int:game_id>/finish")
def finish_game(game_id: int):
    db = get_db()
    game = db.execute("SELECT id, status FROM games WHERE id = ?", (game_id,)).fetchone()
    if game is None:
        return jsonify({"error": "Game not found."}), 404
    if game["status"] == "finished":
        return jsonify(game_payload(game_id))

    db.execute(
        """
        UPDATE game_entries
        SET profit = cash_out - buy_in_total
        WHERE game_id = ?
        """,
        (game_id,),
    )
    db.execute(
        "UPDATE games SET status = 'finished', finished_at = CURRENT_TIMESTAMP WHERE id = ?",
        (game_id,),
    )
    db.commit()
    return jsonify(game_payload(game_id))


@app.get("/api/ledger")
def ledger():
    db = get_db()
    rows = db.execute(
        """
        SELECT p.id, p.name,
               COUNT(CASE WHEN g.status = 'finished' THEN 1 END) AS games_played,
               COALESCE(SUM(CASE WHEN g.status = 'finished' THEN ge.buy_in_total ELSE 0 END), 0) AS total_buy_in,
               COALESCE(SUM(CASE WHEN g.status = 'finished' THEN ge.cash_out ELSE 0 END), 0) AS total_cash_out,
               COALESCE(SUM(CASE WHEN g.status = 'finished' THEN ge.profit ELSE 0 END), 0) AS total_profit
        FROM players p
        LEFT JOIN game_entries ge ON ge.player_id = p.id
        LEFT JOIN games g ON g.id = ge.game_id
        GROUP BY p.id
        ORDER BY total_profit DESC, lower(p.name)
        """
    ).fetchall()
    return jsonify([row_to_dict(row) for row in rows])


if __name__ == "__main__":
    app.run(debug=True)
