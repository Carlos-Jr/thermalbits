import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--output-dir",
        action="store",
        default=None,
        help="Directory to save output images. Defaults to a temporary directory.",
    )


@pytest.fixture
def output_dir(request: pytest.FixtureRequest, tmp_path):
    custom = request.config.getoption("--output-dir")
    if custom:
        from pathlib import Path
        d = Path(custom)
        d.mkdir(parents=True, exist_ok=True)
        return d
    return tmp_path
