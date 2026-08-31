from app.workflow import checksum_matches, file_checksum


def test_checksum_matches_accepts_prefixed_and_legacy_sha256(tmp_path):
    source = tmp_path / "sprite.png"
    source.write_bytes(b"sprite-bytes")
    prefixed = file_checksum(source)

    assert checksum_matches(source, prefixed)
    assert checksum_matches(source, prefixed.removeprefix("sha256:"))
    assert not checksum_matches(source, "0" * 64)
