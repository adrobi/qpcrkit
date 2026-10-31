import qpcr_core


def test_version_is_semver():
    assert qpcr_core.__version__.count(".") == 2
