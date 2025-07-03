import base64
from io import BytesIO

from notifications_python_client.utils import DOCUMENT_UPLOAD_SIZE_LIMIT, prepare_upload


def test_prepare_upload_success():
    content = b"hello world"
    f = BytesIO(content)
    filename = "test.txt"
    confirm_email_before_download = True
    retention_period = "1 day"

    result = prepare_upload(
        f,
        filename=filename,
        confirm_email_before_download=confirm_email_before_download,
        retention_period=retention_period,
    )
    expected = {
        "file": base64.b64encode(content).decode("ascii"),
        "filename": filename,
        "confirm_email_before_download": confirm_email_before_download,
        "retention_period": retention_period,
    }
    assert result == expected


def test_prepare_upload_file_too_large():
    content = b"a" * (DOCUMENT_UPLOAD_SIZE_LIMIT + 1)
    f = BytesIO(content)

    try:
        prepare_upload(f)
        assert 1 == 0, "Expected ValueError for large file"
    except ValueError as e:
        assert str(e) == "File is larger than 2MB"
