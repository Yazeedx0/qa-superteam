import pytest

from qa_superteam.config import ConfigError, is_authorized, load_config
from qa_superteam.redact import Redactor, redact_text

# Secret-looking test inputs are assembled at runtime so this file itself
# never contains a string that secret scanners would flag.
GH = "ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8"
AWS = "AKIA" + "ABCDEFGHIJKLMNOP"
ANT = "sk-ant-" + "api03-" + "x" * 30
JWT = "eyJhbGciOiJIUzI1NiJ9" + "." + "eyJzdWIiOiIxMjM0NTY3ODkwIn0" + "." + "dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"


@pytest.mark.parametrize(
    "text,label",
    [
        (f"token {GH} leaked", "github-token"),
        (f"key={AWS}", "aws-access-key"),
        (f"ANTHROPIC_API_KEY={ANT}", "anthropic-key"),
        (f"Authorization: Bearer {JWT}", "jwt"),
        ("Authorization: Bearer abcdefghijklmnop1234", "bearer-token"),
        ("postgres://admin:hunter2pass@db.internal:5432/app", "url-credentials"),
        ("password = 'correct horse battery'", "secret-assignment"),
        ('{"api_key": "abcd1234efgh"}', "secret-assignment"),
        ("Set-Cookie: session=abc123; HttpOnly", "cookie"),
        ("contact jane.doe@acme-corp.io", "email"),
        ("card 4111 1111 1111 1111", "card-number"),
        ("-----BEGIN RSA PRIVATE KEY-----\nMIIEow\n-----END RSA PRIVATE KEY-----", "private-key"),
    ],
)
def test_redacts_known_secret_shapes(text, label):
    r = Redactor()
    out = r.redact(text)
    assert f"[REDACTED:{label}]" in out, out
    assert r.by_label.get(label) == 1


def test_keeps_structure_around_redaction():
    out, n = redact_text("Authorization: Bearer abcdefghijklmnop1234 end")
    assert out == "Authorization: Bearer [REDACTED:bearer-token] end" and n == 1


def test_synthetic_test_emails_and_non_luhn_numbers_are_kept():
    r = Redactor()
    assert r.redact("alice@example.com 1234 5678 9012 3456") == "alice@example.com 1234 5678 9012 3456"
    assert r.count == 0


@pytest.mark.parametrize("text", [
    '{"avg": 0.7390866666666667, "p(95)": 1.0319863}',
    '{"startTime": 1732371234567, "duration": 4111111111111111111111}',
    "build 4111111111111111.5",
])
def test_numbers_in_tool_reports_are_not_mistaken_for_cards(text):
    r = Redactor()
    assert r.redact(text) == text


def test_redaction_is_idempotent():
    r = Redactor()
    once = r.redact(f"token {GH}")
    assert r.redact(once) == once


def test_custom_patterns(tmp_path):
    r = Redactor.from_config([r"ACME-\d{6}"])
    assert "[REDACTED:custom-1]" in r.redact("order ACME-123456")


def test_default_config_is_read_only_and_local(tmp_path):
    cfg = load_config(tmp_path)
    p = cfg.permissions
    assert (p.write_tests, p.modify_app_code, p.allow_load_testing, p.allow_active_security, p.allow_fault_injection) == (False,) * 5
    assert cfg.is_authorized_target("http://127.0.0.1:8000/api")
    assert not cfg.is_authorized_target("https://api.example-prod.com")


def test_config_template_loads(tmp_path):
    from qa_superteam.config import CONFIG_TEMPLATE

    (tmp_path / ".qa-superteam").mkdir()
    (tmp_path / ".qa-superteam" / "config.toml").write_text(CONFIG_TEMPLATE.read_text())
    cfg = load_config(tmp_path)
    assert cfg.source.endswith("config.toml") and cfg.budgets.max_reproduce_attempts == 5


@pytest.mark.parametrize(
    "body,msg",
    [
        ("[unknown]\nx=1", "unknown config section"),
        ("[permissions]\nwrite_tests='yes'", "must be bool"),
        ("[budgets]\nmax_reproduce_attempts=100", "capped at 20"),
        ("[permissions]\nauthorized_targets='http://x'", "list of strings"),
    ],
)
def test_invalid_config_rejected(tmp_path, body, msg):
    (tmp_path / ".qa-superteam").mkdir()
    (tmp_path / ".qa-superteam" / "config.toml").write_text(body)
    with pytest.raises(ConfigError, match=msg):
        load_config(tmp_path)


@pytest.mark.parametrize(
    "url,allow,ok",
    [
        ("http://localhost:3000/x", ["http://localhost"], True),
        ("http://localhost.evil.com/", ["http://localhost"], False),
        ("https://localhost/", ["http://localhost"], False),
        ("http://staging.acme.test:8080/api/v1", ["http://staging.acme.test:8080/api"], True),
        ("http://staging.acme.test:9090/api", ["http://staging.acme.test:8080"], False),
        ("http://staging.acme.test:8080/apix", ["http://staging.acme.test:8080/api"], False),
        ("file:///etc/passwd", ["http://localhost"], False),
        ("not a url", ["http://localhost"], False),
    ],
)
def test_target_authorization(url, allow, ok):
    assert is_authorized(url, allow) is ok
