"""scripts/create_admin.py: the pure parts only. No database is opened by these tests."""

import importlib.util
import pathlib
import uuid

import pytest

SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "create_admin.py"
_spec = importlib.util.spec_from_file_location("create_admin", SCRIPT)
admin = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(admin)

FACULTY = str(uuid.UUID("11111111-1111-4111-8111-111111111111"))
DEPARTMENT = str(uuid.UUID("22222222-2222-4222-8222-222222222222"))
PASSWORD = "correct horse battery"


# ----------------------------------------------------------------- roles and scope


@pytest.mark.parametrize("role", ["super_admin", "sug"])
def test_roles_without_a_scope_take_no_scope(role):
    scope, problems = admin.plan_scope(role, None, None)

    assert problems == []
    assert scope == admin.Scope(faculty_id=None, department_id=None)


def test_faculty_admin_takes_a_faculty():
    scope, problems = admin.plan_scope("faculty_admin", FACULTY, None)

    assert problems == []
    assert scope == admin.Scope(faculty_id=uuid.UUID(FACULTY), department_id=None)


def test_department_admin_takes_a_department():
    scope, problems = admin.plan_scope("department_admin", None, DEPARTMENT)

    assert problems == []
    assert scope == admin.Scope(faculty_id=None, department_id=uuid.UUID(DEPARTMENT))


@pytest.mark.parametrize("role", ["student", "class_rep", "admin", "SUPER_ADMIN", ""])
def test_any_other_role_is_rejected(role):
    _, problems = admin.plan_scope(role, None, None)

    assert problems
    assert "role must be one of" in problems[0]


def test_unknown_role_is_refused_by_the_parser_too():
    with pytest.raises(SystemExit):
        admin.build_parser().parse_args(
            ["--email", "a@example.com", "--name", "Ada Obi", "--role", "student"]
        )


def test_faculty_admin_needs_a_faculty_and_refuses_a_department():
    _, missing = admin.plan_scope("faculty_admin", None, None)
    _, wrong = admin.plan_scope("faculty_admin", FACULTY, DEPARTMENT)

    assert any("needs --faculty-id" in p for p in missing)
    assert any("not --department-id" in p for p in wrong)


def test_department_admin_needs_a_department_and_refuses_a_faculty():
    _, missing = admin.plan_scope("department_admin", None, None)
    _, wrong = admin.plan_scope("department_admin", FACULTY, DEPARTMENT)

    assert any("needs --department-id" in p for p in missing)
    assert any("not --faculty-id" in p for p in wrong)


@pytest.mark.parametrize("role", ["super_admin", "sug"])
def test_super_admin_and_sug_refuse_any_scope_flag(role):
    _, problems = admin.plan_scope(role, FACULTY, None)

    assert any("takes no scope" in p for p in problems)


def test_a_malformed_id_is_rejected():
    _, problems = admin.plan_scope("faculty_admin", "not-a-uuid", None)

    assert any("not a valid id" in p for p in problems)


def test_validate_arguments_accepts_a_complete_super_admin():
    args = admin.build_parser().parse_args(
        ["--email", "Ada@Example.com", "--name", "Ada Obi", "--role", "super_admin"]
    )

    assert admin.validate_arguments(args) == []


def test_validate_arguments_checks_the_email_even_when_promoting():
    args = admin.build_parser().parse_args(
        ["--email", "not-an-email", "--role", "super_admin", "--promote"]
    )

    assert any("email" in p for p in admin.validate_arguments(args))


# ----------------------------------------------------------------- host and URL handling


def test_host_is_masked_to_its_first_8_and_last_14_characters():
    host = "ep-tiny-glitter-b90w2hee.c-7.eu-central-1.aws.neon.tech"

    masked = admin.mask_host(host)

    assert masked == f"{host[:8]}...{host[-14:]}"
    assert "glitter" not in masked
    assert "b90w2hee" not in masked


def test_a_short_host_is_not_shown_at_all():
    assert admin.mask_host("localhost") == "..."


def test_a_pooled_host_is_detected_and_a_direct_one_is_not():
    assert admin.is_pooled_host("ep-example-pooler.eu-central-1.aws.neon.tech") is True
    assert admin.is_pooled_host("ep-example.eu-central-1.aws.neon.tech") is False


def test_the_host_is_read_without_the_credentials():
    url = "postgresql://someone:secretpw@ep-example.example.com:5432/app?sslmode=require"

    host = admin.database_host(url)

    assert host == "ep-example.example.com"
    assert "secretpw" not in host
    assert "someone" not in host


# ----------------------------------------------------------------- email, password, name


def test_email_is_trimmed_and_lowercased():
    assert admin.normalize_email("  Ada@Example.COM ") == "ada@example.com"


def test_password_rules_are_the_api_rules():
    assert admin.password_problems("x" * 7)
    assert admin.password_problems("x" * 8) == []
    assert admin.password_problems("x" * 128) == []
    assert admin.password_problems("x" * 129)


def test_password_problems_never_contain_the_password():
    password = "Short-1"  # 7 characters: one short of the minimum

    problems = admin.password_problems(password)

    assert problems
    assert all(password not in problem for problem in problems)


def test_the_two_password_entries_must_match():
    assert admin.password_pair_problems(PASSWORD, "something else")
    assert admin.password_pair_problems(PASSWORD, PASSWORD) == []


def test_a_name_must_have_at_least_two_characters():
    assert any("full_name" in p for p in admin.identity_problems("A", "ada@example.com"))
    assert admin.identity_problems("Ada Obi", "ada@example.com") == []


def test_an_email_must_look_like_one():
    assert any("email" in p for p in admin.identity_problems("Ada Obi", "nope"))


# ----------------------------------------------------------------- confirmation


@pytest.mark.parametrize("answer", ["yes", " yes ", "yes\n"])
def test_yes_confirms(answer):
    assert admin.is_confirmed(answer) is True


@pytest.mark.parametrize("answer", ["", "y", "YES", "Yes", "no", "yes please", "1"])
def test_anything_else_stops(answer):
    assert admin.is_confirmed(answer) is False


# ---- run() and main() with a fake connection

USER_ID = uuid.UUID("33333333-3333-4333-8333-333333333333")
OWNING_FACULTY = uuid.UUID("44444444-4444-4444-8444-444444444444")


class _Result:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class FakeConn:
    """Answers by which SQL was sent, and returns dict rows like psycopg's dict_row does."""

    def __init__(self, existing=None, faculty_exists=True, department_faculty=OWNING_FACULTY):
        self.existing = existing
        self.faculty_exists = faculty_exists
        self.department_faculty = department_faculty
        self.calls = []
        self.committed = self.rolled_back = self.closed = False

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        if sql == admin.FIND_USER:
            return _Result(self.existing)
        if sql == admin.LIVE_FACULTY:
            return _Result({"?column?": 1} if self.faculty_exists else None)
        if sql == admin.LIVE_DEPARTMENT:
            row = {"faculty_id": self.department_faculty} if self.department_faculty else None
            return _Result(row)
        if sql in (admin.INSERT_USER, admin.UPDATE_ROLE_AND_SCOPE):
            return _Result({"id": USER_ID, "role": params["role"]})
        raise AssertionError(f"unexpected SQL: {sql}")

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True

    def writes(self):
        return [c for c in self.calls if c[0] in (admin.INSERT_USER, admin.UPDATE_ROLE_AND_SCOPE)]


def _args(*argv):
    return admin.build_parser().parse_args(["--email", "Ada@Example.com", *argv])


def _existing(**fields):
    row = {"id": USER_ID, "role": "student", "faculty_id": None, "department_id": None}
    row["is_active"] = True
    row.update(fields)
    return row


@pytest.fixture
def prompts(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _prompt="": "yes")
    monkeypatch.setattr(admin.getpass, "getpass", lambda _prompt="": PASSWORD)
    monkeypatch.setattr(admin, "hash_password", lambda password: f"hashed::{len(password)}")


def test_create_super_admin_with_dict_rows(prompts, capsys):
    conn = FakeConn()

    code, commit = admin.run(
        conn, _args("--name", "Ada Obi", "--role", "super_admin"), "ep-example.example.com"
    )

    (_, params) = conn.writes()[0]
    assert (code, commit) == (0, True)
    assert params["email"] == "ada@example.com"
    assert params["role"] == "super_admin"
    assert params["password_hash"] == f"hashed::{len(PASSWORD)}"
    out = capsys.readouterr().out
    assert f"User id {USER_ID}, role super_admin" in out
    assert PASSWORD not in out


def test_promote_changes_only_role_and_scope(prompts):
    conn = FakeConn(existing=_existing())

    code, commit = admin.run(
        conn, _args("--role", "super_admin", "--promote"), "ep-example.example.com"
    )

    sql, params = conn.writes()[0]
    assert (code, commit) == (0, True)
    assert sql == admin.UPDATE_ROLE_AND_SCOPE
    assert set(params) == {"id", "role", "faculty_id", "department_id"}
    assert "password" not in sql and "is_active" not in sql


def test_existing_user_without_promote_changes_nothing(prompts):
    conn = FakeConn(existing=_existing())

    code, commit = admin.run(conn, _args("--name", "Ada Obi", "--role", "sug"), "h")

    assert (code, commit) == (1, False)
    assert conn.writes() == []


def test_inactive_user_is_flagged_not_changed(prompts, capsys):
    conn = FakeConn(existing=_existing(is_active=False))

    admin.run(conn, _args("--role", "sug", "--promote"), "ep-example.example.com")

    assert "inactive" in capsys.readouterr().out
    assert "is_active" not in conn.writes()[0][0]


def test_department_admin_takes_its_faculty_from_the_department(prompts):
    conn = FakeConn()

    code, commit = admin.run(
        conn,
        _args("--name", "Ada Obi", "--role", "department_admin", "--department-id", DEPARTMENT),
        "ep-example.example.com",
    )

    _, params = conn.writes()[0]
    assert (code, commit) == (0, True)
    assert params["department_id"] == uuid.UUID(DEPARTMENT)
    assert params["faculty_id"] == OWNING_FACULTY


def test_department_admin_with_a_missing_department_is_refused(prompts):
    conn = FakeConn(department_faculty=None)

    code, commit = admin.run(
        conn,
        _args("--name", "Ada Obi", "--role", "department_admin", "--department-id", DEPARTMENT),
        "h",
    )

    assert (code, commit) == (1, False)
    assert conn.writes() == []


def test_faculty_admin_is_checked_and_scoped(prompts):
    conn = FakeConn()

    code, _ = admin.run(
        conn,
        _args("--name", "Ada Obi", "--role", "faculty_admin", "--faculty-id", FACULTY),
        "ep-example.example.com",
    )

    _, params = conn.writes()[0]
    assert code == 0
    assert params["faculty_id"] == uuid.UUID(FACULTY)
    assert params["department_id"] is None


def test_dry_run_writes_nothing_and_asks_for_no_password(monkeypatch, capsys):
    def refuse(*_a, **_k):
        raise AssertionError("a dry run must not prompt")

    monkeypatch.setattr("builtins.input", refuse)
    monkeypatch.setattr(admin.getpass, "getpass", refuse)
    for argv in (
        ["--name", "Ada Obi", "--role", "super_admin", "--dry-run"],
        ["--role", "department_admin", "--department-id", DEPARTMENT, "--dry-run", "--promote"],
    ):
        conn = FakeConn()

        code, commit = admin.run(conn, _args(*argv), "ep-example.example.com")

        assert (code, commit) == (0, False)
        assert conn.writes() == []
    assert "Dry run" in capsys.readouterr().out


def test_anything_but_yes_stops_before_the_password_prompt(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _p="": "no")
    monkeypatch.setattr(admin.getpass, "getpass", lambda _p="": pytest.fail("asked for a password"))
    conn = FakeConn()

    code, commit = admin.run(conn, _args("--name", "Ada Obi", "--role", "sug"), "h")

    assert (code, commit) == (1, False)
    assert conn.writes() == []


DIRECT_URL = "postgresql://someone:secretpw@ep-example.example.com/db"


def test_main_connects_with_dict_row_and_commits_only_after_a_write(prompts, monkeypatch):
    from psycopg.rows import dict_row

    seen = {}
    conn = FakeConn()

    def fake_connect(url, **kwargs):
        seen.update(kwargs)
        return conn

    monkeypatch.setattr(admin.psycopg, "connect", fake_connect)
    monkeypatch.setattr(admin, "database_url", lambda: DIRECT_URL)

    code = admin.main(["--email", "ada@example.com", "--name", "Ada Obi", "--role", "super_admin"])

    assert code == 0
    assert seen["row_factory"] is dict_row
    assert conn.committed and not conn.rolled_back and conn.closed


def test_main_rolls_back_on_a_dry_run(monkeypatch):
    conn = FakeConn()
    monkeypatch.setattr(admin.psycopg, "connect", lambda url, **kw: conn)
    monkeypatch.setattr(admin, "database_url", lambda: DIRECT_URL)

    code = admin.main(
        ["--email", "ada@example.com", "--name", "Ada Obi", "--role", "sug", "--dry-run"]
    )

    assert code == 0
    assert conn.rolled_back and not conn.committed


def test_main_refuses_a_pooled_host_before_connecting(monkeypatch):
    def must_not_connect(*_a, **_k):
        pytest.fail("must not connect")

    monkeypatch.setattr(admin.psycopg, "connect", must_not_connect)
    monkeypatch.setattr(
        admin, "database_url", lambda: DIRECT_URL.replace("ep-example", "ep-x-pooler")
    )

    assert admin.main(["--email", "a@example.com", "--name", "Ada Obi", "--role", "sug"]) == 2
