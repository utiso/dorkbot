from dorkbot import __version__
from importlib.metadata import version

def test_version():
    assert version("dorkbot") == __version__
