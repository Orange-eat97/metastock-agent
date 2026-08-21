from tools.result_tools import (
    _resolve_persistence_identity,
)
from tools.tool_contracts import (
    ReadMetaStockResultsInput,
    StoredMetaStockExplorerResultDTO,
)


def test_external_reference_becomes_nullable_parent_identity():
    explorer_id, explorer_name = (
        _resolve_persistence_identity(
            explorer_reference=(
                "metastock-name:#AI Bounce Off 50 100 150 MA"
            ),
            supplied_name=None,
        )
    )

    assert explorer_id is None
    assert explorer_name == "#AI Bounce Off 50 100 150 MA"


def test_result_reader_accepts_name_and_run_timestamp():
    payload = ReadMetaStockResultsInput(
        explorer_id="metastock-name:#External Explorer",
        explorer_name="#External Explorer",
        run_started_at="2026-07-22T04:00:00+00:00",
    )

    assert payload.explorer_name == "#External Explorer"
    assert payload.run_started_at == "2026-07-22T04:00:00+00:00"


def test_stored_external_result_has_result_uuid_but_no_parent_uuid():
    result = StoredMetaStockExplorerResultDTO(
        result_id="11111111-1111-1111-1111-111111111111",
        explorer_id=None,
        explorer_name="#External Explorer",
        run_started_at="2026-07-22T04:00:00+00:00",
        schema_version="1.0",
        outcome="no_matches",
        expected_count=0,
        matched_count=0,
        has_matches=False,
    )

    assert result.explorer_id is None
    assert result.explorer_name == "#External Explorer"
