from __future__ import annotations

import ssl

from scripts.fetch_ais import is_recoverable_collection_error, maybe_keep_stale_output


def test_keeps_existing_ais_output_for_recoverable_tls_error(tmp_path, capsys) -> None:
    output = tmp_path / "vessels.json"
    output.write_text('{"vessels": [{"mmsi": "123"}]}\n', encoding="utf-8")

    assert maybe_keep_stale_output(
        ssl.SSLCertVerificationError("certificate has expired"),
        output,
        allow_stale=True,
    )

    assert "Keeping existing" in capsys.readouterr().err


def test_does_not_mask_programming_errors_with_stale_output(tmp_path) -> None:
    output = tmp_path / "vessels.json"
    output.write_text('{"vessels": []}\n', encoding="utf-8")

    assert not is_recoverable_collection_error(ValueError("bad payload"))
    assert not maybe_keep_stale_output(ValueError("bad payload"), output, allow_stale=True)


def test_requires_valid_existing_output_before_using_stale_fallback(tmp_path) -> None:
    missing_output = tmp_path / "missing.json"
    invalid_output = tmp_path / "invalid.json"
    invalid_output.write_text("{not-json", encoding="utf-8")

    error = ssl.SSLCertVerificationError("certificate has expired")
    assert not maybe_keep_stale_output(error, missing_output, allow_stale=True)
    assert not maybe_keep_stale_output(error, invalid_output, allow_stale=True)
