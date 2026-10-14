from pathlib import Path

from scripts.env_file import repo_env_file

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def test_env_file_is_skipped_inside_the_container_image():
    # the Docker image copies the service to /app, which has no repo root above it
    assert repo_env_file(Path("/app")) is None


def test_env_file_is_the_repo_root_env_in_a_checkout():
    assert repo_env_file(Path("/repo/services/07_football_data")) == Path("/repo/.env")


def test_no_script_reaches_two_levels_up_directly():
    # ROOT.parents[1] raises IndexError in the container; use repo_env_file(ROOT) instead
    offenders = [p.name for p in SCRIPTS.glob("*.py") if "ROOT.parents[1]" in p.read_text("utf-8")]
    assert offenders == []
