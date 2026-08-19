"""Pure-function tests for repository helpers - no database needed."""
from autoeval_ops.db.repository import normalize_repo


def test_normalize_strips_https_prefix():
    assert normalize_repo("https://github.com/Owner/Repo") == "owner/repo"


def test_normalize_strips_git_suffix():
    assert normalize_repo("https://github.com/Owner/Repo.git") == "owner/repo"


def test_normalize_handles_bare_owner_repo():
    assert normalize_repo("Owner/Repo") == "owner/repo"


def test_normalize_strips_trailing_slash():
    assert normalize_repo("https://github.com/Owner/Repo/") == "owner/repo"


def test_normalize_is_idempotent():
    once = normalize_repo("https://github.com/Owner/Repo.git")
    assert normalize_repo(once) == once