"""Import faculties and departments from data/*.csv into the database.

Dry run is the default: everything is validated and the plan is printed, and nothing is
written. Only --apply writes, and all writes run in one transaction (all or nothing).

Usage (from repo root):
  python db/import_seed.py                  # dry run: show the plan
  python db/import_seed.py --apply          # write the plan
Reads DATABASE_URL from the environment or from .env in the repo root, like db/migrate.py.

Rules (see data/README.md):
  - Every row needs a source. Imported rows are 'unverified'. This script never sets
    verified, verified_by or verified_at.
  - Existing rows: only fields that differ are updated. A blank CSV value never clears data.
  - Verified (or outdated) rows are never overwritten. A change to one is listed as a
    conflict for a human to resolve.
  - Nothing is deleted or soft-deleted. A row missing from the CSV is left alone.
"""

import argparse
import csv
import io
import os
import pathlib
import sys
import unicodedata
from dataclasses import dataclass, field
from typing import Literal

import psycopg

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

FACULTY_COLUMNS = ("name", "short_name", "source", "note")
DEPARTMENT_COLUMNS = (
    "faculty",
    "name",
    "short_name",
    "hod_name",
    "office_location",
    "source",
    "note",
)
# The note column is for humans. It is checked for columns but never imported.
FACULTY_UPDATABLE = ("name", "short_name", "source")
DEPARTMENT_UPDATABLE = ("name", "short_name", "hod_name", "office_location", "source")
# Limits chosen for the importer. The schema itself only says text.
LIMITS = {
    "name": 120,
    "faculty": 120,
    "short_name": 20,
    "hod_name": 120,
    "office_location": 200,
    "source": 300,
}

INSERT_FACULTY = (
    "INSERT INTO faculties (name, short_name, verification_status, source) "
    "VALUES (%s, %s, 'unverified', %s) RETURNING id"
)
UPDATE_FACULTY = "UPDATE faculties SET name = %s, short_name = %s, source = %s WHERE id = %s::uuid"
INSERT_DEPARTMENT = (
    "INSERT INTO departments (faculty_id, name, short_name, hod_name, office_location, "
    "verification_status, source) VALUES (%s::uuid, %s, %s, %s, %s, 'unverified', %s)"
)
UPDATE_DEPARTMENT = (
    "UPDATE departments SET name = %s, short_name = %s, hod_name = %s, "
    "office_location = %s, source = %s WHERE id = %s::uuid"
)

Kind = Literal["insert", "update", "unchanged", "conflict"]


# ----------------------------------------------------------------- reading files


def read_csv_file(
    path: pathlib.Path, columns: tuple[str, ...]
) -> tuple[list[tuple[int, dict[str, str]]], list[str]]:
    """Read one CSV. Returns ((line number, row) pairs, problems)."""
    if not path.exists():
        return [], [f"{path.name}: file not found"]
    try:
        # utf-8-sig drops the byte order mark that Excel adds.
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        return [], [f"{path.name}: not UTF-8. Save the file as 'CSV UTF-8'."]
    return parse_csv(text, columns, path.name)


def parse_csv(
    text: str, columns: tuple[str, ...], filename: str
) -> tuple[list[tuple[int, dict[str, str]]], list[str]]:
    """Parse CSV text into trimmed rows. Pure: takes text, returns data and problems."""
    text = text.lstrip("﻿")
    reader = csv.reader(io.StringIO(text, newline=""))
    header_row = next(reader, None)
    if header_row is None:
        return [], [f"{filename}: the file is empty"]

    header = [cell.strip().lower() for cell in header_row]
    problems = []
    for column in columns:
        if column not in header:
            problems.append(f"{filename}: missing column '{column}'")
    for column in header:
        if column not in columns:
            problems.append(f"{filename}: unknown column '{column}'")
    if len(set(header)) != len(header):
        problems.append(f"{filename}: a column appears more than once")
    if problems:
        return [], problems

    rows = []
    for line_no, values in enumerate(reader, start=2):
        if not any(value.strip() for value in values):
            continue  # Excel often leaves blank lines at the end
        if len(values) != len(header):
            problems.append(
                f"{filename} line {line_no}: {len(values)} values, expected {len(header)}"
            )
            continue
        rows.append((line_no, {h: v.strip() for h, v in zip(header, values, strict=True)}))
    return rows, problems


# ----------------------------------------------------------------- validation


def check_value(where: str, column: str, value: str) -> list[str]:
    problems = []
    if any(unicodedata.category(char) == "Cc" for char in value):
        problems.append(f"{where}: {column} contains a control character")
    if len(value) > LIMITS.get(column, 10**9):
        problems.append(f"{where}: {column} is longer than {LIMITS[column]} characters")
    return problems


def validate_faculties(rows: list[tuple[int, dict[str, str]]], filename: str) -> list[str]:
    problems = []
    seen: dict[str, int] = {}
    for line, row in rows:
        where = f"{filename} line {line}"
        for column in ("name", "short_name", "source"):
            problems += check_value(where, column, row[column])
        if not row["name"]:
            problems.append(f"{where}: name is empty")
        if not row["source"]:
            problems.append(f"{where}: source is empty (every row needs a source)")
        key = row["name"].lower()
        if key and key in seen:
            problems.append(f"{where}: duplicate name '{row['name']}' (also on line {seen[key]})")
        elif key:
            seen[key] = line
    return problems


def validate_departments(
    rows: list[tuple[int, dict[str, str]]],
    filename: str,
    known_faculties: set[str] | None = None,
) -> list[str]:
    """Checks the file on its own. Pass known_faculties (lower-case names) to also check that
    each faculty is in faculties.csv or the database. None skips that check."""
    problems = []
    seen: dict[tuple[str, str], int] = {}
    for line, row in rows:
        where = f"{filename} line {line}"
        for column in ("faculty", "name", "short_name", "hod_name", "office_location", "source"):
            problems += check_value(where, column, row[column])
        if not row["faculty"]:
            problems.append(f"{where}: faculty is empty")
        if not row["name"]:
            problems.append(f"{where}: name is empty")
        if not row["source"]:
            problems.append(f"{where}: source is empty (every row needs a source)")
        if (
            known_faculties is not None
            and row["faculty"]
            and (row["faculty"].lower() not in known_faculties)
        ):
            problems.append(
                f"{where}: faculty '{row['faculty']}' is not in faculties.csv or the database"
            )
        key = (row["faculty"].lower(), row["name"].lower())
        if key[1] and key in seen:
            problems.append(
                f"{where}: duplicate department '{row['name']}' in '{row['faculty']}' "
                f"(also on line {seen[key]})"
            )
        elif key[1]:
            seen[key] = line
    return problems


# ----------------------------------------------------------------- database state


@dataclass(frozen=True)
class DbFaculty:
    id: str
    name: str
    short_name: str | None
    source: str | None
    verification_status: str
    deleted: bool


@dataclass(frozen=True)
class DbDepartment:
    id: str
    faculty_id: str
    name: str
    short_name: str | None
    hod_name: str | None
    office_location: str | None
    source: str | None
    verification_status: str
    deleted: bool


def load_state(conn: psycopg.Connection) -> tuple[list[DbFaculty], list[DbDepartment]]:
    """Every row, including soft-deleted ones: their names still block exact-name inserts."""
    faculties = [
        DbFaculty(str(r[0]), r[1], r[2], r[3], r[4], r[5])
        for r in conn.execute(
            "SELECT id, name, short_name, source, verification_status, deleted_at IS NOT NULL "
            "FROM faculties"
        ).fetchall()
    ]
    departments = [
        DbDepartment(str(r[0]), str(r[1]), r[2], r[3], r[4], r[5], r[6], r[7], r[8])
        for r in conn.execute(
            "SELECT id, faculty_id, name, short_name, hod_name, office_location, source, "
            "verification_status, deleted_at IS NOT NULL FROM departments"
        ).fetchall()
    ]
    return faculties, departments


# ----------------------------------------------------------------- planning


@dataclass(frozen=True)
class Change:
    kind: Kind
    name: str
    # insert: the values to insert. update: the complete final values (blanks keep old values).
    values: dict[str, str | None] = field(default_factory=dict)
    faculty: str = ""  # departments: the faculty name as written in the CSV
    existing_id: str | None = None  # the matched row, for update and unchanged
    parent_id: str | None = None  # departments: the matched faculty, None if it is new
    changed: dict[str, tuple[str | None, str | None]] = field(default_factory=dict)
    reason: str = ""


def _blank_to_none(value: str) -> str | None:
    return value or None


def _merge(current, incoming: dict[str, str], updatable: tuple[str, ...]):
    """Fields that differ, and the final values. A blank incoming value never overwrites."""
    changed: dict[str, tuple[str | None, str | None]] = {}
    final: dict[str, str | None] = {}
    for name in updatable:
        old = getattr(current, name)
        new = incoming[name]
        if new and new != old:
            changed[name] = (old, new)
            final[name] = new
        else:
            final[name] = old
    return changed, final


def plan_faculties(
    rows: list[tuple[int, dict[str, str]]], existing: list[DbFaculty]
) -> list[Change]:
    live = [f for f in existing if not f.deleted]
    changes = []
    for _, row in rows:
        name = row["name"]
        matches = [f for f in live if f.name.lower() == name.lower()]
        if len(matches) > 1:
            changes.append(Change("conflict", name, reason="matches more than one live faculty"))
            continue
        if not matches:
            if any(f.name == name for f in existing):
                changes.append(
                    Change(
                        "conflict",
                        name,
                        reason="a deleted faculty already uses this exact name",
                    )
                )
                continue
            changes.append(
                Change(
                    "insert",
                    name,
                    values={
                        "name": name,
                        "short_name": _blank_to_none(row["short_name"]),
                        "source": row["source"],
                    },
                )
            )
            continue

        match = matches[0]
        changed, final = _merge(match, row, FACULTY_UPDATABLE)
        if not changed:
            changes.append(Change("unchanged", name, existing_id=match.id))
            continue
        if match.verification_status != "unverified":
            changes.append(
                Change(
                    "conflict",
                    name,
                    existing_id=match.id,
                    changed=changed,
                    reason=f"already {match.verification_status}; would change "
                    + ", ".join(changed),
                )
            )
            continue
        if "name" in changed and any(
            f.id != match.id and f.name == final["name"] for f in existing
        ):
            changes.append(
                Change(
                    "conflict",
                    name,
                    existing_id=match.id,
                    changed=changed,
                    reason="the new name is already used by another faculty",
                )
            )
            continue
        changes.append(Change("update", name, values=final, existing_id=match.id, changed=changed))
    return changes


def plan_departments(
    rows: list[tuple[int, dict[str, str]]],
    faculty_changes: list[Change],
    existing: list[DbDepartment],
) -> list[Change]:
    faculty_by_name = {c.name.lower(): c for c in faculty_changes}
    changes = []
    for _, row in rows:
        name = row["name"]
        faculty = faculty_by_name.get(row["faculty"].lower())
        if faculty is None:
            changes.append(
                Change("conflict", name, faculty=row["faculty"], reason="faculty not found")
            )
            continue
        if faculty.kind == "conflict" and faculty.existing_id is None:
            # Only blocks when the faculty itself could not be matched. A verified faculty
            # with a conflicting field still has an id, so its departments can be planned.
            changes.append(
                Change(
                    "conflict",
                    name,
                    faculty=row["faculty"],
                    reason="its faculty has a conflict; resolve that first",
                )
            )
            continue
        parent_id = faculty.existing_id  # None when the faculty is being inserted
        siblings = [d for d in existing if parent_id and d.faculty_id == parent_id]

        matches = [d for d in siblings if not d.deleted and d.name.lower() == name.lower()]
        if len(matches) > 1:
            changes.append(
                Change(
                    "conflict",
                    name,
                    faculty=row["faculty"],
                    reason="matches more than one live department",
                )
            )
            continue
        if not matches:
            if any(d.name == name for d in siblings):
                changes.append(
                    Change(
                        "conflict",
                        name,
                        faculty=row["faculty"],
                        reason="a deleted department already uses this exact name",
                    )
                )
                continue
            changes.append(
                Change(
                    "insert",
                    name,
                    faculty=row["faculty"],
                    parent_id=parent_id,
                    values={
                        "name": name,
                        "short_name": _blank_to_none(row["short_name"]),
                        "hod_name": _blank_to_none(row["hod_name"]),
                        "office_location": _blank_to_none(row["office_location"]),
                        "source": row["source"],
                    },
                )
            )
            continue

        match = matches[0]
        changed, final = _merge(match, row, DEPARTMENT_UPDATABLE)
        if not changed:
            changes.append(Change("unchanged", name, faculty=row["faculty"], existing_id=match.id))
            continue
        if match.verification_status != "unverified":
            changes.append(
                Change(
                    "conflict",
                    name,
                    faculty=row["faculty"],
                    existing_id=match.id,
                    changed=changed,
                    reason=f"already {match.verification_status}; would change "
                    + ", ".join(changed),
                )
            )
            continue
        if "name" in changed and any(
            d.id != match.id and d.name == final["name"] for d in siblings
        ):
            changes.append(
                Change(
                    "conflict",
                    name,
                    faculty=row["faculty"],
                    existing_id=match.id,
                    changed=changed,
                    reason="the new name is already used by another department",
                )
            )
            continue
        changes.append(
            Change(
                "update",
                name,
                faculty=row["faculty"],
                values=final,
                existing_id=match.id,
                changed=changed,
            )
        )
    return changes


# ----------------------------------------------------------------- applying


def apply_changes(
    conn: psycopg.Connection, faculty_changes: list[Change], department_changes: list[Change]
) -> None:
    """Write the plan. The caller's connection transaction decides whether it commits."""
    new_faculty_ids: dict[str, str] = {}
    with conn.cursor() as cur:
        for change in faculty_changes:
            if change.kind == "insert":
                v = change.values
                row = cur.execute(
                    INSERT_FACULTY, (v["name"], v["short_name"], v["source"])
                ).fetchone()
                new_faculty_ids[change.name.lower()] = str(row[0])
            elif change.kind == "update":
                v = change.values
                cur.execute(
                    UPDATE_FACULTY, (v["name"], v["short_name"], v["source"], change.existing_id)
                )
        for change in department_changes:
            if change.kind == "insert":
                parent = change.parent_id or new_faculty_ids[change.faculty.lower()]
                v = change.values
                cur.execute(
                    INSERT_DEPARTMENT,
                    (
                        parent,
                        v["name"],
                        v["short_name"],
                        v["hod_name"],
                        v["office_location"],
                        v["source"],
                    ),
                )
            elif change.kind == "update":
                v = change.values
                cur.execute(
                    UPDATE_DEPARTMENT,
                    (
                        v["name"],
                        v["short_name"],
                        v["hod_name"],
                        v["office_location"],
                        v["source"],
                        change.existing_id,
                    ),
                )


# ----------------------------------------------------------------- reporting


def summarize(changes: list[Change]) -> dict[str, int]:
    counts = {"insert": 0, "update": 0, "unchanged": 0, "conflict": 0}
    for change in changes:
        counts[change.kind] += 1
    return counts


def describe(change: Change) -> str:
    where = f" [{change.faculty}]" if change.faculty else ""
    if change.kind == "insert":
        return f"  + {change.name}{where}"
    if change.kind == "update":
        diffs = ", ".join(f"{k}: {old!r} -> {new!r}" for k, (old, new) in change.changed.items())
        return f"  ~ {change.name}{where}: {diffs}"
    return f"  ! {change.name}{where}: {change.reason}"


def format_plan(
    faculty_changes: list[Change], department_changes: list[Change], applying: bool
) -> list[str]:
    lines = []
    if not applying:
        lines.append("DRY RUN: nothing will be written. Run with --apply to write.")
        lines.append("")
    for title, changes in (("faculties", faculty_changes), ("departments", department_changes)):
        counts = summarize(changes)
        lines.append(f"{title} ({len(changes)} rows in the file)")
        for kind, label in (
            ("insert", "to insert"),
            ("update", "to update"),
            ("conflict", "skipped: conflict, needs a human"),
        ):
            items = [c for c in changes if c.kind == kind]
            if items:
                lines.append(f"  {label} ({counts[kind]}):")
                lines += [describe(c) for c in items]
        lines.append(f"  unchanged: {counts['unchanged']}")
        lines.append("")
    total_f = summarize(faculty_changes)
    total_d = summarize(department_changes)
    lines.append(
        "Summary: "
        f"faculties inserted {total_f['insert']}, updated {total_f['update']}, "
        f"unchanged {total_f['unchanged']}, skipped {total_f['conflict']}; "
        f"departments inserted {total_d['insert']}, updated {total_d['update']}, "
        f"unchanged {total_d['unchanged']}, skipped {total_d['conflict']}."
    )
    return lines


def problems_report(problems: list[str]) -> list[str]:
    return [f"PROBLEM: {problem}" for problem in problems] + [
        f"{len(problems)} problem(s). Nothing was written. Fix the files and run again."
    ]


# ----------------------------------------------------------------- command line


def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("DATABASE_URL="):
                return line.split("=", 1)[1].strip().strip("'\"")
    sys.exit("DATABASE_URL is not set (copy .env.example to .env)")


def connect(applying: bool) -> psycopg.Connection:
    try:
        # 30 seconds: a serverless database can take a while to wake up.
        conn = psycopg.connect(database_url(), connect_timeout=30)
    except psycopg.OperationalError:
        # The driver's message can name the host, so it is not printed.
        sys.exit("Could not connect to the database. Check DATABASE_URL in .env.")
    if not applying:
        conn.execute("SET TRANSACTION READ ONLY")
    return conn


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--apply", action="store_true", help="write the plan (default: dry run)")
    parser.add_argument("--faculties", type=pathlib.Path, default=DATA / "faculties.csv")
    parser.add_argument("--departments", type=pathlib.Path, default=DATA / "departments.csv")
    args = parser.parse_args(argv)

    faculty_rows, problems = read_csv_file(args.faculties, FACULTY_COLUMNS)
    department_rows, more = read_csv_file(args.departments, DEPARTMENT_COLUMNS)
    problems += more
    problems += validate_faculties(faculty_rows, args.faculties.name)
    problems += validate_departments(department_rows, args.departments.name)
    if problems:
        # Stage 1 is file-only, so the database is not opened while the files are broken.
        print("\n".join(problems_report(problems)))
        return 1

    with connect(args.apply) as conn:
        faculties, departments = load_state(conn)
        known = {f.name.lower() for f in faculties if not f.deleted}
        known |= {row["name"].lower() for _, row in faculty_rows}
        problems = validate_departments(department_rows, args.departments.name, known)
        if problems:
            print("\n".join(problems_report(problems)))
            return 1

        faculty_changes = plan_faculties(faculty_rows, faculties)
        department_changes = plan_departments(department_rows, faculty_changes, departments)

        print("\n".join(format_plan(faculty_changes, department_changes, args.apply)))

        if args.apply:
            apply_changes(conn, faculty_changes, department_changes)
            # The 'with' block commits here. Any exception above rolls everything back.
            print("\nApplied in one transaction.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
