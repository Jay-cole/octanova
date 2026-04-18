"""
Email notifications via Resend SDK (https://resend.com).

Set the following environment variable on Render:
  RESEND_API_KEY       — your Resend API key
  OCTANOVA_FROM_EMAIL  — sender (must be verified domain on Resend)
                         defaults to onboarding@resend.dev (test only)
  OCTANOVA_SITE_URL    — defaults to https://octanova.onrender.com
"""

import os
import threading


def _cfg():
    return {
        "api_key":    os.environ.get("RESEND_API_KEY", ""),
        "from_email": os.environ.get("OCTANOVA_FROM_EMAIL", "OctaNova <onboarding@resend.dev>"),
        "site_url":   os.environ.get("OCTANOVA_SITE_URL", "https://octanova.onrender.com"),
    }


def _send_via_resend(to_email, subject, html):
    cfg = _cfg()
    if not cfg["api_key"]:
        print(f"[mailer] RESEND_API_KEY not set — skipping email to {to_email}")
        return

    def _send():
        try:
            import resend
            resend.api_key = cfg["api_key"]
            print(f"[mailer] Using API key: {cfg['api_key'][:12]}...")
            resend.Emails.send({
                "from":    cfg["from_email"],
                "to":      [to_email],
                "subject": subject,
                "html":    html,
            })
            print(f"[mailer] ✓ Email sent to {to_email}")
        except Exception as e:
            print(f"[mailer] ✗ Failed to send to {to_email}: {type(e).__name__}: {e}")

    threading.Thread(target=_send, daemon=True).start()


def send_match_email(
    to_email, to_name, match_type,
    match_name, industry, offers, commitment, mode,
    matched_skills, matched_interests, matched_wants, score
):
    cfg = _cfg()
    print(f"[mailer] send_match_email → to={to_email} api_key_set={bool(cfg['api_key'])}")

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
    if matched_skills:    reasons.append(f"Matching skills: <strong>{matched_skills}</strong>")
    if matched_interests: reasons.append(f"Shared interest in: <strong>{matched_interests}</strong>")
    if matched_wants:     reasons.append(f"Aligned on: <strong>{matched_wants}</strong>")
    reasons_html = "".join(f"<li>{r}</li>" for r in reasons)

    site_url = cfg["site_url"]
    subject  = f"OctaNova — You have a new match! ({score}% compatibility)"
    html = f"""
    <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
                background:#0f0f13;color:#e2e8f0;padding:40px 0">
      <div style="max-width:560px;margin:0 auto;background:#1a1a2e;border-radius:16px;
                  overflow:hidden;border:1px solid #2d2d44">
        <div style="background:linear-gradient(135deg,#6366f1,#8b5cf6);padding:32px;text-align:center">
          <h1 style="margin:0;font-size:1.4rem;color:#fff;font-weight:700">OctaNova</h1>
          <p style="margin:6px 0 0;color:rgba(255,255,255,.8);font-size:.9rem">Opportunity Engine</p>
        </div>
        <div style="padding:32px">
          <h2 style="margin:0 0 6px;font-size:1.3rem;color:#f1f5f9">Hi {to_name}, you matched!</h2>
          <p style="color:#94a3b8;margin:0 0 24px;font-size:.95rem">
            You have a <strong style="color:#818cf8">{score}% compatibility</strong>
            match with a {entity_label.lower()}.
          </p>
          <div style="background:#0f0f1a;border:1px solid #2d2d44;border-radius:12px;
                      padding:20px;margin-bottom:24px">
            <p style="margin:0 0 4px;font-size:.75rem;color:#6366f1;text-transform:uppercase">{entity_label}</p>
            <h3 style="margin:0 0 16px;font-size:1.1rem;color:#f1f5f9">{match_name}</h3>
            <ul style="list-style:none;padding:0;margin:0;color:#94a3b8;font-size:.88rem">
              <li style="margin-bottom:6px"><strong style="color:#cbd5e1">{detail_label}:</strong> {industry}</li>
              <li style="margin-bottom:6px"><strong style="color:#cbd5e1">{offer_label}:</strong> {offers}</li>
              <li style="margin-bottom:6px"><strong style="color:#cbd5e1">{commit_label}:</strong> {commitment} hrs/week</li>
              {mode_line}
            </ul>
          </div>
          <div style="background:#1e1b4b;border-left:3px solid #6366f1;
                      border-radius:0 8px 8px 0;padding:16px;margin-bottom:24px">
            <p style="margin:0 0 10px;font-size:.85rem;font-weight:600;color:#a5b4fc">Why you matched:</p>
            <ul style="margin:0;padding-left:16px;color:#94a3b8;font-size:.85rem;line-height:1.7">
              {reasons_html}
            </ul>
          </div>
          <div style="text-align:center">
            <a href="{site_url}/matches"
               style="display:inline-block;background:linear-gradient(135deg,#6366f1,#8b5cf6);
                      color:#fff;text-decoration:none;padding:12px 32px;border-radius:8px;
                      font-weight:600;font-size:.95rem">
              View Your Match →
            </a>
          </div>
        </div>
        <div style="padding:20px 32px;border-top:1px solid #2d2d44;text-align:center">
          <p style="margin:0;font-size:.78rem;color:#475569">
            OctaNova Opportunity Engine · You registered on the platform.
          </p>
        </div>
      </div>
    </div>
    """
    _send_via_resend(to_email, subject, html)


def send_reset_email(to_email, reset_url):
    subject = "OctaNova — Reset Your Password"
    html = f"""
    <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
                background:#0f0f13;color:#e2e8f0;padding:40px 0">
      <div style="max-width:520px;margin:0 auto;background:#1a1a2e;border-radius:16px;
                  overflow:hidden;border:1px solid #2d2d44">
        <div style="background:linear-gradient(135deg,#6366f1,#8b5cf6);padding:28px;text-align:center">
          <h1 style="margin:0;font-size:1.2rem;color:#fff;font-weight:700">OctaNova</h1>
        </div>
        <div style="padding:32px">
          <h2 style="margin:0 0 10px;font-size:1.2rem;color:#f1f5f9">Reset your password</h2>
          <p style="color:#94a3b8;margin:0 0 24px;font-size:.92rem;line-height:1.6">
            Click the button below to reset your password.
            This link expires in <strong style="color:#e2e8f0">1 hour</strong>.
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
            If you didn't request this, ignore this email.
          </p>
        </div>
        <div style="padding:16px 32px;border-top:1px solid #2d2d44;text-align:center">
          <p style="margin:0;font-size:.75rem;color:#475569">OctaNova Opportunity Engine</p>
        </div>
      </div>
    </div>
    """
    _send_via_resend(to_email, subject, html)


def send_mutual_match_email(
    student_email, student_name,
    startup_email, startup_name,
    startup_contact_email, startup_whatsapp,
    student_contact_email, student_whatsapp
):
    """Send mutual match notification to both student and startup."""

    # Email to student
    student_html = f"""
    <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0a0a0a;color:#f1f5f9;padding:40px 0">
      <div style="max-width:520px;margin:0 auto;background:#111111;border-radius:12px;overflow:hidden;border:1px solid #2a2a2a">
        <div style="background:linear-gradient(135deg,#3B82F6,#8B5CF6);padding:28px;text-align:center">
          <h1 style="margin:0;font-size:1.2rem;color:#fff;font-weight:700">OctaNova</h1>
          <p style="margin:4px 0 0;color:rgba(255,255,255,.8);font-size:.85rem">Opportunity Engine</p>
        </div>
        <div style="padding:32px">
          <h2 style="margin:0 0 10px;font-size:1.1rem;color:#f1f5f9">You have a new match!</h2>
          <p style="color:#94a3b8;margin:0 0 20px;font-size:.92rem;line-height:1.6">
            Hi {student_name}, you and <strong style="color:#f1f5f9">{startup_name}</strong> have both accepted each other on OctaNova. It's a mutual match!
          </p>
          <div style="background:#1a1a1a;border:1px solid #2a2a2a;border-radius:8px;padding:16px;margin-bottom:20px">
            <p style="margin:0 0 8px;font-size:.75rem;color:#6b7280;text-transform:uppercase;letter-spacing:.08em">Their contact details</p>
            {f'<p style="margin:0 0 6px;font-size:.9rem;color:#f1f5f9">Email: <strong>{startup_contact_email}</strong></p>' if startup_contact_email else ''}
            {f'<p style="margin:0;font-size:.9rem;color:#f1f5f9">WhatsApp: <strong>{startup_whatsapp}</strong></p>' if startup_whatsapp else ''}
          </div>
          <p style="color:#94a3b8;font-size:.88rem;line-height:1.6">Reach out and introduce yourself — they're expecting to hear from you.</p>
        </div>
        <div style="padding:16px 32px;border-top:1px solid #2a2a2a;text-align:center">
          <p style="margin:0;font-size:.75rem;color:#6b7280">OctaNova Opportunity Engine</p>
        </div>
      </div>
    </div>
    """

    # Email to startup
    startup_html = f"""
    <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0a0a0a;color:#f1f5f9;padding:40px 0">
      <div style="max-width:520px;margin:0 auto;background:#111111;border-radius:12px;overflow:hidden;border:1px solid #2a2a2a">
        <div style="background:linear-gradient(135deg,#3B82F6,#8B5CF6);padding:28px;text-align:center">
          <h1 style="margin:0;font-size:1.2rem;color:#fff;font-weight:700">OctaNova</h1>
          <p style="margin:4px 0 0;color:rgba(255,255,255,.8);font-size:.85rem">Opportunity Engine</p>
        </div>
        <div style="padding:32px">
          <h2 style="margin:0 0 10px;font-size:1.1rem;color:#f1f5f9">A student matched with you!</h2>
          <p style="color:#94a3b8;margin:0 0 20px;font-size:.92rem;line-height:1.6">
            Hi {startup_name}, you and <strong style="color:#f1f5f9">{student_name}</strong> have both accepted each other on OctaNova. It's a mutual match!
          </p>
          <div style="background:#1a1a1a;border:1px solid #2a2a2a;border-radius:8px;padding:16px;margin-bottom:20px">
            <p style="margin:0 0 8px;font-size:.75rem;color:#6b7280;text-transform:uppercase;letter-spacing:.08em">Their contact details</p>
            {f'<p style="margin:0 0 6px;font-size:.9rem;color:#f1f5f9">Email: <strong>{student_contact_email}</strong></p>' if student_contact_email else ''}
            {f'<p style="margin:0;font-size:.9rem;color:#f1f5f9">WhatsApp: <strong>{student_whatsapp}</strong></p>' if student_whatsapp else ''}
          </div>
          <p style="color:#94a3b8;font-size:.88rem;line-height:1.6">This student is interested in working with you — expect a message from them soon.</p>
        </div>
        <div style="padding:16px 32px;border-top:1px solid #2a2a2a;text-align:center">
          <p style="margin:0;font-size:.75rem;color:#6b7280">OctaNova Opportunity Engine</p>
        </div>
      </div>
    </div>
    """

    _send_via_resend(student_email, "You have a new match on Octanova!", student_html)
    _send_via_resend(startup_email, "A student matched with you on Octanova!", startup_html)
