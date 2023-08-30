from app.errors import VirusScanError


def test_virus_scan_error():
    vse = VirusScanError("a message")
    assert "a message" in vse.args
