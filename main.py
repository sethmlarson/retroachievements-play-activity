import datetime
import os
import re
import typing
import sqlite3
import urllib3

http = urllib3.PoolManager(
    headers={
        "User-Agent": "retroachievements-play-activity/1.0 (sethmichaellarson@gmail.com)"
    },
    retries=3,
    timeout=3,
)
db = sqlite3.connect("retroachievements-play-activity.sqlite")
db.execute("""CREATE TABLE IF NOT EXISTS games (
  id INTEGER,
  name STRING,
  console_id INTEGER,
  console_name STRING,
  achievements INTEGER,
  completion INTEGER,
  duration INTEGER,
  ended_at DATETIME,
  recorded_at DATETIME
);""")
db.commit()
db_keys = (
    "id",
    "name",
    "console_id",
    "console_name",
    "completion",
    "achievements",
    "duration",
    "ended_at",
    "recorded_at",
)


def latest_row_for_game(game_id: str) -> dict[str, typing.Any] | None:
    cur = db.execute(
        f"SELECT {', '.join(db_keys)} FROM games WHERE id = ? ORDER BY recorded_at DESC LIMIT 1",
        (game_id,),
    )
    row = cur.fetchall()
    return dict(zip(db_keys, row[0])) if row else None


def main():
    api_key = os.environ["API_KEY"]
    username = os.environ["USERNAME"]

    resp = http.request(
        "GET",
        f"https://retroachievements.org/API/API_GetUserProfile.php",
        fields={"y": api_key, "u": username},
    )
    if resp.status != 200:
        raise RuntimeError(f"Could not authenticate: {resp.status} {resp.data}")
    ulid = resp.json()["ULID"]

    # Get recently played games.
    resp = http.request(
        "GET",
        "https://retroachievements.org/API/API_GetUserRecentlyPlayedGames.php",
        fields={"y": api_key, "u": ulid, "c": "50"},
    )
    if resp.status != 200:
        raise RuntimeError(f"Could not authenticate: {resp.status} {resp.data}")
    games = resp.json()
    for game in games:
        # Unfortunately we have to get
        # the game again to get achievement
        # and progression data. Although
        # we do get the 'LastPlayed' column
        # that we don't get in the Game API.
        game_id = game["GameID"]
        ended_at = game["LastPlayed"].replace(" ", "T", 1)
        resp = http.request(
            "GET",
            "https://retroachievements.org/API/API_GetGameInfoAndUserProgress.php",
            fields={"y": api_key, "u": ulid, "g": str(game_id), "a": "1"},
        )
        if resp.status != 200:
            raise RuntimeError(f"Could not authenticate: {resp.status} {resp.data}")

        # Calculate what the expected row would be.
        game = resp.json()
        completion = int(
            re.search(r"([0-9]{1,2}\.[0-9]{2})%", game["UserCompletion"])
            .group(1)
            .replace(".", "", 1)
        )
        new_row = {
            "id": game_id,
            "name": game["Title"],
            "console_id": game["ConsoleID"],
            "console_name": game["ConsoleName"],
            "completion": completion,
            "achievements": int(game["NumAwardedToUser"]),
            "duration": game["UserTotalPlaytime"],
            "ended_at": ended_at,
        }

        # Compare the 'current' row to the potential new row.
        old_row = latest_row_for_game(game_id)
        if old_row:
            old_row.pop("recorded_at")

        # If there's been an update since: commit it!
        if old_row != new_row:
            print(f"Updated '{game['Title']}': {new_row}")
            new_row["recorded_at"] = datetime.datetime.now().strftime(
                "%Y-%m-%dT%H:%M:%S"
            )
            db.execute(
                f"""
                INSERT INTO games ({", ".join(db_keys)})
                VALUES ({", ".join("?" for _ in db_keys)});
                """,
                tuple(new_row[key] for key in db_keys),
            )
            db.commit()


if __name__ == "__main__":
    main()
