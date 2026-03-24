import os
import json
import hashlib
import urllib.request
import urllib.error

# ── Turso HTTP client ─────────────────────────────────────────────────────────

TURSO_URL   = os.environ.get("TURSO_DB_URL", "").replace("libsql://", "https://")
TURSO_TOKEN = os.environ.get("TURSO_DB_TOKEN", "")


def _execute(statements):
    """
    Execute one or more SQL statements via Turso HTTP API.
    `statements` is a list of {"q": "SQL", "params": [...]} dicts.
    Returns list of result sets.
    """
    if not TURSO_URL or not TURSO_TOKEN:
        raise RuntimeError("TURSO_DB_URL / TURSO_DB_TOKEN env vars not set")

    payload = json.dumps({"requests": [
        {"type": "execute", "stmt": {"sql": s["q"], "args": [
            {"type": "text", "value": str(p)} if isinstance(p, str)
            else {"type": "integer", "value": int(p)} if isinstance(p, int)
            else {"type": "null"} if p is None
            else {"type": "text", "value": str(p)}
            for p in s.get("params", [])
        ]}}
        for s in statements
    ] + [{"type": "close"}]}).encode()

    req = urllib.request.Request(
        f"{TURSO_URL}/v2/pipeline",
        data=payload,
        headers={
            "Authorization": f"Bearer {TURSO_TOKEN}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Turso HTTP {e.code}: {e.read().decode()}")

    results = []
    for item in data.get("results", []):
        if item.get("type") == "error":
            raise RuntimeError(f"Turso error: {item}")
        if item.get("type") == "ok":
            results.append(item.get("response", {}).get("result", {}))
    return results


def _q(sql, params=None):
    """Run a single query, return list of row dicts."""
    res = _execute([{"q": sql, "params": params or []}])
    if not res:
        return []
    result = res[0]
    cols = [c["name"] for c in result.get("cols", [])]
    return [dict(zip(cols, [v.get("value") for v in row])) for row in result.get("rows", [])]


def _run(sql, params=None):
    """Run a single statement (INSERT/UPDATE/DELETE), return last insert rowid."""
    res = _execute([{"q": sql, "params": params or []}])
    if res:
        return res[0].get("last_insert_rowid")
    return None


def _run_many(statements):
    """Run multiple statements in one pipeline."""
    _execute(statements)


# ── Password hashing ──────────────────────────────────────────────────────────

def hash_password(password):
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return salt.hex() + ":" + dk.hex()


def verify_password(password, stored):
    salt_hex, dk_hex = stored.split(":")
    salt = bytes.fromhex(salt_hex)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return dk.hex() == dk_hex


# ── DB init ───────────────────────────────────────────────────────────────────

def init_db():
    stmts = [
        {"q": """CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            profile_type TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )"""},
        {"q": """CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            whatsapp TEXT,
            skills TEXT NOT NULL,
            skill_level TEXT NOT NULL,
            interests TEXT NOT NULL,
            wants TEXT NOT NULL,
            availability INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )"""},
        {"q": """CREATE TABLE IF NOT EXISTS startups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            startup_name TEXT NOT NULL,
            email TEXT NOT NULL,
            whatsapp TEXT,
            skills_needed TEXT NOT NULL,
            industry TEXT NOT NULL,
            offers TEXT NOT NULL,
            commitment INTEGER NOT NULL,
            remote_physical TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )"""},
        {"q": """CREATE TABLE IF NOT EXISTS matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            startup_id INTEGER NOT NULL,
            score INTEGER NOT NULL DEFAULT 0,
            matched_skills TEXT,
            matched_interests TEXT,
            matched_wants TEXT,
            student_accepted INTEGER DEFAULT 0,
            startup_accepted INTEGER DEFAULT 0,
            student_seen INTEGER DEFAULT 0,
            startup_seen INTEGER DEFAULT 0,
            email_sent INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )"""},
        {"q": """CREATE TABLE IF NOT EXISTS password_resets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token TEXT NOT NULL UNIQUE,
            expires_at TIMESTAMP NOT NULL,
            used INTEGER DEFAULT 0
        )"""},
    ]
    _run_many(stmts)

    # Create default admin if not exists
    existing = _q("SELECT id FROM users WHERE role='admin' LIMIT 1")
    if not existing:
        pw = hash_password("admin123")
        _run("INSERT INTO users (email, password, role) VALUES (?, ?, 'admin')",
             ["admin@octanova.com", pw])
        print("Admin created: admin@octanova.com / admin123")


# ── Compatibility shim — dict-like row access ─────────────────────────────────

class Row(dict):
    """Dict that also supports attribute and index access like sqlite3.Row."""
    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key)


def _rows(sql, params=None):
    return [Row(r) for r in _q(sql, params)]


def _row(sql, params=None):
    rows = _rows(sql, params)
    return rows[0] if rows else None


# ── Public DB interface (mirrors old sqlite3 API used in app.py) ──────────────

class FakeConn:
    """Mimics sqlite3 connection so app.py needs minimal changes."""

    def execute(self, sql, params=None):
        return FakeCursor(sql, params or [])

    def commit(self):
        pass  # Turso auto-commits

    def close(self):
        pass


class FakeCursor:
    def __init__(self, sql, params):
        self._sql    = sql
        self._params = list(params)
        self._rows   = None
        self._rowid  = None
        self._run()

    def _run(self):
        sql = self._sql.strip().upper()
        if sql.startswith("SELECT") or sql.startswith("PRAGMA"):
            self._rows = _rows(self._sql, self._params)
        else:
            self._rowid = _run(self._sql, self._params)

    def fetchone(self):
        if self._rows is None:
            return None
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows or []

    def __getitem__(self, key):
        return self._rowid


def get_db():
    return FakeConn()


# ── Matching logic ────────────────────────────────────────────────────────────

def compute_score(student, startup):
    s_skills    = set(x.strip().lower() for x in student["skills"].split(","))
    su_skills   = set(x.strip().lower() for x in startup["skills_needed"].split(","))
    s_interests = set(x.strip().lower() for x in student["interests"].split(","))
    su_industry = set(x.strip().lower() for x in startup["industry"].split(","))
    s_wants     = set(x.strip().lower() for x in student["wants"].split(","))
    su_offers   = set(x.strip().lower() for x in startup["offers"].split(","))

    matched_skills    = s_skills & su_skills
    matched_interests = s_interests & su_industry
    matched_wants     = s_wants & su_offers

    score = 0
    if matched_skills:    score += 50
    if matched_interests: score += 30
    if matched_wants:     score += 20

    return (
        score,
        ", ".join(matched_skills),
        ", ".join(matched_interests),
        ", ".join(matched_wants),
    )


def run_matching():
    from mailer import send_match_email
    students = _rows("SELECT * FROM students")
    startups = _rows("SELECT * FROM startups")

    new_matches = 0
    for student in students:
        for startup in startups:
            existing = _row(
                "SELECT id FROM matches WHERE student_id=? AND startup_id=?",
                [student["id"], startup["id"]]
            )
            if existing:
                continue

            score, m_skills, m_interests, m_wants = compute_score(student, startup)
            if score < 60:
                continue

            match_id = _run("""
                INSERT INTO matches
                    (student_id, startup_id, score, matched_skills, matched_interests, matched_wants)
                VALUES (?, ?, ?, ?, ?, ?)
            """, [student["id"], startup["id"], score, m_skills, m_interests, m_wants])

            send_match_email(
                to_email=student["email"], to_name=student["name"],
                match_type="startup", match_name=startup["startup_name"],
                industry=startup["industry"], offers=startup["offers"],
                commitment=str(startup["commitment"]), mode=startup["remote_physical"],
                matched_skills=m_skills, matched_interests=m_interests,
                matched_wants=m_wants, score=score,
            )
            send_match_email(
                to_email=startup["email"], to_name=startup["startup_name"],
                match_type="student", match_name=student["name"],
                industry=student["interests"], offers=student["wants"],
                commitment=str(student["availability"]), mode="",
                matched_skills=m_skills, matched_interests=m_interests,
                matched_wants=m_wants, score=score,
            )

            _run("UPDATE matches SET email_sent=1 WHERE id=?", [match_id])
            new_matches += 1

    return new_matches
