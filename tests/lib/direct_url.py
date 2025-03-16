from __future__ import annotations

from pathlib import Path

from pip._internal.models.direct_url import DIRECT_URL_METADATA_NAME, DirectUrl

from tests.lib import TestPipResult


def get_created_direct_url_path(result: TestPipResult, pkg: str) -> Optional[Path]:
    direct_url_metadata_re = re.compile(
        pkg + r"-[\d\.]+\.dist-info." + DIRECT_URL_METADATA_NAME + r"$"
    )
    for filename in result.files_created:
        if (
            filename.name == DIRECT_URL_METADATA_NAME
            and filename.parent.name.endswith(".dist-info")
            and filename.parent.name.startswith(f"{pkg}-")
        ):
            return result.test_env.base_path / filename
    return None


def get_created_direct_url(result: TestPipResult, pkg: str) -> DirectUrl | None:
    direct_url_path = get_created_direct_url_path(result, pkg)
    if direct_url_path:
        with open(direct_url_path) as f:
            return DirectUrl.from_json(f.read())
    return None
