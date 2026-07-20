from __future__ import annotations

from services.explorer_upload_protocol import (
    decode_explorer_upload_envelope,
    encode_explorer_upload_envelope,
)


def test_upload_envelope_round_trip() -> None:
    encoded = encode_explorer_upload_envelope(
        draft_id="transient:test",
        name="RSI Upload",
        description="Manual",
        columns=[
            {
                "col_letter": "A",
                "col_code": "RSI(14)",
            }
        ],
        filter_code="ColA < 30",
        assumptions=["Daily bars"],
        frontend_errors=[],
        display_text="Upload Explorer: RSI Upload",
    )

    decoded = decode_explorer_upload_envelope(encoded)

    assert decoded is not None
    assert decoded["draft_id"] == "transient:test"
    assert decoded["name"] == "RSI Upload"
    assert decoded["columns"][0]["col_code"] == "RSI(14)"
    assert decoded["filter_code"] == "ColA < 30"
    assert decoded["display_text"] == "Upload Explorer: RSI Upload"
