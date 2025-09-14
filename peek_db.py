import sqlite3, os

DB_PATH = os.path.join(os.path.dirname(__file__), "db.sqlite3")
con = sqlite3.connect(DB_PATH)
con.row_factory = sqlite3.Row
rows = con.execute("""
    SELECT id, username, email, datetime(created_at,'unixepoch') as created_at
    FROM users ORDER BY id DESC
""").fetchall()
for r in rows:
    print(dict(r))
