"""db/import_seed.py: parsing, validation and planning, with no database."""

import importlib.util
import pathlib
from dataclasses import replace

import pytest

SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "db" / "import_seed.py"
_spec = importlib.util.spec_from_file_location("import_seed", SCRIPT)
seed = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(seed)

FAC_HEADER = "name,short_name,source,note\n"
DEPT_HEADER = "faculty,name,short_name,hod_name,office_location,source,note\n"
SOURCE = "campus notice board"


def faculties(text):
    rows, problems = seed.parse_csv(text, seed.FACULTY_COLUMNS, "faculties.csv")
    return rows, problems


def departments(text):
    rows, problems = seed.parse_csv(text, seed.DEPARTMENT_COLUMNS, "departments.csv")
    return rows, problems


def db_faculty(**fields):
    base = {
        "id": "f-1",
        "name": "School of Computing",
        "short_name": "SOC",
        "source": SOURCE,
        "verification_status": "unverified",
        "deleted": False,
    }
    base.update(fields)
    return seed.DbFaculty(**base)


def db_department(**fields):
    base = {
        "id": "d-1",
        "faculty_id": "f-1",
        "name": "Computer Science",
        "short_name": "CSC",
        "hod_name": None,
        "office_location": None,
        "source": SOURCE,
        "verification_status": "unverified",
        "deleted": False,
    }
    base.update(fields)
    return seed.DbDepartment(**base)


def kinds(changes):
    return [c.kind for c in changes]


def apply_to_state(faculty_changes, department_changes, faculty_state, department_state):
    """Pretend to apply a plan in memory, so a second plan can be checked for no changes."""
    new_ids: dict[str, str] = {}
    faculty_state = list(faculty_state)
    department_state = list(department_state)
    for change in faculty_changes:
        if change.kind == "insert":
            fid = f"new-{change.name}"
            new_ids[change.name.lower()] = fid
            faculty_state.append(
                seed.DbFaculty(
                    fid,
                    change.values["name"],
                    change.values["short_name"],
                    change.values["source"],
                    "unverified",
                    False,
                )
            )
        elif change.kind == "update":
            faculty_state = [
                replace(
                    f,
                    name=change.values["name"],
                    short_name=change.values["short_name"],
                    source=change.values["source"],
                )
                if f.id == change.existing_id
                else f
                for f in faculty_state
            ]
    for change in department_changes:
        if change.kind == "insert":
            parent = change.parent_id or new_ids[change.faculty.lower()]
            department_state.append(
                seed.DbDepartment(
                    id=f"new-dept-{change.name}",
                    faculty_id=parent,
                    name=change.values["name"],
                    short_name=change.values["short_name"],
                    hod_name=change.values["hod_name"],
                    office_location=change.values["office_location"],
                    source=change.values["source"],
                    verification_status="unverified",
                    deleted=False,
                )
            )
        elif change.kind == "update":
            department_state = [
                replace(
                    d,
                    name=change.values["name"],
                    short_name=change.values["short_name"],
                    hod_name=change.values["hod_name"],
                    office_location=change.values["office_location"],
                    source=change.values["source"],
                )
                if d.id == change.existing_id
                else d
                for d in department_state
            ]
    return faculty_state, department_state


# ----------------------------------------------------------------- valid files


def test_valid_files_have_no_problems():
    fac_rows, fac_parse = faculties(
        FAC_HEADER + "School of Computing,SOC,campus notice board,\n"
        "School of Life Sciences,SLS,campus notice board,Check the code\n"
    )
    dept_rows, dept_parse = departments(
        DEPT_HEADER + "School of Computing,Computer Science,CSC,,,campus notice board,\n"
    )

    assert fac_parse == [] and dept_parse == []
    assert seed.validate_faculties(fac_rows, "faculties.csv") == []
    assert seed.validate_departments(dept_rows, "departments.csv", {"school of computing"}) == []


def test_real_seed_files_validate_when_present():
    data = SCRIPT.parent.parent / "data"
    if not (data / "faculties.csv").exists() or not (data / "departments.csv").exists():
        pytest.skip("data/*.csv is not in this checkout")
    fac_rows, fac_problems = seed.read_csv_file(data / "faculties.csv", seed.FACULTY_COLUMNS)
    dept_rows, dept_problems = seed.read_csv_file(data / "departments.csv", seed.DEPARTMENT_COLUMNS)
    faculty_names = {row["name"].lower() for _, row in fac_rows}

    problems = (
        fac_problems
        + dept_problems
        + seed.validate_faculties(fac_rows, "faculties.csv")
        + seed.validate_departments(dept_rows, "departments.csv", faculty_names)
    )
    assert problems == []


# ----------------------------------------------------------------- validation


def test_missing_source_is_reported():
    rows, _ = faculties(FAC_HEADER + "School of Computing,SOC,,\n")

    problems = seed.validate_faculties(rows, "faculties.csv")

    assert any("source is empty" in p and "line 2" in p for p in problems)


def test_duplicate_faculty_names_are_reported_case_insensitively():
    rows, _ = faculties(FAC_HEADER + "School of Computing,SOC,a,\nschool of computing,SOC2,b,\n")

    problems = seed.validate_faculties(rows, "faculties.csv")

    assert any("duplicate name" in p for p in problems)


def test_duplicate_department_within_one_faculty_is_reported():
    rows, _ = departments(
        DEPT_HEADER
        + "School of Computing,Computer Science,CSC,,,a,\n"
        + "school of computing,computer science,CSC,,,a,\n"
    )

    problems = seed.validate_departments(rows, "departments.csv")

    assert any("duplicate department" in p for p in problems)


def test_same_department_name_in_two_faculties_is_allowed():
    rows, _ = departments(
        DEPT_HEADER
        + "School of Computing,General Studies,,,,a,\n"
        + "School of Life Sciences,General Studies,,,,a,\n"
    )

    assert seed.validate_departments(rows, "departments.csv") == []


def test_unknown_faculty_is_reported_against_csv_and_database_names():
    rows, _ = departments(DEPT_HEADER + "School of Nowhere,Engineering,,,,a,\n")

    problems = seed.validate_departments(rows, "departments.csv", {"school of computing"})

    assert any("School of Nowhere" in p and "not in faculties.csv" in p for p in problems)


def test_unknown_and_missing_columns_are_reported():
    _, unknown = faculties("name,short_name,source,note,colour\nA,A,a,,red\n")
    _, missing = faculties("name,source,note\nA,a,\n")

    assert any("unknown column 'colour'" in p for p in unknown)
    assert any("missing column 'short_name'" in p for p in missing)


def test_control_characters_and_long_values_are_reported():
    rows, _ = faculties(FAC_HEADER + "School of\x07Computing," + "x" * 200 + ",a,\n")

    problems = seed.validate_faculties(rows, "faculties.csv")

    assert any("control character" in p for p in problems)
    assert any("longer than" in p for p in problems)


def test_every_problem_is_reported_at_once():
    rows, _ = faculties(
        FAC_HEADER + ",SOC,,\nSchool of Computing,SOC,a,\nschool of computing,SOC,,\n"
    )

    problems = seed.validate_faculties(rows, "faculties.csv")

    assert len(problems) >= 3


def test_bom_file_is_read_like_plain_utf8(tmp_path):
    path = tmp_path / "faculties.csv"
    path.write_bytes(
        b"\xef\xbb\xbf" + (FAC_HEADER + "School of Computing,SOC,campus notice board,\r\n").encode()
    )

    rows, problems = seed.read_csv_file(path, seed.FACULTY_COLUMNS)

    assert problems == []
    assert rows[0][1]["name"] == "School of Computing"


def test_non_utf8_file_is_reported_not_crashed(tmp_path):
    path = tmp_path / "faculties.csv"
    path.write_bytes(FAC_HEADER.encode() + b"School of \xff\xfe,SOC,a,\n")

    rows, problems = seed.read_csv_file(path, seed.FACULTY_COLUMNS)

    assert rows == []
    assert any("not UTF-8" in p for p in problems)


def test_wrong_number_of_fields_is_reported():
    _, problems = faculties(FAC_HEADER + "School of Computing,SOC\n")

    assert any("line 2" in p and "expected 4" in p for p in problems)


# ----------------------------------------------------------------- planning


def test_new_rows_are_inserted_unverified_and_never_marked_verified():
    rows, _ = faculties(FAC_HEADER + "School of Computing,SOC,campus notice board,\n")

    changes = seed.plan_faculties(rows, existing=[])

    assert kinds(changes) == ["insert"]
    assert "verified" not in changes[0].values
    assert "verified_by" not in changes[0].values
    assert "'unverified'" in seed.INSERT_FACULTY
    assert "verified_by" not in seed.INSERT_FACULTY
    assert "verified_at" not in seed.INSERT_DEPARTMENT


def test_blank_value_does_not_overwrite_existing_hod_name():
    existing = [db_department(hod_name="Prof. A. Bello", source="old notice")]
    rows, _ = departments(DEPT_HEADER + "School of Computing,Computer Science,CSC,,,new notice,\n")
    faculty_changes = [seed.Change("unchanged", "School of Computing", existing_id="f-1")]

    changes = seed.plan_departments(rows, faculty_changes, existing)

    assert kinds(changes) == ["update"]
    assert changes[0].values["hod_name"] == "Prof. A. Bello"
    assert "hod_name" not in changes[0].changed
    assert changes[0].changed == {"source": ("old notice", "new notice")}


def test_verified_row_that_would_change_becomes_a_conflict_not_an_update():
    existing = [db_faculty(verification_status="verified", short_name="SOC")]
    rows, _ = faculties(FAC_HEADER + "School of Computing,SOCX,campus notice board,\n")

    changes = seed.plan_faculties(rows, existing)

    assert kinds(changes) == ["conflict"]
    assert "short_name" in changes[0].reason
    assert "verified" in changes[0].reason


def test_outdated_rows_are_protected_like_verified_ones():
    existing = [db_faculty(verification_status="outdated", short_name="SOC")]
    rows, _ = faculties(FAC_HEADER + "School of Computing,SOCX,campus notice board,\n")

    assert kinds(seed.plan_faculties(rows, existing)) == ["conflict"]


def test_verified_row_with_no_difference_is_unchanged():
    existing = [db_faculty(verification_status="verified")]
    rows, _ = faculties(FAC_HEADER + "School of Computing,SOC,campus notice board,\n")

    assert kinds(seed.plan_faculties(rows, existing)) == ["unchanged"]


def test_unverified_row_is_updated_to_the_csv_values():
    existing = [db_faculty(short_name=None)]
    rows, _ = faculties(FAC_HEADER + "School of Computing,SOC,campus notice board,\n")

    changes = seed.plan_faculties(rows, existing)

    assert kinds(changes) == ["update"]
    assert changes[0].changed == {"short_name": (None, "SOC")}


def test_rows_missing_from_the_csv_are_left_alone():
    existing = [db_faculty(id="f-9", name="Retired School")]
    rows, _ = faculties(FAC_HEADER + "School of Computing,SOC,campus notice board,\n")

    changes = seed.plan_faculties(rows, existing)

    assert all("Retired School" not in c.name for c in changes)
    assert set(kinds(changes)) == {"insert"}


def test_deleted_row_with_the_same_exact_name_blocks_insert_as_a_conflict():
    existing = [db_faculty(name="School of Computing", deleted=True)]
    rows, _ = faculties(FAC_HEADER + "School of Computing,SOC,campus notice board,\n")

    changes = seed.plan_faculties(rows, existing)

    assert kinds(changes) == ["conflict"]
    assert "deleted faculty" in changes[0].reason


def test_department_under_a_new_faculty_is_inserted_with_the_faculty_name():
    fac_rows, _ = faculties(FAC_HEADER + "School of Computing,SOC,campus notice board,\n")
    dept_rows, _ = departments(
        DEPT_HEADER + "School of Computing,Computer Science,CSC,,,campus notice board,\n"
    )
    faculty_changes = seed.plan_faculties(fac_rows, existing=[])

    changes = seed.plan_departments(dept_rows, faculty_changes, existing=[])

    assert kinds(changes) == ["insert"]
    assert changes[0].parent_id is None
    assert changes[0].faculty == "School of Computing"


def test_department_is_not_planned_under_an_ambiguous_faculty():
    fac_existing = [
        db_faculty(id="f-1", name="School of Computing"),
        db_faculty(id="f-2", name="school of computing"),
    ]
    fac_rows, _ = faculties(FAC_HEADER + "School of Computing,SOC,campus notice board,\n")
    dept_rows, _ = departments(
        DEPT_HEADER + "School of Computing,Computer Science,CSC,,,campus notice board,\n"
    )
    faculty_changes = seed.plan_faculties(fac_rows, fac_existing)

    changes = seed.plan_departments(dept_rows, faculty_changes, existing=[])

    assert kinds(changes) == ["conflict"]


def test_department_of_a_verified_faculty_can_still_be_planned():
    fac_existing = [db_faculty(verification_status="verified", short_name="SOCX")]
    fac_rows, _ = faculties(FAC_HEADER + "School of Computing,SOC,campus notice board,\n")
    dept_rows, _ = departments(
        DEPT_HEADER + "School of Computing,Computer Science,CSC,,,campus notice board,\n"
    )
    faculty_changes = seed.plan_faculties(fac_rows, fac_existing)

    changes = seed.plan_departments(dept_rows, faculty_changes, existing=[])

    assert kinds(faculty_changes) == ["conflict"]
    assert kinds(changes) == ["insert"]
    assert changes[0].parent_id == "f-1"


def test_rerun_after_apply_plans_zero_changes():
    fac_rows, _ = faculties(
        FAC_HEADER
        + "School of Computing,SOC,campus notice board,\n"
        + "School of Life Sciences,SLS,campus notice board,\n"
    )
    dept_rows, _ = departments(
        DEPT_HEADER
        + "School of Computing,Computer Science,CSC,,,campus notice board,\n"
        + "School of Life Sciences,Biology,BIO,,,campus notice board,\n"
    )

    faculty_changes = seed.plan_faculties(fac_rows, existing=[])
    department_changes = seed.plan_departments(dept_rows, faculty_changes, existing=[])
    faculty_state, department_state = apply_to_state(faculty_changes, department_changes, [], [])

    second_f = seed.plan_faculties(fac_rows, faculty_state)
    second_d = seed.plan_departments(dept_rows, second_f, department_state)

    assert kinds(second_f) == ["unchanged", "unchanged"]
    assert kinds(second_d) == ["unchanged", "unchanged"]
    assert seed.summarize(second_f + second_d)["insert"] == 0
    assert seed.summarize(second_f + second_d)["update"] == 0


def test_summary_counts_each_kind():
    existing = [db_faculty(verification_status="verified", short_name="SOC")]
    rows, _ = faculties(
        FAC_HEADER
        + "School of Computing,SOCX,campus notice board,\n"
        + "School of Life Sciences,SLS,campus notice board,\n"
    )

    counts = seed.summarize(seed.plan_faculties(rows, existing))

    assert counts == {"insert": 1, "update": 0, "unchanged": 0, "conflict": 1}


def test_sql_only_inserts_unverified_and_never_deletes():
    for sql in (
        seed.INSERT_FACULTY,
        seed.UPDATE_FACULTY,
        seed.INSERT_DEPARTMENT,
        seed.UPDATE_DEPARTMENT,
    ):
        assert "DELETE" not in sql.upper()
        assert "deleted_at" not in sql
        assert "%s" in sql


class _RecordingCursor:
    """Records each statement and its parameters. Inserts return a fake new id."""

    def __init__(self, calls):
        self.calls = calls
        self._next_id = 100

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        result = _RecordingCursor(self.calls)
        result._next_id = self._next_id + 1
        result._row = (f"uuid-{self._next_id}",)
        return result

    def fetchone(self):
        return self._row


class _RecordingConn:
    def __init__(self):
        self.calls = []

    def cursor(self):
        return _RecordingCursor(self.calls)


def test_apply_writes_new_faculty_first_and_links_its_departments_to_the_new_id():
    fac_rows, _ = faculties(FAC_HEADER + "School of Computing,SOC,campus notice board,\n")
    dept_rows, _ = departments(
        DEPT_HEADER + "School of Computing,Computer Science,CSC,,,campus notice board,\n"
    )
    faculty_changes = seed.plan_faculties(fac_rows, existing=[])
    department_changes = seed.plan_departments(dept_rows, faculty_changes, existing=[])
    conn = _RecordingConn()

    seed.apply_changes(conn, faculty_changes, department_changes)

    sql = [call[0] for call in conn.calls]
    assert sql == [seed.INSERT_FACULTY, seed.INSERT_DEPARTMENT]
    assert conn.calls[0][1] == ("School of Computing", "SOC", "campus notice board")
    # The department's faculty_id is the id returned by the faculty insert.
    assert conn.calls[1][1][0] == "uuid-100"
    assert conn.calls[1][1][1] == "Computer Science"


def test_apply_updates_only_the_planned_rows_with_their_final_values():
    fac_existing = [db_faculty(short_name=None)]
    fac_rows, _ = faculties(FAC_HEADER + "School of Computing,SOC,campus notice board,\n")
    dept_existing = [db_department(hod_name="Prof. A. Bello", source="old notice")]
    dept_rows, _ = departments(
        DEPT_HEADER + "School of Computing,Computer Science,CSC,,,new notice,\n"
    )
    faculty_changes = seed.plan_faculties(fac_rows, fac_existing)
    department_changes = seed.plan_departments(dept_rows, faculty_changes, dept_existing)
    conn = _RecordingConn()

    seed.apply_changes(conn, faculty_changes, department_changes)

    assert [call[0] for call in conn.calls] == [seed.UPDATE_FACULTY, seed.UPDATE_DEPARTMENT]
    faculty_params = conn.calls[0][1]
    department_params = conn.calls[1][1]
    assert faculty_params == ("School of Computing", "SOC", "campus notice board", "f-1")
    # The blank CSV hod_name keeps the existing value.
    assert department_params == (
        "Computer Science",
        "CSC",
        "Prof. A. Bello",
        None,
        "new notice",
        "d-1",
    )
