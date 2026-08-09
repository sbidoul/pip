import logging
from collections.abc import Iterable, Iterator
from typing import TYPE_CHECKING, Any

from pip._vendor.packaging.dependency_groups import DependencyGroupResolver
from pip._vendor.packaging.errors import ExceptionGroup

from pip._internal.exceptions import InstallationError
from pip._internal.models.link import Link
from pip._internal.req.constructors import (
    install_req_from_pylock_package,
    install_req_from_req_string,
)
from pip._internal.req.req_install import InstallRequirement
from pip._internal.utils.compat import tomllib
from pip._internal.utils.pylock import (
    is_valid_pylock_filename,
    select_from_pylock_path_or_url,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from pip._internal.network.session import PipSession


def parse_dependency_groups(
    groups: list[tuple[str, str]],
    session: PipSession,
    isolated: bool,
) -> list[tuple[InstallRequirement, Link | None]]:
    """
    Parse dependency groups data as provided via the CLI, in a `[path:]group` syntax.

    Raises InstallationErrors if anything goes wrong.
    """
    pyproject_groups = []
    pylock_groups = []
    for path, group in groups:
        if is_valid_pylock_filename(path):
            pylock_groups.append((path, group))
        else:
            pyproject_groups.append((path, group))
    # get requirements from pyproject groups
    resolvers = _build_resolvers(path for (path, _) in pyproject_groups)
    pyproject_reqs = []
    for req in _resolve_all_groups(resolvers, pyproject_groups):
        req_to_add = install_req_from_req_string(
            req, isolated=isolated, user_supplied=True
        )
        pyproject_reqs.append((req_to_add, None))
    # get requirements from pylock groups
    pylock_reqs = []
    # TODO: group by identical path
    for path, group in pylock_groups:
        logger.warning(
            "Using pylock.toml as a requirements source "
            "is an experimental feature. "
            "It may be removed/changed in a future release "
            "without prior warning."
        )
        for package, package_dist in select_from_pylock_path_or_url(
            path,
            session=session,
            dependency_groups=[group],
        ):
            req_to_add, locked_link = install_req_from_pylock_package(
                package,
                package_dist,
                path,
                user_supplied=True,
            )
            pylock_reqs.append((req_to_add, locked_link))
    return pyproject_reqs + pylock_reqs


def _resolve_all_groups(
    resolvers: dict[str, DependencyGroupResolver], groups: list[tuple[str, str]]
) -> Iterator[str]:
    """
    Run all resolution, converting any error from `DependencyGroupResolver` into
    an InstallationError.
    """
    for path, groupname in groups:
        resolver = resolvers[path]
        try:
            yield from (str(req) for req in resolver.resolve(groupname))
        except ExceptionGroup as eg:
            # Convert ExceptionGroup to a single InstallationError with all messages
            messages = [str(e) for e in eg.exceptions]
            raise InstallationError(
                f"[dependency-groups] resolution failed for '{groupname}' "
                f"from '{path}': {'; '.join(messages)}"
            ) from eg


def _build_resolvers(paths: Iterable[str]) -> dict[str, Any]:
    resolvers = {}
    for path in paths:
        if path in resolvers:
            continue

        pyproject = _load_pyproject(path)
        if "dependency-groups" not in pyproject:
            raise InstallationError(
                f"[dependency-groups] table was missing from '{path}'. "
                "Cannot resolve '--group' option."
            )
        raw_dependency_groups = pyproject["dependency-groups"]
        if not isinstance(raw_dependency_groups, dict):
            raise InstallationError(
                f"[dependency-groups] table was malformed in {path}. "
                "Cannot resolve '--group' option."
            )

        try:
            resolvers[path] = DependencyGroupResolver(raw_dependency_groups)
        except ExceptionGroup as eg:
            # Handle ExceptionGroup from resolver initialization
            messages = [str(e) for e in eg.exceptions]
            raise InstallationError(
                f"[dependency-groups] data was invalid in {path}: {'; '.join(messages)}"
            ) from eg

    return resolvers


def _load_pyproject(path: str) -> dict[str, Any]:
    """
    This helper loads a pyproject.toml as TOML.

    It raises an InstallationError if the operation fails.
    """
    try:
        with open(path, "rb") as fp:
            return tomllib.load(fp)
    except FileNotFoundError:
        raise InstallationError(f"{path} not found. Cannot resolve '--group' option.")
    except tomllib.TOMLDecodeError as e:
        raise InstallationError(f"Error parsing {path}: {e}") from e
    except OSError as e:
        raise InstallationError(f"Error reading {path}: {e}") from e
