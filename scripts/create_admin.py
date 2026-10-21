"""Create an admin user, or promote an existing one. A one-off command, run by a person.

Run from the repo root, with the project's virtualenv (on Windows: .venv/Scripts/python.exe):
  python scripts/create_admin.py --email you@example.com --name "Full Name" --role super_admin

Scope:
  faculty_admin     needs --faculty-id (a live faculty)
  department_admin  needs --department-id (a live department). Its school is looked up.
  super_admin, sug  take no scope

Flags:
  --dry-run   show the plan and check the database read-only. Writes nothing. No password prompt.
  --promote   if the email already belongs to a user, change that user's role and scope.
              Never changes the password, is_active, or any other column.

Safety:
  - DATABASE_URL comes from the environment or .env, as in db/import_seed.py. Use the direct
    (non-pooled) host: a pooled host is refused.
  - The password is typed twice at a prompt. It is never an argument, never read from a file,
    never printed. It is hashed with app.security.hash_password, the same function the API uses.
  - Before any write, the masked host, action, email and role are printed, and you must type yes.
  - One transaction. On success only the user id and role are printed.
"""

import argparse
import getpass
import pathlib
import sys
import uuid
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))
sys.path.insert(0, str(ROOT / "db"))

# The imports below need the paths above, so they cannot come first.
# ruff: noqa: E402
import psycopg
from import_seed import database_url  # same DATABASE_URL handling as db/import_seed.py
from psycopg.rows import dict_row
from pydantic import ValidationError

from app.routers.auth import RegisterRequest  # the same rules the API enforces
from app.security import hash_password

ROLES = ("super_admin", "sug", "faculty_admin", "department_admin")
POOLER_MARKER = "-pooler"
MASK_HEAD = 8
MASK_TAIL = 14

FIND_USER = """
    SELECT id, role, faculty_id, department_id, is_active
    FROM users
    WHERE lower(email) = %(email)s
    LIMIT 1
    """
LIVE_FACULTY = "SELECT 1 FROM faculties WHERE id = %(id)s AND deleted_at IS NULL"
LIVE_DEPARTMENT = "SELECT faculty_id FROM departments WHERE id = %(id)s AND deleted_at IS NULL"
INSERT_USER = """
    INSERT INTO users (full_name, email, password_hash, role, faculty_id, department_id)
    VALUES (%(full_name)s, %(email)s, %(password_hash)s, %(role)s, %(faculty_id)s,
            %(department_id)s)
    RETURNING id, role
    """
UPDATE_ROLE_AND_SCOPE = """
    UPDATE users
    SET role = %(role)s, faculty_id = %(faculty_id)s, department_id = %(department_id)s
    WHERE id = %(id)s
    RETURNING id, role
    """


# ----------------------------------------------------------------- pure logic (tested)


@dataclass(frozen=True)
class Scope:
    faculty_id: uuid.UUID | None
    department_id: uuid.UUID | None


def parse_uuid(value: str | None) -> uuid.UUID | None:
    if value is None:
        return None
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


def plan_scope(
    role: str, faculty_id: str | None, department_id: str | None
) -> tuple[Scope | None, list[str]]:
    """The scope a role needs, and what is wrong with the scope flags given for it."""
    problems = []
    if role not in ROLES:
        return None, [f"role must be one of: {', '.join(ROLES)}"]

    faculty = parse_uuid(faculty_id)
    department = parse_uuid(department_id)
    if faculty_id is not None and faculty is None:
        problems.append("--faculty-id is not a valid id")
    if department_id is not None and department is None:
        problems.append("--department-id is not a valid id")

    if role == "faculty_admin":
        if faculty_id is None:
            problems.append("faculty_admin needs --faculty-id")
        if department_id is not None:
            problems.append("faculty_admin takes --faculty-id, not --department-id")
    elif role == "department_admin":
        if department_id is None:
            problems.append("department_admin needs --department-id")
        if faculty_id is not None:
            problems.append("department_admin takes --department-id, not --faculty-id")
    else:
        if faculty_id is not None or department_id is not None:
            problems.append(f"{role} takes no scope; remove --faculty-id and --department-id")

    if problems:
        return None, problems
    return Scope(faculty_id=faculty, department_id=department), []


def normalize_email(raw: str) -> str:
    return raw.strip().lower()


def mask_host(host: str) -> str:
    """The first 8 and last 14 characters of the host, with the middle hidden.

    A host too short to mask safely is shown only as an ellipsis.
    """
    if len(host) <= MASK_HEAD + MASK_TAIL:
        return "..."
    return f"{host[:MASK_HEAD]}...{host[-MASK_TAIL:]}"


def database_host(url: str) -> str:
    return urlsplit(url).hostname or ""


def is_pooled_host(host: str) -> bool:
    return POOLER_MARKER in host


def is_confirmed(answer: str) -> bool:
    return answer.strip() == "yes"


def password_problems(password: str) -> list[str]:
    """The API's own rules (8 to 128 characters) applied through the sign-up model."""
    return _field_problems(
        {"full_name": "Admin account", "email": "admin@example.com", "password": password},
        field="password",
    )


def identity_problems(full_name: str, email: str) -> list[str]:
    return _field_problems(
        {"full_name": full_name, "email": email, "password": "placeholder-password"},
        field=("full_name", "email"),
    )


def _field_problems(data: dict[str, Any], field: str | tuple[str, ...]) -> list[str]:
    fields = (field,) if isinstance(field, str) else field
    try:
        RegisterRequest.model_validate(data)
    except ValidationError as error:
        # Only the field and the rule are printed. Pydantic's own text can include the value.
        return [
            f"{item['loc'][0]}: {item['msg']}"
            for item in error.errors()
            if item["loc"] and item["loc"][0] in fields
        ]
    return []


def password_pair_problems(first: str, second: str) -> list[str]:
    if first != second:
        return ["the two passwords do not match"]
    return password_problems(first)


def validate_arguments(args: argparse.Namespace) -> list[str]:
    problems = []
    if args.role not in ROLES:
        problems.append(f"role must be one of: {', '.join(ROLES)}")
    _, scope_problems = plan_scope(args.role, args.faculty_id, args.department_id)
    problems += scope_problems
    email = normalize_email(args.email)
    # A promotion takes no name, so a placeholder stands in for the name check only.
    name = args.name if args.name is not None else "Admin account"
    problems += identity_problems(name, email)
    return problems


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create or promote an admin user.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", help="full name (required when creating a new user)")
    parser.add_argument("--role", required=True, choices=ROLES)
    parser.add_argument("--faculty-id")
    parser.add_argument("--department-id")
    parser.add_argument("--promote", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser


# ----------------------------------------------------------------- database and prompts


def check_scope_exists(
    conn: psycopg.Connection, scope: Scope, role: str
) -> tuple[uuid.UUID | None, list[str]]:
    """Confirms the faculty or department is live. For a department, returns its faculty id."""
    if role == "faculty_admin":
        row = conn.execute(LIVE_FACULTY, {"id": scope.faculty_id}).fetchone()
        return None, [] if row else ["that faculty does not exist or is deleted"]
    if role == "department_admin":
        row = conn.execute(LIVE_DEPARTMENT, {"id": scope.department_id}).fetchone()
        if row is None:
            return None, ["that department does not exist or is deleted"]
        return row["faculty_id"], []
    return None, []


def ask_password() -> str:
    while True:
        first = getpass.getpass("Password (8-128 characters): ")
        second = getpass.getpass("Type the password again: ")
        problems = password_pair_problems(first, second)
        if not problems:
            return first
        print("Not accepted:")
        for problem in problems:
            print(f"  - {problem}")


def run(conn: psycopg.Connection, args: argparse.Namespace, url_host: str) -> tuple[int, bool]:
    """Returns (exit code, whether the transaction should be committed)."""
    email = normalize_email(args.email)
    scope, _ = plan_scope(args.role, args.faculty_id, args.department_id)
    assert scope is not None  # validated earlier

    existing = conn.execute(FIND_USER, {"email": email}).fetchone()
    if existing and not args.promote:
        print("A user with this email already exists. Nothing was changed.")
        print("Run again with --promote to change that user's role and scope.")
        return 1, False

    scope_faculty = scope.faculty_id
    if args.role in ("faculty_admin", "department_admin"):
        owning_faculty, problems = check_scope_exists(conn, scope, args.role)
        if problems:
            for problem in problems:
                print(f"Not done: {problem}.")
            return 1, False
        if args.role == "department_admin":
            scope_faculty = owning_faculty

    action = "promote an existing user (role and scope only)" if existing else "create a new user"
    print(f"Target database host: {mask_host(url_host)}")
    print(f"Action:               {action}")
    print(f"Email:                {email}")
    print(f"Role:                 {args.role}")
    if existing and not existing["is_active"]:
        print(
            "Note: this account is inactive. It stays inactive; this script does not change that."
        )

    if args.dry_run:
        print("Dry run: nothing was written.")
        return 0, False

    if not is_confirmed(input("Type yes to continue, anything else to stop: ")):
        print("Stopped. Nothing was written.")
        return 1, False

    if existing:
        row = conn.execute(
            UPDATE_ROLE_AND_SCOPE,
            {
                "id": existing["id"],
                "role": args.role,
                "faculty_id": scope_faculty,
                "department_id": scope.department_id if args.role == "department_admin" else None,
            },
        ).fetchone()
    else:
        if not args.name:
            print("Not done: --name is needed to create a new user.")
            return 1, False
        password = ask_password()
        row = conn.execute(
            INSERT_USER,
            {
                "full_name": args.name.strip(),
                "email": email,
                "password_hash": hash_password(password),
                "role": args.role,
                "faculty_id": scope_faculty,
                "department_id": scope.department_id if args.role == "department_admin" else None,
            },
        ).fetchone()
    print(f"Done. User id {row['id']}, role {row['role']}.")
    return 0, True


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    problems = validate_arguments(args)
    if problems:
        for problem in problems:
            print(f"Not done: {problem}.")
        return 2

    url = database_url()
    host = database_host(url)
    if not host:
        print("Not done: DATABASE_URL has no host.")
        return 2
    if is_pooled_host(host):
        print(
            "Not done: this is a pooled connection. Use the direct (non-pooled) connection string."
        )
        return 2

    try:
        conn = psycopg.connect(url, connect_timeout=30, row_factory=dict_row)
    except psycopg.OperationalError:
        # The driver's message can name the host, so it is not printed.
        print("Not done: could not connect to the database. Check DATABASE_URL.")
        return 1

    commit = False
    try:
        code, commit = run(conn, args, host)
    except psycopg.Error as error:
        # Only the error type is printed: the message can contain row values.
        print(f"Not done: database error ({type(error).__name__}). Nothing was written.")
        code = 1
    except KeyboardInterrupt:
        print("Stopped. Nothing was written.")
        code = 1
    finally:
        if commit:
            conn.commit()
        else:
            conn.rollback()
        conn.close()
    return code


if __name__ == "__main__":
    sys.exit(main())
