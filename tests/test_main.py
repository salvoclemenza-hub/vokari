from pathlib import Path

from app import main as main_mod


def test_icon_path_finds_committed_asset():
    """L'icona dell'app è presente nel repo e _icon_path la trova (FB-E)."""
    p = main_mod._icon_path()
    assert p is not None
    assert Path(p).exists()
    assert Path(p).suffix in (".ico", ".png")
