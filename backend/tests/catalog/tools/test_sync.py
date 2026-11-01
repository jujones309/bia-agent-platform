from unittest.mock import sentinel

import pytest

from bia.catalog.tools import sync
from bia.catalog.tools.artifacts import ToolName
from bia.catalog.tools.registry import list_registered_tools


def test_sync_writes_every_tool_and_retires_only_the_rest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verifies the sync's decisions; the SQL itself is covered by test_repository.py."""
    upserted: list[object] = []
    kept_active: list[list[str]] = []
    monkeypatch.setattr(sync, "upsert_catalog_tool", lambda _session, tool: upserted.append(tool))
    monkeypatch.setattr(
        sync, "deactivate_catalog_tools_except", lambda _session, names: kept_active.append(names)
    )

    sync.sync_tools(sentinel.session)

    assert upserted == list_registered_tools()
    assert kept_active == [[name.value for name in ToolName]]
