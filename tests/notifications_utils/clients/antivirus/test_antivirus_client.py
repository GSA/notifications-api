import io

import pytest
import requests

from notifications_utils.clients.antivirus.antivirus_client import (
    AntivirusClient,
    AntivirusError,
)


@pytest.fixture()
def antivirus(app, mocker):
    client = AntivirusClient()
    app.config["ANTIVIRUS_API_HOST"] = "https://antivirus"
    app.config["ANTIVIRUS_API_KEY"] = "test-antivirus-key"
    client.init_app(app)
    return client


def test_scan_document(antivirus, rmock):
    document = io.BytesIO(b"filecontents")
    rmock.request(
        "POST",
        "https://antivirus/scan",
        json={"ok": True},
        request_headers={
            "Authorization": "Bearer test-antivirus-key",
        },
        status_code=200,
    )

    resp = antivirus.scan(document)

    assert resp
    assert "filecontents" in rmock.last_request.text
    assert document.tell() == 0


def test_should_raise_for_status(antivirus, rmock):
    with pytest.raises(AntivirusError) as excinfo:
        _test_one_statement_for_status(antivirus, rmock)

    assert excinfo.value.message == "Antivirus error"
    assert excinfo.value.status_code == 400


def _test_one_statement_for_status(antivirus, rmock):
    rmock.request(
        "POST",
        "https://antivirus/scan",
        json={"error": "Antivirus error"},
        status_code=400,
    )

    antivirus.scan(io.BytesIO(b"document"))


def test_should_raise_for_connection_errors(antivirus, rmock):
    with pytest.raises(AntivirusError) as excinfo:
        _test_one_statement_for_connection_errors(antivirus, rmock)

    assert excinfo.value.message == "connection error"
    assert excinfo.value.status_code == 503


def _test_one_statement_for_connection_errors(antivirus, rmock):
    rmock.request(
        "POST", "https://antivirus/scan", exc=requests.exceptions.ConnectTimeout
    )
    antivirus.scan(io.BytesIO(b"document"))
