from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
from typing import Iterable

BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "poker_ledger.sqlite3"


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.row_factory = sqlite3.Row
    return connection


def print_rows(rows: Iterable[sqlite3.Row]) -> None:
    for row in rows:
        print(
            " | ".join(f"{key}={row[key]}" for key in row.keys())
        )


def list_players() -> None:
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT id, name, created_at FROM players ORDER BY lower(name)"
        ).fetchall()
        if not rows:
            print("No players found.")
            return
        print(f"{len(rows)} players:")
        print_rows(rows)


def list_games(limit: int | None = None) -> None:
    query = "SELECT id, title, played_on, status FROM games ORDER BY played_on DESC, id DESC"
    if limit is not None:
        query += " LIMIT ?"
    with get_connection() as connection:
        rows = connection.execute(query, (limit,) if limit is not None else ()).fetchall()
        if not rows:
            print("No games found.")
            return
        print(f"{len(rows)} games:")
        print_rows(rows)


def list_entries(game_id: int | None = None, player_id: int | None = None) -> None:
    sql = (
        "SELECT ge.id, ge.game_id, ge.player_id, p.name AS player_name, "
        "ge.buy_in_total, ge.cash_out, ge.profit, ge.settled "
        "FROM game_entries ge "
        "JOIN players p ON p.id = ge.player_id"
    )
    params: list[object] = []
    filters: list[str] = []
    if game_id is not None:
        filters.append("ge.game_id = ?")
        params.append(game_id)
    if player_id is not None:
        filters.append("ge.player_id = ?")
        params.append(player_id)
    if filters:
        sql += " WHERE " + " AND ".join(filters)
    sql += " ORDER BY ge.game_id, lower(p.name)"

    with get_connection() as connection:
        rows = connection.execute(sql, params).fetchall()
        if not rows:
            print("No matching entries found.")
            return
        print(f"{len(rows)} entries:")
        print_rows(rows)


def delete_player(name: str, confirm: bool = False) -> None:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT id, name FROM players WHERE lower(name) = lower(?)",
            (name,),
        ).fetchone()
        if not row:
            print(f"Player {name!r} not found.")
            return
        player_id = row["id"]
        entries_count = connection.execute(
            "SELECT COUNT(*) FROM game_entries WHERE player_id = ?",
            (player_id,),
        ).fetchone()[0]
        if not confirm:
            print(
                f"Player {row['name']!r} (id={player_id}) has {entries_count} game entry(ies)."
            )
            print("Use --yes to confirm deletion.")
            return
        connection.execute("DELETE FROM players WHERE id = ?", (player_id,))
        print(
            f"Deleted player {row['name']!r} and {entries_count} associated game entry(ies)."
        )


def rename_player(old_name: str, new_name: str) -> None:
    with get_connection() as connection:
        existing = connection.execute(
            "SELECT id FROM players WHERE lower(name) = lower(?)",
            (old_name,),
        ).fetchone()
        if not existing:
            print(f"Player {old_name!r} not found.")
            return
        conflict = connection.execute(
            "SELECT id FROM players WHERE lower(name) = lower(?)",
            (new_name,),
        ).fetchone()
        if conflict:
            print(f"A player with name {new_name!r} already exists.")
            return
        connection.execute(
            "UPDATE players SET name = ? WHERE id = ?",
            (new_name, existing["id"]),
        )
        print(f"Renamed player {old_name!r} to {new_name!r}.")


def delete_game(game_id: int, confirm: bool = False) -> None:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT id, title, played_on FROM games WHERE id = ?",
            (game_id,),
        ).fetchone()
        if not row:
            print(f"Game id={game_id} not found.")
            return
        entries_count = connection.execute(
            "SELECT COUNT(*) FROM game_entries WHERE game_id = ?",
            (game_id,),
        ).fetchone()[0]
        if not confirm:
            print(
                f"Game id={game_id} {row['title']!r} on {row['played_on']} has {entries_count} entry(ies)."
            )
            print("Use --yes to confirm deletion.")
            return
        connection.execute("DELETE FROM games WHERE id = ?", (game_id,))
        print(f"Deleted game id={game_id} and {entries_count} associated entry(ies).")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Utility script for manual database updates in bullet-ledger."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list-players", help="List all players.")
    subparsers.add_parser("list-games", help="List all games.")

    list_entries_parser = subparsers.add_parser(
        "list-entries", help="List game entries."
    )
    list_entries_parser.add_argument("--game-id", type=int, help="Filter by game id.")
    list_entries_parser.add_argument("--player-id", type=int, help="Filter by player id.")

    delete_player_parser = subparsers.add_parser(
        "delete-player", help="Delete a player and all related game entries.")
    delete_player_parser.add_argument("name", help="Player name to delete.")
    delete_player_parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirm deletion by removing the player and related entries.",
    )

    rename_player_parser = subparsers.add_parser(
        "rename-player", help="Rename a player.")
    rename_player_parser.add_argument("old_name", help="Existing player name.")
    rename_player_parser.add_argument("new_name", help="New player name.")

    delete_game_parser = subparsers.add_parser(
        "delete-game", help="Delete a game and its entries.")
    delete_game_parser.add_argument("game_id", type=int, help="Game id to delete.")
    delete_game_parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirm deletion of the game and related entries.",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "list-players":
        list_players()
    elif args.command == "list-games":
        list_games()
    elif args.command == "list-entries":
        list_entries(game_id=args.game_id, player_id=args.player_id)
    elif args.command == "delete-player":
        delete_player(args.name, confirm=args.yes)
    elif args.command == "rename-player":
        rename_player(args.old_name, args.new_name)
    elif args.command == "delete-game":
        delete_game(args.game_id, confirm=args.yes)
    else:
        raise ValueError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    main()
