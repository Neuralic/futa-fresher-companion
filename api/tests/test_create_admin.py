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
