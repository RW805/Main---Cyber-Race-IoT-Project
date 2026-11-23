"""
Digital scoreboard: sends each finished score to a MySQL database, so a separate
display can show the scoreboard on a big screen for everyone to see.

There is no local database any more -- the scoreboard lives only in MySQL.

One row is sent per player, when they finish all three levels:

    id        auto increment (set by MySQL)
    username  VARCHAR(99)  the player's name, e.g.  Reece
    time      VARCHAR(99)  total time over all levels, as text, e.g.  174.52s
    penalty   VARCHAR(99)  total penalty seconds, as text, e.g.  +30s
    correct   TEXT         questions right out of questions asked, e.g.  7/9
    isshown   INT          always 1 (set by the game for every record)

Connection details go in scoreboard_config.json (next to this file), never in
the code. Run `python3 scoreboard.py` to check them: it connects, checks the
table has the right columns, and sends nothing.

Sending happens in the background so the game never freezes waiting for the
network. If the database can't be reached (Wi-Fi down, wrong password...), the
score is kept in memory and sent again automatically the next time a player
finishes, or when the next player starts.

Needs PyMySQL (pure Python, installs on a Raspberry Pi with no compiling):
    pip install pymysql
"""
import json
import os
import re
import threading

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scoreboard_config.json")

# What scoreboard_config.json should look like. Fill in your own values.
CONFIG_TEMPLATE = {
    "host": "",              # the MySQL server's address, e.g. "db.example.com" or "192.168.1.20"
    "port": 3306,
    "database": "",          # the database (schema) name -- leave blank to find it automatically
    "user": "",
    "password": "",
    "table": "scoreboard",   # the table with username / time / penalty / correct / isshown
    "ssl": False,            # true if your host requires an encrypted (TLS) connection
    "timeout_secs": 5,       # give up on a slow connection after this long
}

NAME_MAX = 16            # what fits on screen; the column allows 99


# --- Formatting: the text that goes into each column ------------------------------
def sanitise_name(raw_name: str) -> str:
    """Keep names short and printable -- basic hygiene for anything typed on a kiosk."""
    cleaned = "".join(ch for ch in raw_name if ch.isprintable()).strip()
    cleaned = cleaned[:NAME_MAX]
    return cleaned or "PLAYER"


def format_time(secs):
    return f"{secs:0.2f}s"            # 174.52s -- same as the game's finish screen


def format_penalty(secs):
    return f"+{secs:0.0f}s"           # +30s  (+0s for a perfect run)


def format_correct(right, total):
    return f"{right}/{total}"         # 7/9


def make_row(name, time_secs, penalty_secs, questions_correct, questions_total):
    """The values for one scoreboard row, as the text the columns expect."""
    return {
        "username": sanitise_name(name)[:99],
        "time": format_time(time_secs),
        "penalty": format_penalty(penalty_secs),
        "correct": format_correct(questions_correct, questions_total),
    }


# --- Config ------------------------------------------------------------------------
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def load_config(path=CONFIG_PATH):
    """(config, None) when it's filled in, or (None, "what's wrong") when it isn't."""
    try:
        with open(path) as f:
            saved = json.load(f)
    except FileNotFoundError:
        return None, "scoreboard not set up (no scoreboard_config.json)"
    except (OSError, ValueError):
        return None, "scoreboard_config.json can't be read (check it's valid JSON)"
    if not isinstance(saved, dict):
        return None, "scoreboard_config.json can't be read (check it's valid JSON)"
    cfg = dict(CONFIG_TEMPLATE)
    cfg.update({k: v for k, v in saved.items() if k in CONFIG_TEMPLATE})
    missing = [k for k in ("host", "user") if not str(cfg[k]).strip()]
    if missing:
        return None, f"scoreboard not set up (fill in {', '.join(missing)} in scoreboard_config.json)"
    if not _IDENT.match(str(cfg["table"])):
        return None, "the table name in scoreboard_config.json can only use letters, numbers and _"
    return cfg, None


def write_template(path=CONFIG_PATH):
    """Create a blank scoreboard_config.json to fill in (never overwrites one)."""
    if not os.path.exists(path):
        with open(path, "w") as f:
            json.dump(CONFIG_TEMPLATE, f, indent=2)


SYSTEM_DATABASES = {"information_schema", "performance_schema", "mysql", "sys"}


def connect(cfg):
    """Open a connection to the MySQL server in the config.

    If "database" is left blank, it's found automatically: the database this
    user can see that holds the scoreboard table (or the only one they can see)."""
    import pymysql   # imported here so the game still starts if PyMySQL isn't installed yet
    t = cfg["timeout_secs"]
    conn = pymysql.connect(
        host=cfg["host"], port=int(cfg["port"]), user=cfg["user"], password=cfg["password"],
        database=cfg["database"] or None, connect_timeout=t, read_timeout=t, write_timeout=t,
        ssl={} if cfg["ssl"] else None, autocommit=True, charset="utf8mb4",
    )
    if not cfg["database"]:
        try:
            cfg["database"] = find_database(conn, cfg["table"])
            conn.select_db(cfg["database"])
        except Exception:
            conn.close()
            raise
    return conn


def find_database(conn, table):
    """The name of the database holding `table`, among those this user can see."""
    with conn.cursor() as cur:
        cur.execute("SHOW DATABASES")
        names = [r[0] for r in cur.fetchall() if r[0].lower() not in SYSTEM_DATABASES]
        with_table = []
        for name in names:
            cur.execute(f"SHOW TABLES FROM `{name}` LIKE %s", (table,))
            if cur.fetchone():
                with_table.append(name)
    if len(with_table) == 1:
        return with_table[0]
    if not with_table and len(names) == 1:
        return names[0]
    if not names:
        raise RuntimeError("this MySQL user can't see any databases -- fill in \"database\" in scoreboard_config.json")
    raise RuntimeError(f"couldn't tell which database to use ({', '.join(names)}) -- "
                       f"fill in \"database\" in scoreboard_config.json")


def insert_sql(table):
    # Values are passed separately as %s parameters, never pasted into the SQL,
    # so whatever a player types as their name can't change the query.
    return (f"INSERT INTO `{table}` (username, time, penalty, correct, isshown) "
            f"VALUES (%s, %s, %s, %s, 1)")


# --- Sending -------------------------------------------------------------------------
class Scoreboard:
    """Sends rows to MySQL in the background and remembers any that failed.

    status is one of:
      "idle"        nothing sent yet
      "sending"     a send is in progress
      "sent"        everything has reached the scoreboard
      "offline"     couldn't reach it -- will try again (message says why)
      "not_set_up"  scoreboard_config.json isn't filled in (message says what's missing)
    """

    def __init__(self, config_path=CONFIG_PATH, connect_fn=connect):
        self.config_path = config_path
        self.connect_fn = connect_fn
        self.pending = []            # rows not yet on the scoreboard
        self.status = "idle"
        self.message = ""
        self._lock = threading.Lock()
        self._thread = None

    def submit(self, row):
        """Queue a row and start sending it. Returns straight away."""
        with self._lock:
            self.pending.append(row)
        self.retry()

    def retry(self):
        """Send anything still waiting (does nothing if the queue is empty)."""
        with self._lock:
            if not self.pending or (self._thread and self._thread.is_alive()):
                return
            self.status = "sending"
            self._thread = threading.Thread(target=self._send_pending, daemon=True)
            self._thread.start()

    def wait(self, timeout=None):
        """Block until the current send finishes (used by tests and the self-check)."""
        t = self._thread
        if t:
            t.join(timeout)

    def _send_pending(self):
        cfg, problem = load_config(self.config_path)
        if cfg is None:
            self._set("not_set_up", problem)
            return
        conn = None
        try:
            conn = self.connect_fn(cfg)
            sql = insert_sql(cfg["table"])
            with conn.cursor() as cur:
                while True:
                    with self._lock:
                        if not self.pending:
                            break
                        row = self.pending[0]
                    cur.execute(sql, (row["username"], row["time"], row["penalty"], row["correct"]))
                    if hasattr(conn, "commit"):
                        conn.commit()
                    with self._lock:
                        self.pending.pop(0)      # only removed once it's safely in MySQL
            self._set("sent", "")
        except ImportError:
            self._set("offline", "PyMySQL isn't installed -- run: pip install pymysql")
        except Exception as e:  # network down, wrong password, missing table...
            self._set("offline", _short_reason(e))
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    def _set(self, status, message):
        with self._lock:
            self.status = status
            self.message = message


def _short_reason(e):
    """A one-line reason for the screen, from a PyMySQL error like (2003, "Can't connect ...")."""
    args = getattr(e, "args", ())
    text = str(args[1]) if len(args) >= 2 else str(e)
    text = text.split("\n")[0]
    return (text[:90] + "...") if len(text) > 90 else (text or type(e).__name__)


# --- Self-check ------------------------------------------------------------------------
def check_connection(path=CONFIG_PATH):
    """Connect with the real config and check the table has the right columns.
    Sends nothing, so nothing appears on the big screen."""
    cfg, problem = load_config(path)
    if cfg is None:
        write_template(path)
        print(problem[0].upper() + problem[1:] + ".")
        print(f"Fill in {path} and run this again.")
        return False
    print(f"Connecting to {cfg['user']}@{cfg['host']}:{cfg['port']} ...")
    conn = connect(cfg)
    print(f"  database: {cfg['database']}")
    try:
        with conn.cursor() as cur:
            cur.execute(f"SHOW COLUMNS FROM `{cfg['table']}`")
            cols = {r[0].lower(): r[1] for r in cur.fetchall()}
            cur.execute(f"SELECT COUNT(*) FROM `{cfg['table']}`")
            count = cur.fetchone()[0]
    finally:
        conn.close()
    need = ["id", "username", "time", "penalty", "correct", "isshown"]
    missing = [c for c in need if c not in cols]
    for c in need:
        print(f"  {c:9s} {cols.get(c, 'MISSING')}")
    if missing:
        print(f"Connected, but the table `{cfg['table']}` is missing: {', '.join(missing)}")
        return False
    print(f"OK: connected, table `{cfg['table']}` has every column, {count} rows so far.")
    return True


def _self_test():
    """Checks the sending logic against a pretend MySQL server (no network needed)."""
    import tempfile

    class FakeCursor:
        def __init__(self, db): self.db = db
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def execute(self, sql, params):
            if self.db.fail_next:
                self.db.fail_next -= 1
                raise ConnectionError(2003, "Can't connect to MySQL server")
            self.db.rows.append((sql, params))

    class FakeConn:
        def __init__(self, db): self.db = db
        def cursor(self): return FakeCursor(self.db)
        def commit(self): pass
        def close(self): pass

    class FakeDB:
        def __init__(self): self.rows, self.fail_next, self.connects = [], 0, 0
        def connect(self, cfg):
            self.connects += 1
            return FakeConn(self)

    tmp = os.path.join(tempfile.mkdtemp(), "scoreboard_config.json")

    # formatting: exactly the text that goes in each column
    row = make_row("  Reece\x07  ", 174.524, 30, 7, 9)
    assert row == {"username": "Reece", "time": "174.52s", "penalty": "+30s", "correct": "7/9"}, row
    assert make_row("x" * 40, 60, 0, 3, 3)["username"] == "x" * NAME_MAX
    assert make_row("", 60, 0, 0, 3)["username"] == "PLAYER"
    assert insert_sql("scoreboard").endswith("VALUES (%s, %s, %s, %s, 1)"), "isshown must always be 1"

    # not set up -> nothing sent, says what's missing, score kept for later
    db = FakeDB()
    sb = Scoreboard(tmp, db.connect)
    sb.submit(row); sb.wait(5)
    assert sb.status == "not_set_up" and "scoreboard_config.json" in sb.message and len(sb.pending) == 1
    write_template(tmp)
    sb.retry(); sb.wait(5)
    assert sb.status == "not_set_up" and "host" in sb.message, sb.message
    assert db.connects == 0

    # bad table names are refused
    with open(tmp, "w") as f:
        json.dump(dict(CONFIG_TEMPLATE, host="h", database="d", user="u", table="x; DROP TABLE y"), f)
    assert load_config(tmp)[0] is None

    # filled in -> the waiting score is sent, with isshown = 1
    with open(tmp, "w") as f:
        json.dump(dict(CONFIG_TEMPLATE, host="h", database="d", user="u"), f)
    sb.retry(); sb.wait(5)
    assert sb.status == "sent" and sb.pending == [], (sb.status, sb.message)
    sql, params = db.rows[0]
    assert params == ("Reece", "174.52s", "+30s", "7/9") and "isshown" in sql

    # offline -> kept, then sent on the next try; never sent twice
    db.fail_next = 1
    sb.submit(make_row("Ava", 180.0, 10, 8, 9)); sb.wait(5)
    assert sb.status == "offline" and "Can't connect" in sb.message and len(sb.pending) == 1
    sb.submit(make_row("Sam", 190.0, 20, 6, 9)); sb.wait(5)
    assert sb.status == "sent" and sb.pending == []
    assert [p[0] for _, p in db.rows] == ["Reece", "Ava", "Sam"], db.rows

    # the name goes in as a parameter, never into the SQL text itself
    sb.submit(make_row("Bob'); DROP--", 100, 0, 9, 9)); sb.wait(5)
    sql, params = db.rows[-1]
    assert "Bob" not in sql and params[0] == "Bob'); DROP--"

    # a blank database name is found automatically
    class DBCursor:
        def __init__(self, dbs): self.dbs, self.last = dbs, []
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def execute(self, sql, params=None):
            if sql == "SHOW DATABASES":
                self.last = [(d,) for d in ["information_schema"] + list(self.dbs)]
            else:
                db = sql.split("`")[1]
                self.last = [(params[0],)] if params[0] in self.dbs[db] else []
        def fetchall(self): return self.last
        def fetchone(self): return self.last[0] if self.last else None

    class DBConn:
        def __init__(self, dbs): self.dbs = dbs
        def cursor(self): return DBCursor(self.dbs)
    assert find_database(DBConn({"freedb_cyber": ["scoreboard"], "other": []}), "scoreboard") == "freedb_cyber"
    assert find_database(DBConn({"only_one": []}), "scoreboard") == "only_one"
    try:
        find_database(DBConn({"a": [], "b": []}), "scoreboard")
        raise AssertionError("should ask for the database name when it can't tell")
    except RuntimeError as e:
        assert "fill in" in str(e)

    print("OK: scoreboard rows formatted, isshown=1, sent in the background, kept and retried when offline,")
    print("    and a blank database name is found automatically.")


if __name__ == "__main__":
    import sys
    _self_test()
    if os.path.exists(CONFIG_PATH) or "--check" in sys.argv:
        print()
        try:
            check_connection()
        except Exception as e:
            print(f"Couldn't connect: {_short_reason(e)}")
    else:
        write_template()
        print(f"\nNext: fill in {CONFIG_PATH} and run `python3 scoreboard.py` again to check the connection.")
