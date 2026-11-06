import qpcr_core


def test_version_is_semver():
    assert qpcr_core.__version__.count(".") == 2


def test_changelog_describes_this_version():
    """The release page is built from this section; without it the release has no notes."""
    from pathlib import Path

    from scripts.changelog_section import section

    text = (Path(__file__).resolve().parent.parent / "CHANGELOG.md").read_text(encoding="utf-8")
    assert section(text, f"v{qpcr_core.__version__}")
    assert "[Unreleased]" not in text
