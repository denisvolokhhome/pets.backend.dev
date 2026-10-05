"""
Create load-test accounts and write loadtest/accounts.json.

    python loadtest/seed_users.py --host http://localhost:8001 --seekers 40 --breeders 10

Accounts are named loadtest.seeker.N@loadtest.breedly.dev / loadtest.breeder.N@... and all
use LOADTEST_PASSWORD (default LoadTest2026!). Re-running is safe: existing accounts are kept.
Only run against local / staging environments — never production.
"""
import argparse
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

PASSWORD = os.environ.get("LOADTEST_PASSWORD", "LoadTest2026!")


def post(host: str, path: str, body: dict, ip: str) -> int:
    req = urllib.request.Request(
        host + path,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "X-Forwarded-For": ip},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="http://localhost:8001")
    p.add_argument("--seekers", type=int, default=40)
    p.add_argument("--breeders", type=int, default=10)
    a = p.parse_args()

    accounts = {"seekers": [], "breeders": []}
    for i in range(a.seekers):
        email = f"loadtest.seeker.{i}@loadtest.breedly.dev"
        # Registration is rate-limited per client IP (3 / 10 min) — one simulated IP per account
        status = post(a.host, "/api/auth/register/pet-seeker",
                      {"email": email, "password": PASSWORD, "name": f"Load Seeker {i}"}, f"10.250.0.{i + 1}")
        if status in (200, 201, 400):  # 400 = already exists
            accounts["seekers"].append(email)
    for i in range(a.breeders):
        email = f"loadtest.breeder.{i}@loadtest.breedly.dev"
        status = post(a.host, "/api/auth/register",
                      {"email": email, "password": PASSWORD, "name": f"Load Breeder {i}"}, f"10.251.0.{i + 1}")
        if status in (200, 201, 400):
            accounts["breeders"].append(email)

    out = Path(__file__).with_name("accounts.json")
    out.write_text(json.dumps(accounts, indent=2))
    print(f"{len(accounts['seekers'])} seekers, {len(accounts['breeders'])} breeders -> {out}")


if __name__ == "__main__":
    main()
