"""Local administrative commands for application authentication."""

from __future__ import annotations

import argparse
import sys
from getpass import getpass
from typing import Sequence

from pydantic import ValidationError

from . import crud, schemas
from .auth import (
    create_password_reset_token,
    password_reset_token_minutes,
)
from .database import SessionLocal
from .security import validate_password


def _read_new_password() -> str:
    password = getpass("New password: ")
    confirmation = getpass("Confirm new password: ")
    if password != confirmation:
        raise ValueError("Passwords do not match.")
    return validate_password(password)


def _create_admin(username: str) -> int:
    username = username.strip()
    try:
        request = schemas.FirstAdminCreate(
            username=username,
            password=_read_new_password(),
        )
    except (ValidationError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    with SessionLocal() as db:
        try:
            user = crud.create_first_admin(db, request)
        except crud.FirstAdminAlreadyExistsError as error:
            print(f"ERROR: {error}", file=sys.stderr)
            return 3

    print(
        "First administrator created successfully: "
        f"{user.username}"
    )
    return 0


def _issue_reset_token(username: str) -> int:
    username = username.strip()
    with SessionLocal() as db:
        user = crud.get_user_by_username(db, username)
        if user is None or not user.is_active:
            print(
                "ERROR: Active user account was not found.",
                file=sys.stderr,
            )
            return 4
        try:
            token = create_password_reset_token(
                username=user.username,
                password_hash=user.password_hash,
            )
            lifetime = password_reset_token_minutes()
        except RuntimeError as error:
            print(f"ERROR: {error}", file=sys.stderr)
            return 5

    print(
        f"Password-reset token for {username} "
        f"(valid for {lifetime} minutes):"
    )
    print(token)
    print(
        "Keep this token private. It becomes invalid after the "
        "password changes or the token expires."
    )
    return 0


def _reset_password(username: str) -> int:
    username = username.strip()
    try:
        password = _read_new_password()
    except ValueError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    with SessionLocal() as db:
        user = crud.get_user_by_username(db, username)
        if user is None:
            print(
                "ERROR: User account was not found.",
                file=sys.stderr,
            )
            return 4
        crud.update_user_password(db, user, password)

    print(f"Password updated successfully: {username}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Manage Telecom Forensics application authentication "
            "from the backend host."
        )
    )
    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    create_admin = subparsers.add_parser(
        "create-admin",
        help="Create the first administrator if no users exist.",
    )
    create_admin.add_argument("username")

    reset_token = subparsers.add_parser(
        "reset-token",
        help="Issue a short-lived GUI password-reset token.",
    )
    reset_token.add_argument("username")

    reset_password = subparsers.add_parser(
        "reset-password",
        help="Reset a password directly from the backend host.",
    )
    reset_password.add_argument("username")
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(arguments)

    if args.command == "create-admin":
        return _create_admin(args.username)
    if args.command == "reset-token":
        return _issue_reset_token(args.username)
    if args.command == "reset-password":
        return _reset_password(args.username)

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
