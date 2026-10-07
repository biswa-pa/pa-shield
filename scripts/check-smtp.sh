#!/usr/bin/env python3
"""Check the Hostinger mailbox in smtp.env.

Connects with STARTTLS and logs in. Pass --send user@example.com to deliver
one test message. NetBird's management server does not call this script.
"""
import argparse
import smtplib
import ssl
import sys
from email.message import EmailMessage
from pathlib import Path


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--env",
        default="smtp.env",
        help="path to smtp.env (default: smtp.env)",
    )
    parser.add_argument(
        "--send",
        metavar="ADDRESS",
        help="send one test message to this address",
    )
    args = parser.parse_args()

    env_path = Path(args.env)
    if not env_path.is_file():
        print(f"Missing {env_path}. Copy smtp.env.example and set SMTP_PASSWORD.", file=sys.stderr)
        return 1

    cfg = load_env(env_path)
    host = cfg.get("SMTP_HOST", "")
    port = int(cfg.get("SMTP_PORT", "587"))
    user = cfg.get("SMTP_USER", "")
    password = cfg.get("SMTP_PASSWORD", "")
    sender = cfg.get("SMTP_FROM") or user
    if not host or not user or not password:
        print("smtp.env needs SMTP_HOST, SMTP_USER, and SMTP_PASSWORD.", file=sys.stderr)
        return 1

    print(f"Connecting to {host}:{port} as {user}")
    with smtplib.SMTP(host, port, timeout=30) as smtp:
        smtp.ehlo()
        smtp.starttls(context=ssl.create_default_context())
        smtp.ehlo()
        smtp.login(user, password)
        print("Login ok")
        if args.send:
            message = EmailMessage()
            message["From"] = sender
            message["To"] = args.send
            message["Subject"] = "Predicta NetBird SMTP test"
            message.set_content("Hostinger accepted this message from pa-netbird check-smtp.")
            smtp.send_message(message)
            print(f"Sent test message to {args.send}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
