import libsql_experimental as libsql
import hashlib
import os

TURSO_URL   = os.environ.get("TURSO_URL", "")
TURSO_TOKEN = os.environ.get("TURSO_TOKEN", "")


class DictRow:
    """Wraps a libsql row so columns can be accessed by name like sqlite3.Row."""
    def __init__(self, cursor, row):
        self._data = {desc[0]: val for desc, val in zip(cursor.description, row)}

    def __getitem__(self, key):
        return self._data[key]

    def __contains__(self, key):
        return key in self._data

    def keys(self):
        return self._data.keys()

    def get(self, key, default=None):
        return self._data.get(key, default)


class DictCursor:
    """Wraps libsql cursor to return DictRow objects."""
    def __init__(self, cursor):
        self._cur = cursor

    @property
    def description(self):
        return self._cur.description

    @property
    def lastrowid(self):
        return self._cur.lastrowid

    def execute(self, sql, params=()):
        self._cur.execute(sql, params)
        return self

    def executescript(self, sql):
        # libsql doesn't support executescript — split and run individually
        for stmt in sql.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                self._cur.execute(stmt)
        return self

    def fetchone(self):
        row = self._cur.fetchone()
        if row is None:
            return None
        return DictRow(self._cur, row)

    def fetchall(self):
        rows = self._cur.fetchall()
        return [DictRow(self._cur, r) for r in rows]

    def __getattr__(self, name):
        return getattr(self._cur, name)


class DictConnection:
    """Wraps libsql connection to return DictCursor objects."""
    def __init__(self, conn):
        self._conn = conn

    def cursor(self):
        return DictCursor(self._conn.cursor())

    def execute(self, sql, params=()):
        cur = DictCursor(self._conn.cursor())
        cur.execute(sql, params)
        return cur

    def executescript(self, sql):
        cur = DictCursor(self._conn.cursor())
        cur.executescript(sql)
        return cur

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()


def get_db():
    conn = libsql.connect(database=TURSO_URL, auth_token=TURSO_TOKEN)
    return DictConnection(conn)

def hash_password(password):
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return salt.hex() + ":" + dk.hex()

def verify_password(password, stored):
    salt_hex, dk_hex = stored.split(":")
    salt = bytes.fromhex(salt_hex)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return dk.hex() == dk_hex

def init_db():
    conn = get_db()
    c = conn.cursor()

    c.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            profile_type TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS students (
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS startups (
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS password_resets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token TEXT NOT NULL UNIQUE,
            expires_at TIMESTAMP NOT NULL,
            used INTEGER DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS matches (
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (student_id) REFERENCES students(id),
            FOREIGN KEY (startup_id) REFERENCES startups(id)
        );
    """)
    conn.commit()

    existing = c.execute("SELECT id FROM users WHERE role='admin'").fetchone()
    if not existing:
        pw = hash_password("admin123")
        c.execute(
            "INSERT INTO users (email, password, role) VALUES (?, ?, 'admin')",
            ("admin@octanova.com", pw)
        )
        conn.commit()
        print("Admin created: admin@octanova.com / admin123")

    conn.close()


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
    conn = get_db()
    c = conn.cursor()
    students = c.execute("SELECT * FROM students").fetchall()
    startups = c.execute("SELECT * FROM startups").fetchall()

    new_matches = 0
    for student in students:
        for startup in startups:
            existing = c.execute(
                "SELECT id FROM matches WHERE student_id=? AND startup_id=?",
                (student["id"], startup["id"])
            ).fetchone()
            if existing:
                continue

            score, m_skills, m_interests, m_wants = compute_score(student, startup)

            if score >= 60:
                c.execute("""
                    INSERT INTO matches
                        (student_id, startup_id, score, matched_skills, matched_interests, matched_wants)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (student["id"], startup["id"], score, m_skills, m_interests, m_wants))
                conn.commit()

                match_id = c.execute("SELECT last_insert_rowid()").fetchone()[0]

                # Send email notifications
                send_match_email(
                    to_email=student["email"],
                    to_name=student["name"],
                    match_type="startup",
                    match_name=startup["startup_name"],
                    industry=startup["industry"],
                    offers=startup["offers"],
                    commitment=str(startup["commitment"]),
                    mode=startup["remote_physical"],
                    matched_skills=m_skills,
                    matched_interests=m_interests,
                    matched_wants=m_wants,
                    score=score,
                )
                send_match_email(
                    to_email=startup["email"],
                    to_name=startup["startup_name"],
                    match_type="student",
                    match_name=student["name"],
                    industry=student["interests"],
                    offers=student["wants"],
                    commitment=str(student["availability"]),
                    mode="",
                    matched_skills=m_skills,
                    matched_interests=m_interests,
                    matched_wants=m_wants,
                    score=score,
                )

                c.execute("UPDATE matches SET email_sent=1 WHERE id=?", (match_id,))
                new_matches += 1

    conn.commit()
    conn.close()
    return new_matches
