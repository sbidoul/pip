import functools
import sys
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pytest

import pip._internal.network.auth
from pip._internal.network.auth import MultiDomainBasicAuth
from tests.lib.requests_mocks import MockConnection, MockRequest, MockResponse


@pytest.fixture(scope="function", autouse=True)
def reset_keyring() -> Iterable[None]:
    yield None
    # Reset the state of the module between tests
    pip._internal.network.auth.KEYRING_DISABLED = False


@pytest.mark.parametrize(
    ["input_url", "url", "username", "password"],
    [
        (
            "http://user%40email.com:password@example.com/path",
            "http://example.com/path",
            "user@email.com",
            "password",
        ),
        (
            "http://username:password@example.com/path",
            "http://example.com/path",
            "username",
            "password",
        ),
        (
            "http://token@example.com/path",
            "http://example.com/path",
            "token",
            "",
        ),
        (
            "http://example.com/path",
            "http://example.com/path",
            None,
            None,
        ),
    ],
)
def test_get_credentials_parses_correctly(
    input_url: str, url: str, username: Optional[str], password: Optional[str]
) -> None:
    auth = MultiDomainBasicAuth()
    get = auth._get_url_and_credentials

    # Check URL parsing
    assert get(input_url) == (url, username, password)
    assert (
        # There are no credentials in the URL
        (username is None and password is None)
        or
        # Credentials were found and "cached" appropriately
        auth.passwords["example.com"] == (username, password)
    )


def test_get_credentials_not_to_uses_cached_credentials() -> None:
    auth = MultiDomainBasicAuth()
    auth.passwords["example.com"] = ("user", "pass")

    got = auth._get_url_and_credentials("http://foo:bar@example.com/path")
    expected = ("http://example.com/path", "foo", "bar")
    assert got == expected


def test_get_credentials_not_to_uses_cached_credentials_only_username() -> None:
    auth = MultiDomainBasicAuth()
    auth.passwords["example.com"] = ("user", "pass")

    got = auth._get_url_and_credentials("http://foo@example.com/path")
    expected = ("http://example.com/path", "foo", "")
    assert got == expected


def test_get_credentials_uses_cached_credentials() -> None:
    auth = MultiDomainBasicAuth()
    auth.passwords["example.com"] = ("user", "pass")

    got = auth._get_url_and_credentials("http://example.com/path")
    expected = ("http://example.com/path", "user", "pass")
    assert got == expected


def test_get_credentials_uses_cached_credentials_only_username() -> None:
    auth = MultiDomainBasicAuth()
    auth.passwords["example.com"] = ("user", "pass")

    got = auth._get_url_and_credentials("http://user@example.com/path")
    expected = ("http://example.com/path", "user", "pass")
    assert got == expected


def test_get_index_url_credentials() -> None:
    auth = MultiDomainBasicAuth(index_urls=["http://foo:bar@example.com/path"])
    get = functools.partial(
        auth._get_new_credentials, allow_netrc=False, allow_keyring=False
    )

    # Check resolution of indexes
    assert get("http://example.com/path/path2") == ("foo", "bar")
    assert get("http://example.com/path3/path2") == (None, None)


class KeyringModuleV1:
    """Represents the supported API of keyring before get_credential
    was added.
    """

    def __init__(self) -> None:
        self.saved_passwords: List[Tuple[str, str, str]] = []

    def get_password(self, system: str, username: str) -> Optional[str]:
        if system == "example.com" and username:
            return username + "!netloc"
        if system == "http://example.com/path2" and username:
            return username + "!url"
        return None

    def set_password(self, system: str, username: str, password: str) -> None:
        self.saved_passwords.append((system, username, password))


@pytest.mark.parametrize(
    "url, expect",
    (
        ("http://example.com/path1", (None, None)),
        # path1 URLs will be resolved by netloc
        ("http://user@example.com/path1", ("user", "user!netloc")),
        ("http://user2@example.com/path1", ("user2", "user2!netloc")),
        # path2 URLs will be resolved by index URL
        ("http://example.com/path2/path3", (None, None)),
        ("http://foo@example.com/path2/path3", ("foo", "foo!url")),
    ),
)
def test_keyring_get_password(
    monkeypatch: pytest.MonkeyPatch,
    url: str,
    expect: Tuple[Optional[str], Optional[str]],
) -> None:
    keyring = KeyringModuleV1()
    monkeypatch.setitem(sys.modules, "keyring", keyring)  # type: ignore[misc]
    auth = MultiDomainBasicAuth(index_urls=["http://example.com/path2"])

    actual = auth._get_new_credentials(url, allow_netrc=False, allow_keyring=True)
    assert actual == expect


def test_keyring_get_password_after_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    keyring = KeyringModuleV1()
    monkeypatch.setitem(sys.modules, "keyring", keyring)  # type: ignore[misc]
    auth = MultiDomainBasicAuth()

    def ask_input(prompt: str) -> str:
        assert prompt == "User for example.com: "
        return "user"

    monkeypatch.setattr("pip._internal.network.auth.ask_input", ask_input)
    actual = auth._prompt_for_password("example.com")
    assert actual == ("user", "user!netloc", False)


def test_keyring_get_password_after_prompt_when_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    keyring = KeyringModuleV1()
    monkeypatch.setitem(sys.modules, "keyring", keyring)  # type: ignore[misc]
    auth = MultiDomainBasicAuth()

    def ask_input(prompt: str) -> str:
        assert prompt == "User for unknown.com: "
        return "user"

    def ask_password(prompt: str) -> str:
        assert prompt == "Password: "
        return "fake_password"

    monkeypatch.setattr("pip._internal.network.auth.ask_input", ask_input)
    monkeypatch.setattr("pip._internal.network.auth.ask_password", ask_password)
    actual = auth._prompt_for_password("unknown.com")
    assert actual == ("user", "fake_password", True)


def test_keyring_get_password_username_in_index(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    keyring = KeyringModuleV1()
    monkeypatch.setitem(sys.modules, "keyring", keyring)  # type: ignore[misc]
    auth = MultiDomainBasicAuth(index_urls=["http://user@example.com/path2"])
    get = functools.partial(
        auth._get_new_credentials, allow_netrc=False, allow_keyring=True
    )

    assert get("http://example.com/path2/path3") == ("user", "user!url")
    assert get("http://example.com/path4/path1") == (None, None)


@pytest.mark.parametrize(
    "response_status, creds, expect_save",
    (
        (403, ("user", "pass", True), False),
        (
            200,
            ("user", "pass", True),
            True,
        ),
        (
            200,
            ("user", "pass", False),
            False,
        ),
    ),
)
def test_keyring_set_password(
    monkeypatch: pytest.MonkeyPatch,
    response_status: int,
    creds: Tuple[str, str, bool],
    expect_save: bool,
) -> None:
    keyring = KeyringModuleV1()
    monkeypatch.setitem(sys.modules, "keyring", keyring)  # type: ignore[misc]
    auth = MultiDomainBasicAuth(prompting=True)
    monkeypatch.setattr(auth, "_get_url_and_credentials", lambda u: (u, None, None))
    monkeypatch.setattr(auth, "_prompt_for_password", lambda *a: creds)
    if creds[2]:
        # when _prompt_for_password indicates to save, we should save
        def should_save_password_to_keyring(*a: Any) -> bool:
            return True

    else:
        # when _prompt_for_password indicates not to save, we should
        # never call this function
        def should_save_password_to_keyring(*a: Any) -> bool:
            assert False, "_should_save_password_to_keyring should not be called"

    monkeypatch.setattr(
        auth, "_should_save_password_to_keyring", should_save_password_to_keyring
    )

    req = MockRequest("https://example.com")
    resp = MockResponse(b"")
    resp.url = req.url
    connection = MockConnection()

    def _send(sent_req: MockRequest, **kwargs: Any) -> MockResponse:
        assert sent_req is req
        assert "Authorization" in sent_req.headers
        r = MockResponse(b"")
        r.status_code = response_status
        return r

    # https://github.com/python/mypy/issues/2427
    connection._send = _send  # type: ignore[assignment]

    resp.request = req
    resp.status_code = 401
    resp.connection = connection

    auth.handle_401(resp)

    if expect_save:
        assert keyring.saved_passwords == [("example.com", creds[0], creds[1])]
    else:
        assert keyring.saved_passwords == []


class KeyringModuleV2:
    """Represents the current supported API of keyring"""

    class Credential:
        def __init__(self, username: str, password: str) -> None:
            self.username = username
            self.password = password

    def get_password(self, system: str, username: str) -> None:
        assert False, "get_password should not ever be called"

    def get_credential(self, system: str, username: str) -> Optional[Credential]:
        if system == "http://example.com/path2":
            return self.Credential("username", "url")
        if system == "example.com":
            return self.Credential("username", "netloc")
        return None


@pytest.mark.parametrize(
    "url, expect",
    (
        ("http://example.com/path1", ("username", "netloc")),
        ("http://example.com/path2/path3", ("username", "url")),
        ("http://user2@example.com/path2/path3", ("username", "url")),
    ),
)
def test_keyring_get_credential(
    monkeypatch: pytest.MonkeyPatch, url: str, expect: str
) -> None:
    monkeypatch.setitem(sys.modules, "keyring", KeyringModuleV2())  # type: ignore[misc]
    auth = MultiDomainBasicAuth(index_urls=["http://example.com/path2"])

    assert (
        auth._get_new_credentials(url, allow_netrc=False, allow_keyring=True) == expect
    )


class KeyringModuleBroken:
    """Represents the current supported API of keyring, but broken"""

    def __init__(self) -> None:
        self._call_count = 0

    def get_credential(self, system: str, username: str) -> None:
        self._call_count += 1
        raise Exception("This keyring is broken!")


def test_broken_keyring_disables_keyring(monkeypatch: pytest.MonkeyPatch) -> None:
    keyring_broken = KeyringModuleBroken()
    monkeypatch.setitem(sys.modules, "keyring", keyring_broken)  # type: ignore[misc]

    auth = MultiDomainBasicAuth(index_urls=["http://example.com/"])

    assert keyring_broken._call_count == 0
    for i in range(5):
        url = "http://example.com/path" + str(i)
        assert auth._get_new_credentials(
            url, allow_netrc=False, allow_keyring=True
        ) == (None, None)
        assert keyring_broken._call_count == 1


class KeyringSubprocessResult(KeyringModuleV1):
    """Represents the subprocess call to keyring"""

    returncode = 0  # Default to zero retcode

    def __call__(
        self,
        cmd: List[str],
        *,
        env: Dict[str, str],
        stdin: Optional[Any] = None,
        capture_output: Optional[bool] = None,
        input: Optional[bytes] = None,
    ) -> Any:
        if cmd[1] == "get":
            assert stdin == -3  # subprocess.DEVNULL
            assert capture_output is True
            assert env["PYTHONIOENCODING"] == "utf-8"

            password = self.get_password(*cmd[2:])
            if password is None:
                # Expect non-zero returncode if no password present
                self.returncode = 1
            else:
                # Passwords are returned encoded with a newline appended
                self.stdout = password.encode("utf-8") + b"\n"

        if cmd[1] == "set":
            assert stdin is None
            assert capture_output is None
            assert env["PYTHONIOENCODING"] == "utf-8"
            assert input is not None

            # Input from stdin is encoded
            self.set_password(cmd[2], cmd[3], input.decode("utf-8").strip("\n"))

        return self

    def check_returncode(self) -> None:
        if self.returncode:
            raise Exception()


@pytest.mark.parametrize(
    "url, expect",
    (
        ("http://example.com/path1", (None, None)),
        # path1 URLs will be resolved by netloc
        ("http://user@example.com/path1", ("user", "user!netloc")),
        ("http://user2@example.com/path1", ("user2", "user2!netloc")),
        # path2 URLs will be resolved by index URL
        ("http://example.com/path2/path3", (None, None)),
        ("http://foo@example.com/path2/path3", ("foo", "foo!url")),
    ),
)
def test_keyring_cli_get_password(
    monkeypatch: pytest.MonkeyPatch,
    url: str,
    expect: Tuple[Optional[str], Optional[str]],
) -> None:
    monkeypatch.setattr(pip._internal.network.auth.shutil, "which", lambda x: "keyring")
    monkeypatch.setattr(
        pip._internal.network.auth.subprocess, "run", KeyringSubprocessResult()
    )
    auth = MultiDomainBasicAuth(index_urls=["http://example.com/path2"])

    actual = auth._get_new_credentials(url, allow_netrc=False, allow_keyring=True)
    assert actual == expect


@pytest.mark.parametrize(
    "response_status, creds, expect_save",
    (
        (403, ("user", "pass", True), False),
        (
            200,
            ("user", "pass", True),
            True,
        ),
        (
            200,
            ("user", "pass", False),
            False,
        ),
    ),
)
def test_keyring_cli_set_password(
    monkeypatch: pytest.MonkeyPatch,
    response_status: int,
    creds: Tuple[str, str, bool],
    expect_save: bool,
) -> None:
    monkeypatch.setattr(pip._internal.network.auth.shutil, "which", lambda x: "keyring")
    keyring = KeyringSubprocessResult()
    monkeypatch.setattr(pip._internal.network.auth.subprocess, "run", keyring)
    auth = MultiDomainBasicAuth(prompting=True)
    monkeypatch.setattr(auth, "_get_url_and_credentials", lambda u: (u, None, None))
    monkeypatch.setattr(auth, "_prompt_for_password", lambda *a: creds)
    if creds[2]:
        # when _prompt_for_password indicates to save, we should save
        def should_save_password_to_keyring(*a: Any) -> bool:
            return True

    else:
        # when _prompt_for_password indicates not to save, we should
        # never call this function
        def should_save_password_to_keyring(*a: Any) -> bool:
            assert False, "_should_save_password_to_keyring should not be called"

    monkeypatch.setattr(
        auth, "_should_save_password_to_keyring", should_save_password_to_keyring
    )

    req = MockRequest("https://example.com")
    resp = MockResponse(b"")
    resp.url = req.url
    connection = MockConnection()

    def _send(sent_req: MockRequest, **kwargs: Any) -> MockResponse:
        assert sent_req is req
        assert "Authorization" in sent_req.headers
        r = MockResponse(b"")
        r.status_code = response_status
        return r

    # https://github.com/python/mypy/issues/2427
    connection._send = _send  # type: ignore[assignment]

    resp.request = req
    resp.status_code = 401
    resp.connection = connection

    auth.handle_401(resp)

    if expect_save:
        assert keyring.saved_passwords == [("example.com", creds[0], creds[1])]
    else:
        assert keyring.saved_passwords == []
