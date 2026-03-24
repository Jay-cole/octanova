"""
Email notifications via SMTP.

Configure by setting environment variables (or editing the defaults below):
  OCTANOVA_SMTP_HOST   — default: smtp.gmail.com
  OCTANOVA_SMTP_PORT   — default: 587
  OCTANOVA_SMTP_USER   — your Gmail address
  OCTANOVA_SMTP_PASS   — your Gmail App Password (not your login password)
  OCTANOVA_FROM_EMAIL  — sender address (defaults to SMTP_USER)

To get a Gmail App Password:
  Google Account → Security → 2-Step Verification → App passwords
"""

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

SMTP_HOST  = os.environ.get("OCTANOVA_SMTP_HOST", "smtp.gmail.com")
SMTP_PORT  = int(os.environ.get("OCTANOVA_SMTP_PORT", 587))
SMTP_USER  = os.environ.get("OCTANOVA_SMTP_USER", "")
SMTP_PASS  = os.environ.get("OCTANOVA_SMTP_PASS", "")
FROM_EMAIL = os.environ.get("OCTANOVA_FROM_EMAIL", SMTP_USER)


def send_match_email(
    to_email, to_name, match_type,
    match_name, industry, offers, commitment, mode,
    matched_skills, matched_interests, matched_wants, score
):
    """Send a match notification email. Silently skips if SMTP is not configured."""
    if not SMTP_USER or not SMTP_PASS:
        print(f"[mailer] SMTP not configured — skipping email to {to_email}")
        return

    subject = f"⬡ OctaNova — You have a new match! ({score}% compatibility)"

    if match_type == "startup":
        entity_label = "Startup"
        detail_label = "Industry"
        offer_label  = "What they offer"
        commit_label = "Commitment"
        mode_line    = f"<li><strong>Work mode:</strong> {mode.capitalize()}</li>" if mode else ""
    else:
        entity_label = "Student"
        detail_label = "Interests"
        offer_label  = "Looking for"
        commit_label = "Availability (hrs/wk)"
        mode_line    = ""

    reasons = []
    if matched_skills:
        reasons.append(f"Matching skills: <strong>{matched_skills}</strong>")
    if matched_interests:
        reasons.append(f"Shared interest in: <strong>{matched_interests}</strong>")
    if matched_wants:
        reasons.append(f"Aligned on: <strong>{matched_wants}</strong>")
    reasons_html = "".join(f"<li>{r}</li>" for r in reasons)

    html = f"""
    <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
                background:#0f0f13;color:#e2e8f0;padding:40px 0;min-height:100vh">
      <div style="max-width:560px;margin:0 auto;background:#1a1a2e;border-radius:16px;
                  overflow:hidden;border:1px solid #2d2d44">

        <!-- Header -->
        <div style="background:linear-gradient(135deg,#6366f1,#8b5cf6);padding:32px;text-align:center">
          <div style="font-size:2rem;margin-bottom:8px">⬡</div>
          <h1 style="margin:0;font-size:1.4rem;color:#fff;font-weight:700">OctaNova</h1>
          <p style="margin:6px 0 0;color:rgba(255,255,255,.8);font-size:.9rem">Opportunity Engine</p>
        </div>

        <!-- Body -->
        <div style="padding:32px">
          <p style="color:#a5b4fc;font-size:.85rem;text-transform:uppercase;
                    letter-spacing:.1em;margin-bottom:8px">New Match</p>
          <h2 style="margin:0 0 6px;font-size:1.3rem;color:#f1f5f9">
            Hi {to_name}, you matched!
          </h2>
          <p style="color:#94a3b8;margin:0 0 24px;font-size:.95rem">
            You have a <strong style="color:#818cf8">{score}% compatibility</strong>
            match with a {entity_label.lower()}.
          </p>

          <!-- Match card -->
          <div style="background:#0f0f1a;border:1px solid #2d2d44;border-radius:12px;padding:20px;margin-bottom:24px">
            <p style="margin:0 0 4px;font-size:.75rem;color:#6366f1;
                      text-transform:uppercase;letter-spacing:.08em">{entity_label}</p>
            <h3 style="margin:0 0 16px;font-size:1.1rem;color:#f1f5f9">{match_name}</h3>
            <ul style="list-style:none;padding:0;margin:0;color:#94a3b8;font-size:.88rem">
              <li style="margin-bottom:6px"><strong style="color:#cbd5e1">{detail_label}:</strong> {industry}</li>
              <li style="margin-bottom:6px"><strong style="color:#cbd5e1">{offer_label}:</strong> {offers}</li>
              <li style="margin-bottom:6px"><strong style="color:#cbd5e1">{commit_label}:</strong> {commitment} hrs/week</li>
              {mode_line}
            </ul>
          </div>

          <!-- Why matched -->
          <div style="background:#1e1b4b;border-left:3px solid #6366f1;
                      border-radius:0 8px 8px 0;padding:16px;margin-bottom:24px">
            <p style="margin:0 0 10px;font-size:.85rem;font-weight:600;color:#a5b4fc">
              Why you matched:
            </p>
            <ul style="margin:0;padding-left:16px;color:#94a3b8;font-size:.85rem;line-height:1.7">
              {reasons_html}
            </ul>
          </div>

          <!-- CTA -->
          <div style="text-align:center">
            <a href="http://127.0.0.1:5000/matches"
               style="display:inline-block;background:linear-gradient(135deg,#6366f1,#8b5cf6);
                      color:#fff;text-decoration:none;padding:12px 32px;border-radius:8px;
                      font-weight:600;font-size:.95rem">
              View Your Match →
            </a>
          </div>
        </div>

        <!-- Footer -->
        <div style="padding:20px 32px;border-top:1px solid #2d2d44;text-align:center">
          <p style="margin:0;font-size:.78rem;color:#475569">
            OctaNova Opportunity Engine · You're receiving this because you registered on the platform.
          </p>
        </div>
      </div>
    </div>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"OctaNova ⬡ <{FROM_EMAIL}>"
    msg["To"]      = to_email
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(FROM_EMAIL, to_email, msg.as_string())
        print(f"[mailer] Email sent to {to_email}")
    except Exception as e:
        print(f"[mailer] Failed to send to {to_email}: {e}")


def send_reset_email(to_email, reset_url):
    """Send a password reset email."""
    if not SMTP_USER or not SMTP_PASS:
        print(f"[mailer] SMTP not configured — reset link: {reset_url}")
        return

    subject = "⬡ OctaNova — Reset Your Password"
    html = f"""
    <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
                background:#0f0f13;color:#e2e8f0;padding:40px 0;min-height:100vh">
      <div style="max-width:520px;margin:0 auto;background:#1a1a2e;border-radius:16px;
                  overflow:hidden;border:1px solid #2d2d44">
        <div style="background:linear-gradient(135deg,#6366f1,#8b5cf6);padding:28px;text-align:center">
          <div style="font-size:1.8rem;margin-bottom:6px">⬡</div>
          <h1 style="margin:0;font-size:1.2rem;color:#fff;font-weight:700">OctaNova</h1>
        </div>
        <div style="padding:32px">
          <h2 style="margin:0 0 10px;font-size:1.2rem;color:#f1f5f9">Reset your password</h2>
          <p style="color:#94a3b8;margin:0 0 24px;font-size:.92rem;line-height:1.6">
            We received a request to reset your OctaNova password.
            Click the button below — this link expires in <strong style="color:#e2e8f0">1 hour</strong>.
          </p>
          <div style="text-align:center;margin-bottom:24px">
            <a href="{reset_url}"
               style="display:inline-block;background:linear-gradient(135deg,#6366f1,#8b5cf6);
                      color:#fff;text-decoration:none;padding:13px 32px;border-radius:8px;
                      font-weight:600;font-size:.95rem">
              Reset Password →
            </a>
          </div>
          <p style="color:#475569;font-size:.8rem;text-align:center">
            If you didn't request this, you can safely ignore this email.
          </p>
        </div>
        <div style="padding:16px 32px;border-top:1px solid #2d2d44;text-align:center">
          <p style="margin:0;font-size:.75rem;color:#475569">OctaNova Opportunity Engine</p>
        </div>
      </div>
    </div>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"OctaNova ⬡ <{FROM_EMAIL}>"
    msg["To"]      = to_email
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(FROM_EMAIL, to_email, msg.as_string())
        print(f"[mailer] Reset email sent to {to_email}")
    except Exception as e:
        print(f"[mailer] Failed to send reset email to {to_email}: {e}")
