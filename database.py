import os
import hashlib
import pymysql
import pymysql.cursors

# ── Connection ────────────────────────────────────────────────────────────────

DB_HOST = os.environ.get("MYSQL_HOST", "caboose.proxy.rlwy.net")
DB_PORT = int(os.environ.get("MYSQL_PORT", 22081))
DB_USER = os.environ.get("MYSQL_USER", "root")
DB_PASS = os.environ.get("MYSQL_PASSWORD", "")
DB_NAME = os.environ.get("MYSQL_DATABASE", "railway")


def get_db():
    conn = pymysql.connect(
        host=DB_HOST, port=DB_PORT,
        user=DB_USER, password=DB_PASS,
        database=DB_NAME,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
        connect_timeout=10,
    )
    return DBConn(conn)


class DBConn:
    """Wraps pymysql connection to mimic sqlite3 interface used in app.py."""

    def __init__(self, conn):
        self._conn = conn
        self._cursor = conn.cursor()

    def execute(self, sql, params=None):
        self._cursor.execute(sql, params or ())
        return self._cursor

    def commit(self):
        self._conn.commit()

    def close(self):
        self._cursor.close()
        self._conn.close()


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
    conn = get_db()
    c = conn.cursor()

    c.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTO_INCREMENT,
        email VARCHAR(255) NOT NULL UNIQUE,
        password TEXT NOT NULL,
        role VARCHAR(20) NOT NULL DEFAULT 'user',
        profile_type VARCHAR(20),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS students (
        id INTEGER PRIMARY KEY AUTO_INCREMENT,
        user_id INTEGER NOT NULL UNIQUE,
        name VARCHAR(255) NOT NULL,
        email VARCHAR(255) NOT NULL,
        whatsapp VARCHAR(50),
        skills TEXT NOT NULL,
        skill_level VARCHAR(20) NOT NULL,
        interests TEXT NOT NULL,
        wants TEXT NOT NULL,
        availability INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS startups (
        id INTEGER PRIMARY KEY AUTO_INCREMENT,
        user_id INTEGER NOT NULL UNIQUE,
        startup_name VARCHAR(255) NOT NULL,
        email VARCHAR(255) NOT NULL,
        whatsapp VARCHAR(50),
        skills_needed TEXT NOT NULL,
        industry TEXT NOT NULL,
        offers TEXT NOT NULL,
        commitment INTEGER NOT NULL,
        remote_physical VARCHAR(20) NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS matches (
        id INTEGER PRIMARY KEY AUTO_INCREMENT,
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
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS password_resets (
        id INTEGER PRIMARY KEY AUTO_INCREMENT,
        user_id INTEGER NOT NULL,
        token VARCHAR(255) NOT NULL UNIQUE,
        expires_at TIMESTAMP NOT NULL,
        used INTEGER DEFAULT 0
    )""")

    # Default admin
    c.execute("SELECT id FROM users WHERE role='admin' LIMIT 1")
    if not c.fetchone():
        pw = hash_password("admin123")
        c.execute(
            "INSERT INTO users (email, password, role) VALUES (%s, %s, 'admin')",
            ("admin@octanova.com", pw)
        )
        print("Admin created: admin@octanova.com / admin123")

    conn.close()


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
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT * FROM students")
    students = c.fetchall()
    c.execute("SELECT * FROM startups")
    startups = c.fetchall()

    new_matches = 0
    for student in students:
        for startup in startups:
            c.execute(
                "SELECT id FROM matches WHERE student_id=%s AND startup_id=%s",
                (student["id"], startup["id"])
            )
            if c.fetchone():
                continue

            score, m_skills, m_interests, m_wants = compute_score(student, startup)
            if score < 60:
                continue

            c.execute("""
                INSERT INTO matches
                    (student_id, startup_id, score, matched_skills, matched_interests, matched_wants)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (student["id"], startup["id"], score, m_skills, m_interests, m_wants))

            match_id = c.lastrowid

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

            c.execute("UPDATE matches SET email_sent=1 WHERE id=%s", (match_id,))
            new_matches += 1

    conn.close()
    return new_matches
