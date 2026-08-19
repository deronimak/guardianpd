"""One-time bootstrap: create a PlatformStaffUser account.

There's no self-service signup for platform-ops accounts (these grant
access to school enrollment and billing across every tenant, so they're
provisioned deliberately, not via a signup form). Run this once per person
who needs access:

    python -m app.jobs.create_platform_staff --email you@example.com --name "Jane Ops"

You'll be prompted for a password (not passed as an argument, so it
doesn't end up in shell history).
"""

import argparse
import getpass

from app.db.platform import SessionLocal
from app.core.security import hash_password
from app.models.platform import PlatformStaffUser


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--role", default="ops", help="Free-text role label, e.g. admin/ops/support")
    args = parser.parse_args()

    password = getpass.getpass("Password: ")
    if len(password) < 8:
        raise SystemExit("Password must be at least 8 characters")
    if password != getpass.getpass("Confirm password: "):
        raise SystemExit("Passwords don't match")

    db = SessionLocal()
    try:
        if db.query(PlatformStaffUser).filter_by(email=args.email).first() is not None:
            raise SystemExit(f"{args.email} already has a platform staff account")

        staff = PlatformStaffUser(
            name=args.name,
            email=args.email,
            password_hash=hash_password(password),
            role=args.role,
        )
        db.add(staff)
        db.commit()
        print(f"Created platform staff account: {args.email} ({args.role})")
    finally:
        db.close()


if __name__ == "__main__":
    main()
