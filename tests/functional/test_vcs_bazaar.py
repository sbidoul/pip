"""
Contains functional tests of the Bazaar class.
"""

import os

import pytest

from tests.lib import is_bzr_installed


@pytest.mark.skipif(
    'TRAVIS' not in os.environ,
    reason='Bazaar is only required under Travis')
def test_ensure_bzr_available():
    """Make sure that bzr is available when running in Travis."""
    assert is_bzr_installed()
