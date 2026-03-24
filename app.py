import os
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, session
from database import init_db, get_db, run_matching, hash_password, verify_password

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "octanova-dev-secret")

# ── Auth helpers ──────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please log in first.", "error")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user_id") or session.get("role") != "admin":
            return redirect(url_for("index"))
        return f(*args, **kwargs)
    return decorated

def unread_match_count():
    """Return count of unseen matches for the current logged-in user."""
    uid = session.get("user_id")
    ptype = session.get("profile_type")
    if not uid or not ptype:
        return 0
    conn = get_db()
    if ptype == "student":
        pid = conn.execute("SELECT id FROM students WHERE user_id=?", (uid,)).fetchone()
        if not pid:
            conn.close(); return 0
        count = conn.execute(
            "SELECT COUNT(*) FROM matches WHERE student_id=? AND student_seen=0", (pid["id"],)
        ).fetchone()[0]
    else:
        pid = conn.execute("SELECT id FROM startups WHERE user_id=?", (uid,)).fetchone()
        if not pid:
            conn.close(); return 0
        count = conn.execute(
            "SELECT COUNT(*) FROM matches WHERE startup_id=? AND startup_seen=0", (pid["id"],)
        ).fetchone()[0]
    conn.close()
    return count

@app.context_processor
def inject_notifications():
    return {"unread_count": unread_match_count()}

# ── Landing ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")

# ── Register ──────────────────────────────────────────────────────────────────

@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        email    = request.form["email"].strip().lower()
        password = request.form["password"]
        role     = request.form["role"]  # student | startup

        if len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
            return render_template("register.html")

        conn = get_db()
        existing = conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
        if existing:
            conn.close()
            flash("Email already registered.", "error")
            return render_template("register.html")

        conn.execute(
            "INSERT INTO users (email, password, role, profile_type) VALUES (?, ?, 'user', ?)",
            (email, hash_password(password), role)
        )
        conn.commit()
        user = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        conn.close()

        session["user_id"]      = user["id"]
        session["email"]        = user["email"]
        session["role"]         = user["role"]
        session["profile_type"] = role

        flash("Account created! Complete your profile.", "success")
        return redirect(url_for("student_profile") if role == "student" else url_for("startup_profile"))

    return render_template("register.html")

# ── Login / Logout ────────────────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        email    = request.form["email"].strip().lower()
        password = request.form["password"]
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        conn.close()
        if not user or not verify_password(password, user["password"]):
            flash("Invalid email or password.", "error")
            return render_template("login.html")

        session["user_id"]      = user["id"]
        session["email"]        = user["email"]
        session["role"]         = user["role"]
        session["profile_type"] = user["profile_type"]
        flash(f"Welcome back!", "success")
        return redirect(url_for("admin") if user["role"] == "admin" else url_for("dashboard"))

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out.", "success")
    return redirect(url_for("login"))

# ── Forgot password ───────────────────────────────────────────────────────────

@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        conn  = get_db()
        user  = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()

        if user:
            import secrets, datetime
            token      = secrets.token_urlsafe(32)
            expires_at = datetime.datetime.utcnow() + datetime.timedelta(hours=1)
            conn.execute(
                "INSERT INTO password_resets (user_id, token, expires_at) VALUES (?, ?, ?)",
                (user["id"], token, expires_at)
            )
            conn.commit()

            reset_url = url_for("reset_password", token=token, _external=True)
            from mailer import send_reset_email
            send_reset_email(to_email=email, reset_url=reset_url)

        conn.close()
        # Always show success to prevent email enumeration
        flash("If that email exists, a reset link has been sent.", "success")
        return redirect(url_for("login"))

    return render_template("forgot_password.html")


@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    import datetime
    conn  = get_db()
    reset = conn.execute(
        "SELECT * FROM password_resets WHERE token=? AND used=0", (token,)
    ).fetchone()

    if not reset:
        conn.close()
        flash("Invalid or expired reset link.", "error")
        return redirect(url_for("forgot_password"))

    # Check expiry
    expires_at = datetime.datetime.fromisoformat(reset["expires_at"])
    if datetime.datetime.utcnow() > expires_at:
        conn.close()
        flash("This reset link has expired. Please request a new one.", "error")
        return redirect(url_for("forgot_password"))

    if request.method == "POST":
        password = request.form["password"]
        confirm  = request.form["confirm"]

        if len(password) < 6:
            conn.close()
            flash("Password must be at least 6 characters.", "error")
            return render_template("reset_password.html", token=token)

        if password != confirm:
            conn.close()
            flash("Passwords do not match.", "error")
            return render_template("reset_password.html", token=token)

        conn.execute("UPDATE users SET password=? WHERE id=?",
                     (hash_password(password), reset["user_id"]))
        conn.execute("UPDATE password_resets SET used=1 WHERE token=?", (token,))
        conn.commit()
        conn.close()
        flash("Password updated! You can now log in.", "success")
        return redirect(url_for("login"))

    conn.close()
    return render_template("reset_password.html", token=token)

# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.route("/dashboard")
@login_required
def dashboard():
    uid   = session["user_id"]
    ptype = session.get("profile_type")
    conn  = get_db()

    profile = None
    match_count = 0

    if ptype == "student":
        profile = conn.execute("SELECT * FROM students WHERE user_id=?", (uid,)).fetchone()
        if profile:
            match_count = conn.execute(
                "SELECT COUNT(*) FROM matches WHERE student_id=?", (profile["id"],)
            ).fetchone()[0]
    elif ptype == "startup":
        profile = conn.execute("SELECT * FROM startups WHERE user_id=?", (uid,)).fetchone()
        if profile:
            match_count = conn.execute(
                "SELECT COUNT(*) FROM matches WHERE startup_id=?", (profile["id"],)
            ).fetchone()[0]

    conn.close()
    return render_template("dashboard.html", profile=profile, ptype=ptype, match_count=match_count)

# ── Student profile ───────────────────────────────────────────────────────────

@app.route("/profile/student", methods=["GET", "POST"])
@login_required
def student_profile():
    uid  = session["user_id"]
    conn = get_db()
    existing = conn.execute("SELECT * FROM students WHERE user_id=?", (uid,)).fetchone()

    if request.method == "POST":
        data = (
            request.form["name"],
            request.form["email"].strip().lower(),
            request.form.get("whatsapp", "").strip(),
            request.form["skills"],
            request.form["skill_level"],
            request.form["interests"],
            ", ".join(request.form.getlist("wants")),
            request.form["availability"],
            uid,
        )
        if existing:
            conn.execute("""
                UPDATE students SET name=?, email=?, whatsapp=?, skills=?, skill_level=?,
                interests=?, wants=?, availability=? WHERE user_id=?
            """, data)
        else:
            conn.execute("""
                INSERT INTO students (name, email, whatsapp, skills, skill_level, interests, wants, availability, user_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, data)
        conn.execute("UPDATE users SET profile_type='student' WHERE id=?", (uid,))
        conn.commit()
        conn.close()
        session["profile_type"] = "student"
        run_matching()
        flash("Profile saved!", "success")
        return redirect(url_for("dashboard"))

    conn.close()
    return render_template("student.html", profile=existing)

# ── Startup profile ───────────────────────────────────────────────────────────

@app.route("/profile/startup", methods=["GET", "POST"])
@login_required
def startup_profile():
    uid  = session["user_id"]
    conn = get_db()
    existing = conn.execute("SELECT * FROM startups WHERE user_id=?", (uid,)).fetchone()

    if request.method == "POST":
        data = (
            request.form["startup_name"],
            request.form["email"].strip().lower(),
            request.form.get("whatsapp", "").strip(),
            request.form["skills_needed"],
            request.form["industry"],
            ", ".join(request.form.getlist("offers")),
            request.form["commitment"],
            request.form["remote_physical"],
            uid,
        )
        if existing:
            conn.execute("""
                UPDATE startups SET startup_name=?, email=?, whatsapp=?, skills_needed=?, industry=?,
                offers=?, commitment=?, remote_physical=? WHERE user_id=?
            """, data)
        else:
            conn.execute("""
                INSERT INTO startups (startup_name, email, whatsapp, skills_needed, industry, offers, commitment, remote_physical, user_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, data)
        conn.execute("UPDATE users SET profile_type='startup' WHERE id=?", (uid,))
        conn.commit()
        conn.close()
        session["profile_type"] = "startup"
        run_matching()
        flash("Profile saved!", "success")
        return redirect(url_for("dashboard"))

    conn.close()
    return render_template("startup.html", profile=existing)

# ── Matches ───────────────────────────────────────────────────────────────────

@app.route("/matches")
@login_required
def matches():
    from urllib.parse import quote
    uid   = session["user_id"]
    ptype = session.get("profile_type")
    conn  = get_db()

    def wa_url(number, message):
        """Build a wa.me deep-link that opens a pre-filled DM."""
        if not number:
            return None
        clean = number.replace("+", "").replace(" ", "").replace("-", "")
        return f"https://wa.me/{clean}?text={quote(message, safe='')}"

    def email_url(address, subject, body):
        if not address:
            return None
        return f"mailto:{address}?subject={quote(subject, safe='')}&body={quote(body, safe='')}"

    if ptype == "student":
        profile = conn.execute("SELECT * FROM students WHERE user_id=?", (uid,)).fetchone()
        if not profile:
            conn.close()
            flash("Complete your profile first.", "error")
            return redirect(url_for("student_profile"))
        raw = conn.execute("""
            SELECT m.id, m.score, m.matched_skills, m.matched_interests, m.matched_wants,
                   m.student_accepted, m.startup_accepted,
                   s.startup_name, s.industry, s.offers, s.commitment, s.remote_physical,
                   s.email AS match_email, s.whatsapp AS match_whatsapp
            FROM matches m JOIN startups s ON m.startup_id = s.id
            WHERE m.student_id = ?
            ORDER BY m.score DESC
        """, (profile["id"],)).fetchall()
        conn.execute("UPDATE matches SET student_seen=1 WHERE student_id=?", (profile["id"],))
        conn.commit()
        conn.close()

        rows = []
        for m in raw:
            m = dict(m)
            skills    = m["matched_skills"] or "our shared interests"
            industry  = m["industry"] or ""
            offers    = m["offers"] or ""
            name      = m["startup_name"]

            wa_msg = (
                f"Hi {name}! 👋\n\n"
                f"I found you through OctaNova — we matched based on my skills in {skills}.\n\n"
                f"I'm really interested in what you're building in {industry} "
                f"and would love to explore how I can contribute.\n\n"
                f"Looking forward to connecting!"
            )
            email_subj = "OctaNova Match – Let's Connect!"
            email_body = (
                f"Hi {name},\n\n"
                f"I found you through OctaNova. We matched based on my skills in {skills} "
                f"and your work in {industry}.\n\n"
                f"I'm looking for {offers} and would love to learn more about what you're building.\n\n"
                f"Looking forward to connecting!"
            )
            m["wa_link"]    = wa_url(m["match_whatsapp"], wa_msg)
            m["email_link"] = email_url(m["match_email"], email_subj, email_body)
            rows.append(m)

    else:
        profile = conn.execute("SELECT * FROM startups WHERE user_id=?", (uid,)).fetchone()
        if not profile:
            conn.close()
            flash("Complete your profile first.", "error")
            return redirect(url_for("startup_profile"))
        raw = conn.execute("""
            SELECT m.id, m.score, m.matched_skills, m.matched_interests, m.matched_wants,
                   m.student_accepted, m.startup_accepted,
                   st.name, st.skills, st.interests, st.availability,
                   st.email AS match_email, st.whatsapp AS match_whatsapp
            FROM matches m JOIN students st ON m.student_id = st.id
            WHERE m.startup_id = ?
            ORDER BY m.score DESC
        """, (profile["id"],)).fetchall()
        conn.execute("UPDATE matches SET startup_seen=1 WHERE startup_id=?", (profile["id"],))
        conn.commit()
        conn.close()

        rows = []
        for m in raw:
            m = dict(m)
            skills   = m["matched_skills"] or "your background"
            industry = profile["industry"] or ""
            offers   = profile["offers"] or ""
            name     = m["name"]

            wa_msg = (
                f"Hi {name}! 👋\n\n"
                f"I found you through OctaNova — we matched because your skills in {skills} "
                f"are exactly what we need.\n\n"
                f"We're building in {industry} and we offer {offers}. "
                f"Would love to chat about working together!"
            )
            email_subj = "OctaNova Match – Opportunity for You!"
            email_body = (
                f"Hi {name},\n\n"
                f"I found you through OctaNova. We matched because your skills in {skills} "
                f"are a great fit for what we're building.\n\n"
                f"We're a startup in {industry} and we offer {offers}. "
                f"I'd love to chat about a potential collaboration.\n\n"
                f"Looking forward to connecting!"
            )
            m["wa_link"]    = wa_url(m["match_whatsapp"], wa_msg)
            m["email_link"] = email_url(m["match_email"], email_subj, email_body)
            rows.append(m)

    return render_template("matches.html", matches=rows, user_type=ptype)

@app.route("/accept/<int:match_id>", methods=["POST"])
@login_required
def accept_match(match_id):
    ptype = session.get("profile_type")
    conn  = get_db()
    if ptype == "student":
        conn.execute("UPDATE matches SET student_accepted=1 WHERE id=?", (match_id,))
    else:
        conn.execute("UPDATE matches SET startup_accepted=1 WHERE id=?", (match_id,))
    conn.commit()
    conn.close()
    flash("Match accepted!", "success")
    return redirect(url_for("matches"))

# ── Admin ─────────────────────────────────────────────────────────────────────

@app.route("/admin")
@admin_required
def admin():
    conn     = get_db()
    students = conn.execute("SELECT * FROM students ORDER BY created_at DESC").fetchall()
    startups = conn.execute("SELECT * FROM startups ORDER BY created_at DESC").fetchall()
    matches  = conn.execute("""
        SELECT m.id, m.score, m.student_accepted, m.startup_accepted,
               st.name AS student_name, s.startup_name, m.created_at
        FROM matches m
        JOIN students st ON m.student_id = st.id
        JOIN startups s  ON m.startup_id = s.id
        ORDER BY m.created_at DESC
    """).fetchall()
    conn.close()
    return render_template("admin.html", students=students, startups=startups, matches=matches)

@app.route("/admin/manual_match", methods=["POST"])
@admin_required
def manual_match():
    student_id = request.form["student_id"]
    startup_id = request.form["startup_id"]
    conn = get_db()
    existing = conn.execute(
        "SELECT id FROM matches WHERE student_id=? AND startup_id=?",
        (student_id, startup_id)
    ).fetchone()
    if not existing:
        conn.execute(
            "INSERT INTO matches (student_id, startup_id, score) VALUES (?, ?, 100)",
            (student_id, startup_id)
        )
        conn.commit()
        flash("Manual match created.", "success")
    else:
        flash("Match already exists.", "error")
    conn.close()
    return redirect(url_for("admin"))

# Always initialize DB — runs on import, works with gunicorn and python app.py
with app.app_context():
    init_db()

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_ENV") != "production")
