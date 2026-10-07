"""Password reset by email for the NetBird embedded login.

NetBird 0.74.4 cannot send mail and its API only lets users change their own
password with the old one. This service fills the gap: it emails a signed,
single-use link and then writes the new bcrypt hash into the login database
(idp.db), which the server reads on every sign-in.

Config comes from environment variables (see smtp.env.example).
"""
import base64
import hashlib
import hmac
import html
import json
import os
import secrets
import smtplib
from datetime import datetime
import sqlite3
import ssl
import time
import urllib.error
import urllib.request
from email.message import EmailMessage
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlencode, urlparse

import bcrypt

DB_PATH = os.environ.get("IDP_DB", "/data/idp.db")
PUBLIC_URL = os.environ.get("PUBLIC_URL", "http://localhost:8088").rstrip("/")
BRAND = os.environ.get("PA_BRAND_NAME", "PA Shield")
TTL = int(os.environ.get("RESET_TTL_MINUTES", "30")) * 60
SECRET = (os.environ.get("RESET_SECRET") or secrets.token_hex(32)).encode()
RESEND_AFTER = 60
LOGO_CID = "pa-netbird-logo"
try:
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "email-banner.png"), "rb") as fh:
        LOGO_PNG = fh.read()
except OSError:
    LOGO_PNG = b""

NETBIRD_API = os.environ.get("NETBIRD_API", "http://netbird-server:80").rstrip("/")
SETTINGS_PATH = os.environ.get("SETTINGS_PATH", "/config/email-settings.json")

# Defaults come from the environment (smtp.env). Anything saved from the
# dashboard (Settings > Email Provider) overrides them.
ENV_SMTP = {
    "host": os.environ.get("SMTP_HOST", ""),
    "port": int(os.environ.get("SMTP_PORT", "587")),
    "user": os.environ.get("SMTP_USER", ""),
    "password": os.environ.get("SMTP_PASSWORD", ""),
    "from": os.environ.get("SMTP_FROM") or os.environ.get("SMTP_USER", ""),
    "security": os.environ.get("SMTP_SECURITY", "starttls").lower(),  # starttls | ssl | none
}


def load_settings():
    settings = {
        "provider": "smtp" if ENV_SMTP["host"] else "none",
        "smtp": dict(ENV_SMTP),
        "graph": {"tenant_id": "", "client_id": "", "client_secret": "", "sender": ""},
    }
    try:
        with open(SETTINGS_PATH) as fh:
            saved = json.load(fh)
        settings["provider"] = saved.get("provider", settings["provider"])
        settings["smtp"].update(saved.get("smtp", {}))
        settings["graph"].update(saved.get("graph", {}))
    except (OSError, ValueError):
        pass
    return settings


def save_settings(settings):
    os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
    tmp = SETTINGS_PATH + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        json.dump(settings, fh)
    os.replace(tmp, SETTINGS_PATH)


def mail_ready(settings=None):
    settings = settings or load_settings()
    if settings["provider"] == "graph":
        g = settings["graph"]
        return all(g.get(k) for k in ("tenant_id", "client_id", "client_secret", "sender"))
    if settings["provider"] == "smtp":
        return bool(settings["smtp"]["host"] and settings["smtp"]["from"])
    return False


def public_settings(settings):
    """Settings for the dashboard: secrets are replaced by a 'saved' flag."""
    smtp = {k: v for k, v in settings["smtp"].items() if k != "password"}
    smtp["password_set"] = bool(settings["smtp"].get("password"))
    graph = {k: v for k, v in settings["graph"].items() if k != "client_secret"}
    graph["client_secret_set"] = bool(settings["graph"].get("client_secret"))
    return {"provider": settings["provider"], "smtp": smtp, "graph": graph}


_last_sent: dict[str, float] = {}

CSS = """
*{box-sizing:border-box}html,body{margin:0;min-height:100vh;font-family:ui-sans-serif,system-ui,sans-serif;font-size:14px;color:#1f2937;background:#fff}
body::before{content:"";position:fixed;left:0;top:0;bottom:0;width:50%;background:linear-gradient(to top,rgba(26,10,34,.85),rgba(26,10,34,.15) 50%,rgba(26,10,34,.5)),url(/oauth2/theme/login-bg.png) center/cover,#1a0a22}
.logo{position:fixed;left:40px;top:40px;width:200px;height:40px;z-index:2;background:url(/oauth2/theme/logo.png) left center/contain no-repeat}
.tag{position:fixed;left:40px;top:86px;z-index:2;white-space:nowrap;color:#fd9904;font-size:11px;font-weight:600;letter-spacing:.18em}
.promo{position:fixed;left:40px;bottom:40px;width:calc(50% - 80px);max-width:448px;z-index:2;color:#fff}
.promo h2{margin:0 0 8px;font-size:30px;line-height:36px;font-weight:700;letter-spacing:-.025em;color:#fff}
.promo p{margin:0;font-size:18px;line-height:28px;color:rgba(255,255,255,.9)}
main{margin-left:50%;width:50%;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:40px}
.card{width:100%;max-width:480px}
h1{font-size:32px;font-weight:600;color:#2d3a52;margin:0 0 8px}
p.sub{color:#6b7280;margin:0 0 24px}
label{display:block;font-size:15px;color:#374151;margin:16px 0 6px}
input{width:100%;height:48px;padding:0 14px;border:1px solid #6b7a90;border-radius:8px;background:#f9fafb;font-size:14px;outline:none}
input:focus{border-color:#fd9904;background:#fff;box-shadow:0 0 0 3px rgba(253,153,4,.2)}
button,a.btn{display:flex;align-items:center;justify-content:center;width:100%;height:48px;margin-top:24px;border:0;border-radius:8px;background:#fd9904;color:#fff;font-size:15px;font-weight:500;cursor:pointer;text-decoration:none}
button:hover,a.btn:hover{background:#481057}
.msg{padding:12px 14px;border-radius:8px;font-size:14px;line-height:1.5;margin-bottom:8px}
.ok{background:#ecfdf3;border:1px solid #abefc6;color:#05603a}
.err{background:#fef3f2;border:1px solid #fecdca;color:#b42318}
.dev{background:#fff7e8;border:1px solid #fde1ae;color:#4b3a1a}
.back{display:block;margin-top:20px;text-align:center;color:#fd9904;text-decoration:none;font-weight:500}
@media(max-width:1279px){body::before,.tag,.promo{display:none}.logo{position:static;width:200px;height:40px;margin:32px auto 0}main{margin:0;width:100%;min-height:auto;padding:24px}}
"""


def page(title, body):
    if title == "Not found":
        promo_title, promo_text = "Welcome Back", "Securely connect your devices, servers and teams on one private network."
    else:
        promo_title, promo_text = "Reset Your Password", "We'll help you get back into your account."
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)} - {html.escape(BRAND)}</title>
<link rel="icon" href="/oauth2/theme/favicon.ico"><style>{CSS}</style></head><body>
<div class="logo"></div><div class="tag">SECURE PRIVATE NETWORKING, ONE PEER AT A TIME</div><div class="promo"><h2>{promo_title}</h2><p>{promo_text}</p></div>
<main><div class="card">{body}</div></main></body></html>""".encode()


def forgot_form(notice=""):
    return page("Forgot password", f"""<h1>Forgot password?</h1>
<p class="sub">Enter your account email and we will send you a link to set a new password.</p>{notice}
<form method="post" action="/reset/forgot"><label for="email">Email address</label>
<input id="email" name="email" type="email" required autofocus placeholder="Enter your email address">
<button type="submit">Send reset link</button></form><a class="back" href="/">Back to sign in</a>""")


def db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA busy_timeout=10000")
    return conn


def lookup(email):
    with db() as conn:
        return conn.execute("SELECT email, hash FROM password WHERE lower(email)=lower(?)", (email,)).fetchone()


def display_name(email):
    try:
        with db() as conn:
            row = conn.execute("SELECT name, username FROM password WHERE lower(email)=lower(?)", (email,)).fetchone()
        return ((row[0] or row[1]) if row else "") or ""
    except Exception:
        return ""


def fingerprint(hash_value):
    raw = hash_value if isinstance(hash_value, bytes) else str(hash_value).encode()
    return hashlib.sha256(raw).hexdigest()[:16]


def sign(payload):
    mac = hmac.new(SECRET, payload.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{payload}|{mac}".encode()).decode()


def make_token(email, hash_value):
    return sign(f"{email}|{int(time.time()) + TTL}|{fingerprint(hash_value)}")


def read_token(token):
    """Return the email if the token is valid, unexpired and not yet used."""
    try:
        email, exp, fp, mac = base64.urlsafe_b64decode(token.encode()).decode().rsplit("|", 3)
    except Exception:
        return None
    good = hmac.new(SECRET, f"{email}|{exp}|{fp}".encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(mac, good) or int(exp) < time.time():
        return None
    row = lookup(email)
    # The fingerprint is the current hash, so a used link stops working.
    if not row or fingerprint(row[1]) != fp:
        return None
    return row[0]


def deliver(to, subject, text, html_body, settings=None):
    """Send one message with the configured provider. Raises on failure.

    The banner is attached inline (cid:pa-netbird-logo): mail clients block
    SVG, data: and localhost images, but they show inline attachments.
    """
    settings = settings or load_settings()
    if settings["provider"] == "graph":
        return send_graph(settings["graph"], to, subject, html_body)
    if settings["provider"] == "smtp":
        return send_smtp(settings["smtp"], to, subject, text, html_body)
    raise RuntimeError("no email provider is configured")


def send_smtp(cfg, to, subject, text, html_body):
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg["from"]
    msg["To"] = to
    msg.set_content(text)
    msg.add_alternative(html_body, subtype="html")
    if LOGO_PNG and f"cid:{LOGO_CID}" in html_body:
        msg.get_payload()[1].add_related(LOGO_PNG, "image", "png", cid=f"<{LOGO_CID}>", filename="logo.png")
    ctx = ssl.create_default_context()
    port = int(cfg.get("port") or 587)
    if cfg.get("security") == "ssl":
        server = smtplib.SMTP_SSL(cfg["host"], port, context=ctx, timeout=20)
    else:
        server = smtplib.SMTP(cfg["host"], port, timeout=20)
        if cfg.get("security", "starttls") == "starttls":
            server.starttls(context=ctx)
    with server:
        if cfg.get("user") and cfg.get("password"):
            server.login(cfg["user"], cfg["password"])
        server.send_message(msg)


def http_json(url, data=None, headers=None, method=None):
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        try:
            err = json.loads(detail)
            detail = err.get("error_description") or (err.get("error") or {}).get("message") or detail
        except ValueError:
            pass
        raise RuntimeError(f"{exc.code}: {str(detail)[:300]}") from None
    return json.loads(raw) if raw else {}


def send_graph(cfg, to, subject, html_body):
    """Microsoft Graph sendMail with app-only (client credentials) auth.

    The Entra app needs the Mail.Send application permission with admin
    consent. `sender` is the mailbox the message is sent from.
    """
    token = http_json(
        f"https://login.microsoftonline.com/{quote(cfg['tenant_id'])}/oauth2/v2.0/token",
        data=urlencode({
            "client_id": cfg["client_id"],
            "client_secret": cfg["client_secret"],
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials",
        }).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )["access_token"]
    message = {
        "subject": subject,
        "body": {"contentType": "HTML", "content": html_body},
        "toRecipients": [{"emailAddress": {"address": to}}],
    }
    if LOGO_PNG and f"cid:{LOGO_CID}" in html_body:
        message["attachments"] = [{
            "@odata.type": "#microsoft.graph.fileAttachment",
            "name": "logo.png",
            "contentType": "image/png",
            "contentBytes": base64.b64encode(LOGO_PNG).decode(),
            "isInline": True,
            "contentId": LOGO_CID,
        }]
    payload = {"message": message, "saveToSentItems": False}
    http_json(
        f"https://graph.microsoft.com/v1.0/users/{quote(cfg['sender'])}/sendMail",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )


def email_shell(heading, inner_html, preheader=""):
    """Shared layout: banner, orange rule, content card, footer. Table based
    with inline styles so it holds up in Gmail and Outlook."""
    e = html.escape
    return f"""<!doctype html><html><body style="margin:0;padding:0;background:#f4f1f7;">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;color:#f4f1f7;">{e(preheader)}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f1f7;padding:28px 12px;">
<tr><td align="center">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="width:100%;max-width:600px;background:#ffffff;border-radius:14px;overflow:hidden;border:1px solid #e6e0ee;font-family:Segoe UI,Helvetica,Arial,sans-serif;color:#1f2937;">
<tr><td style="background:#1a0a22;line-height:0;font-size:0;"><img src="cid:{LOGO_CID}" width="600" alt="{e(BRAND)}" style="display:block;width:100%;max-width:600px;height:auto;border:0;"></td></tr>
<tr><td style="height:4px;background:#fd9904;line-height:4px;font-size:4px;">&nbsp;</td></tr>
<tr><td style="padding:36px 40px 12px 40px;">
<h1 style="margin:0 0 16px 0;font-size:24px;line-height:1.3;font-weight:600;color:#2d1b3d;">{e(heading)}</h1>
{inner_html}
</td></tr>
<tr><td style="padding:8px 40px 32px 40px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-top:1px solid #eee8f3;"><tr><td style="padding-top:18px;font-size:12px;line-height:1.6;color:#8b8296;">
{e(BRAND)} &middot; Secure private networking<br>This is an automated message, please do not reply.</td></tr></table>
</td></tr></table></td></tr></table></body></html>"""


def send_reset_mail(to, link, name=""):
    minutes = TTL // 60
    e = html.escape
    who = name or to
    subject = f"Reset your {BRAND} password"
    text = (
        f"Hi {who},\n\n"
        f"We received a request to reset the password for your {BRAND} account ({to}).\n\n"
        f"Set a new password: {link}\n\n"
        f"The link works once and expires in {minutes} minutes. "
        "If you did not ask for this, you can ignore this email and your password will stay the same.\n"
    )
    inner = f"""<p style="margin:0 0 14px 0;font-size:15px;line-height:1.6;">Hi {e(who)},</p>
<p style="margin:0 0 24px 0;font-size:15px;line-height:1.6;">We received a request to reset the password for your {e(BRAND)} account (<b style="color:#2d1b3d;">{e(to)}</b>). Click the button below to choose a new one.</p>
<table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 0 26px 0;"><tr><td bgcolor="#fd9904" style="border-radius:8px;">
<a href="{e(link)}" target="_blank" style="display:inline-block;padding:14px 32px;font-size:16px;font-weight:600;color:#ffffff;text-decoration:none;border-radius:8px;background:#fd9904;">Set a new password</a></td></tr></table>
<p style="margin:0 0 6px 0;font-size:13px;line-height:1.6;color:#6b7280;">This link works once and expires in <b>{minutes} minutes</b>.</p>
<p style="margin:0 0 22px 0;font-size:13px;line-height:1.6;color:#6b7280;">If you did not ask for this, you can safely ignore this email. Your password will not change.</p>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#faf7fd;border:1px solid #eee8f3;border-radius:8px;"><tr><td style="padding:14px 16px;font-size:12px;line-height:1.6;color:#6b7280;">
Button not working? Copy this link into your browser:<br><a href="{e(link)}" style="color:#b86e00;word-break:break-all;">{e(link)}</a></td></tr></table>"""
    deliver(to, subject, text, email_shell("Reset your password", inner, f"Use this link within {minutes} minutes to set a new password."))


def pretty_date(iso):
    try:
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).strftime("%d %b %Y")
    except ValueError:
        return ""


def send_invite_mail(to, name, inviter, link, expires_at, role):
    e = html.escape
    until = pretty_date(expires_at)
    by = f"{inviter} has" if inviter else "You have"
    expiry_line = f"This invitation expires on {until}." if until else "This invitation expires soon."
    subject = f"You're invited to {BRAND}"
    text = (
        f"Hi {name or to},\n\n{by} invited you to join {BRAND}"
        f"{' as ' + role if role else ''}.\n\nAccept the invitation and choose your password: {link}\n\n"
        f"{expiry_line} If you were not expecting this, you can ignore this email.\n"
    )
    inner = f"""<p style="margin:0 0 14px 0;font-size:15px;line-height:1.6;">Hi {e(name or to)},</p>
<p style="margin:0 0 24px 0;font-size:15px;line-height:1.6;"><b style="color:#2d1b3d;">{e(inviter) if inviter else "An administrator"}</b> has invited you to join <b style="color:#2d1b3d;">{e(BRAND)}</b>{(' as <b>' + e(role) + '</b>') if role else ''}. Accept the invitation and choose your own password to get started.</p>
<table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 0 26px 0;"><tr><td bgcolor="#fd9904" style="border-radius:8px;">
<a href="{e(link)}" target="_blank" style="display:inline-block;padding:14px 32px;font-size:16px;font-weight:600;color:#ffffff;text-decoration:none;border-radius:8px;background:#fd9904;">Accept invitation</a></td></tr></table>
<p style="margin:0 0 22px 0;font-size:13px;line-height:1.6;color:#6b7280;">{e(expiry_line)} If you were not expecting this, you can safely ignore this email.</p>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#faf7fd;border:1px solid #eee8f3;border-radius:8px;"><tr><td style="padding:14px 16px;font-size:12px;line-height:1.6;color:#6b7280;">
Button not working? Copy this link into your browser:<br><a href="{e(link)}" style="color:#b86e00;word-break:break-all;">{e(link)}</a></td></tr></table>"""
    deliver(to, subject, text, email_shell("You're invited", inner, f"{by} invited you to join {BRAND}."))


def send_test_mail(to, settings, name=""):
    e = html.escape
    inner = f"""<p style="margin:0 0 14px 0;font-size:15px;line-height:1.6;">Hi {e(name or to)},</p>
<p style="margin:0 0 20px 0;font-size:15px;line-height:1.6;">This is a test message from <b>{e(BRAND)}</b>. If you can read it, your email provider is set up correctly and password reset emails will be delivered.</p>
<table role="presentation" cellpadding="0" cellspacing="0"><tr><td style="background:#ecfdf3;border:1px solid #abefc6;border-radius:8px;padding:12px 16px;font-size:14px;color:#05603a;">&#10003; Email delivery works</td></tr></table>"""
    deliver(to, f"{BRAND} test email", f"This is a test message from {BRAND}. Email delivery works.",
            email_shell("Email delivery works", inner, "Your email provider is set up correctly."), settings)


def request_reset(email):
    email = email.strip()
    now = time.time()
    if now - _last_sent.get(email.lower(), 0) < RESEND_AFTER:
        return
    row = lookup(email)
    if not row:
        return
    _last_sent[email.lower()] = now
    link = f"{PUBLIC_URL}/reset/new?token={quote(make_token(row[0], row[1]))}"
    if not mail_ready():
        print(f"[reset] No email provider configured. Reset link for {row[0]}: {link}", flush=True)
        return
    try:
        send_reset_mail(row[0], link, display_name(row[0]))
        print(f"[reset] email sent to {row[0]}", flush=True)
    except Exception as exc:  # never reveal delivery problems to the requester
        print(f"[reset] could not send to {row[0]}: {exc}", flush=True)


def set_password(email, password):
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=10, prefix=b"2a"))
    with db() as conn:
        conn.execute("UPDATE password SET hash=? WHERE lower(email)=lower(?)", (hashed, email))


def current_admin(auth_header):
    """Return the signed-in NetBird user if they are an owner or admin."""
    if not auth_header.lower().startswith("bearer ") or len(auth_header) < 20:
        print("[reset] settings API: no bearer token on the request", flush=True)
        return None
    try:
        user = http_json(f"{NETBIRD_API}/api/users/current", headers={"Authorization": auth_header})
    except Exception as exc:
        print(f"[reset] settings API: NetBird rejected the token: {exc}", flush=True)
        return None
    if user.get("role") not in ("owner", "admin"):
        print(f"[reset] settings API: user {user.get('email')} has role {user.get('role')}", flush=True)
        return None
    return user


def merge_settings(current, incoming):
    """Apply a dashboard save. Empty secrets keep the stored value."""
    out = {"provider": current["provider"], "smtp": dict(current["smtp"]), "graph": dict(current["graph"])}
    provider = incoming.get("provider")
    if provider in ("none", "smtp", "graph"):
        out["provider"] = provider
    for section, keys, secret in (
        ("smtp", ("host", "port", "security", "user", "from"), "password"),
        ("graph", ("tenant_id", "client_id", "sender"), "client_secret"),
    ):
        inc = incoming.get(section) or {}
        for key in keys:
            if key in inc:
                out[section][key] = str(inc[key]).strip()
        if inc.get(secret):
            out[section][secret] = str(inc[secret])
    return out


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def send(self, body, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)

    def json_reply(self, payload, status=200):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def api(self, method):
        path = urlparse(self.path).path
        admin = current_admin(self.headers.get("Authorization", ""))
        if not admin:
            return self.json_reply({"error": "Only owners and admins can manage email settings."}, 403)
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(min(length, 16384)) or b"{}")
        except ValueError:
            return self.json_reply({"error": "Invalid JSON."}, 400)
        current = load_settings()
        if path == "/reset/api/email-settings" and method == "GET":
            return self.json_reply(public_settings(current))
        if path == "/reset/api/email-settings" and method == "PUT":
            merged = merge_settings(current, body)
            if merged["provider"] == "graph" and not mail_ready(merged):
                return self.json_reply({"error": "Fill in tenant ID, client ID, client secret and sender mailbox."}, 400)
            if merged["provider"] == "smtp" and not mail_ready(merged):
                return self.json_reply({"error": "Fill in the SMTP host and from address."}, 400)
            save_settings(merged)
            print(f"[reset] email provider set to {merged['provider']} by {admin.get('email')}", flush=True)
            return self.json_reply(public_settings(merged))
        if path == "/reset/api/email-settings/test" and method == "POST":
            target = admin.get("email") or ""
            # Test what is on screen, not only what is saved.
            settings = merge_settings(current, body) if body else current
            if not mail_ready(settings):
                return self.json_reply({"error": "Email provider is not fully configured."}, 400)
            if not target:
                return self.json_reply({"error": "Your account has no email address to send the test to."}, 400)
            try:
                send_test_mail(target, settings, admin.get("name") or "")
            except Exception as exc:
                return self.json_reply({"error": f"Could not send: {exc}"}, 502)
            return self.json_reply({"ok": True, "sent_to": target})
        if path == "/reset/api/send-invite" and method == "POST":
            # The recipient comes from NetBird's own invite record, not from the
            # request, so this cannot be used to mail arbitrary addresses.
            if not mail_ready(current):
                return self.json_reply({"error": "Email provider is not configured."}, 409)
            invite_id = str(body.get("invite_id") or "")
            token = str(body.get("invite_token") or "")
            if not invite_id or not token.startswith("nbi_"):
                return self.json_reply({"error": "Missing invite."}, 400)
            try:
                invites = http_json(f"{NETBIRD_API}/api/users/invites",
                                    headers={"Authorization": self.headers.get("Authorization", "")})
            except Exception as exc:
                return self.json_reply({"error": f"Could not read the invite: {exc}"}, 502)
            invite = next((i for i in invites if i.get("id") == invite_id), None)
            if not invite or not invite.get("email"):
                return self.json_reply({"error": "Invite not found."}, 404)
            link = f"{PUBLIC_URL}/invite?token={quote(token)}"
            try:
                send_invite_mail(invite["email"], invite.get("name") or "", admin.get("name") or admin.get("email") or "",
                                 link, body.get("expires_at") or invite.get("expires_at"), invite.get("role") or "")
            except Exception as exc:
                print(f"[reset] invite email to {invite['email']} failed: {exc}", flush=True)
                return self.json_reply({"error": f"Could not send: {exc}"}, 502)
            print(f"[reset] invite email sent to {invite['email']} by {admin.get('email')}", flush=True)
            return self.json_reply({"ok": True, "sent_to": invite["email"]})
        self.json_reply({"error": "Not found."}, 404)

    def do_PUT(self):
        if urlparse(self.path).path.startswith("/reset/api/"):
            return self.api("PUT")
        self.send(page("Not found", "<h1>Not found</h1>"), 404)

    def form(self):
        length = int(self.headers.get("Content-Length") or 0)
        return {k: v[0] for k, v in parse_qs(self.rfile.read(min(length, 4096)).decode()).items()}

    def new_form(self, token, notice=""):
        return page("New password", f"""<h1>Set a new password</h1>
<p class="sub">Choose a password of at least 8 characters.</p>{notice}
<form method="post" action="/reset/new"><input type="hidden" name="token" value="{html.escape(token)}">
<label for="p1">New password</label><input id="p1" name="password" type="password" minlength="8" required autofocus>
<label for="p2">Confirm password</label><input id="p2" name="confirm" type="password" minlength="8" required>
<button type="submit">Save password</button></form>""")

    def invalid(self):
        self.send(page("Link expired", """<h1>Link expired</h1>
<div class="msg err">This reset link is invalid, has expired or was already used.</div>
<a class="btn" href="/reset/forgot">Request a new link</a>"""), 400)

    def do_GET(self):
        url = urlparse(self.path)
        if url.path.startswith("/reset/api/"):
            return self.api("GET")
        if url.path in ("/reset/forgot", "/reset", "/reset/"):
            return self.send(forgot_form())
        if url.path == "/reset/new":
            token = parse_qs(url.query).get("token", [""])[0]
            return self.send(self.new_form(token)) if read_token(token) else self.invalid()
        if url.path == "/reset/health":
            return self.send(b"ok")
        self.send(page("Not found", '<h1>Not found</h1><a class="back" href="/">Back to sign in</a>'), 404)

    def do_POST(self):
        path = urlparse(self.path).path
        if path.startswith("/reset/api/"):
            return self.api("POST")
        data = self.form()
        if path == "/reset/forgot":
            request_reset(data.get("email", ""))
            # Same answer whether or not the account exists.
            note = '<div class="msg ok">If an account exists for that email, a reset link is on its way.</div>'
            if not mail_ready():
                note += '<div class="msg dev">No email provider is configured on this server, so the link was written to the reset service log.</div>'
            return self.send(forgot_form(note))
        if path == "/reset/new":
            token = data.get("token", "")
            email = read_token(token)
            if not email:
                return self.invalid()
            password = data.get("password", "")
            if len(password) < 8:
                return self.send(self.new_form(token, '<div class="msg err">Password must be at least 8 characters.</div>'), 400)
            if password != data.get("confirm"):
                return self.send(self.new_form(token, '<div class="msg err">The two passwords do not match.</div>'), 400)
            set_password(email, password)
            print(f"[reset] password changed for {email}", flush=True)
            return self.send(page("Password updated", """<h1>Password updated</h1>
<div class="msg ok">You can now sign in with your new password.</div><a class="btn" href="/">Sign in</a>"""))
        self.send(page("Not found", "<h1>Not found</h1>"), 404)


if __name__ == "__main__":
    print(f"[reset] listening on :8000, email={load_settings()['provider']}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
