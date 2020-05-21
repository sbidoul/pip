"""
For types associated with installation schemes.

For a general overview of available schemes and their context, see
https://docs.python.org/3/install/index.html#alternate-installation.
"""
from pip._internal.utils.typing import MYPY_CHECK_RUNNING

if MYPY_CHECK_RUNNING:
    from typing import Dict


SCHEME_KEYS = ['platlib', 'purelib', 'headers', 'scripts', 'data']


class Scheme(object):
    """A Scheme holds paths which are used as the base directories for
    artifacts associated with a Python package.
    """

    __slots__ = SCHEME_KEYS

    def __init__(
        self,
        platlib,  # type: str
        purelib,  # type: str
        headers,  # type: str
        scripts,  # type: str
        data,  # type: str
    ):
        self.platlib = platlib
        self.purelib = purelib
        self.headers = headers
        self.scripts = scripts
        self.data = data

    def as_dict(self):
        # type: () -> Dict[str, str]
        return dict(
            platlib=self.platlib,
            purelib=self.purelib,
            headers=self.headers,
            scripts=self.scripts,
            data=self.data,
        )
