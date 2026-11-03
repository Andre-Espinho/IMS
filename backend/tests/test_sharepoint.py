"""SharePoint import: no network. Graph and sign-in are faked."""

import base64
import io
import json

import openpyxl
import pytest
import requests
from fastapi.testclient import TestClient
from sqlalchemy import select

from ims import sharepoint as sp
from ims.db import init_db, make_engine, session_factory
from ims.main import create_app
from ims.models import Item
from ims.sharepoint import DEFAULT_SHARE_URL, SharePointConfig, SharePointError, share_id


def _workbook_bytes() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "INVENTARIO test"
    ws.append(["DESCRICAO", "MARCA", "REFERENCIA", "id", "QTD_STOCK", "PRATELEIRA", "ESTANTE"])
    ws.append(["Item do SharePoint", "HARTING", "S1", 700, 4, "2", 3])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


class FakeSharePoint:
    def __init__(self, signed_in: bool = True):
        self.signed_in = signed_in
        self.workbook = _workbook_bytes()

    def status(self):
        return {
            "configured": True,
            "signed_in": self.signed_in,
            "account": "operador@bridgepoint.pt" if self.signed_in else None,
            "pending": False,
            "error": None,
            "share_url": DEFAULT_SHARE_URL,
        }

    def begin_sign_in(self):
        return {
            "user_code": "ABCD1234",
            "verification_uri": "https://microsoft.com/devicelogin",
            "message": "Abra o link e introduza o código",
        }

    def download_workbook(self, token=None):
        if not self.signed_in:
            raise SharePointError("Inicie sessão no SharePoint primeiro")
        return "Inventario.xlsx", self.workbook


@pytest.fixture()
def engine(tmp_path):
    eng = make_engine(tmp_path / "sp.sqlite3")
    init_db(eng)
    yield eng
    eng.dispose()


def _client(engine, service):
    return TestClient(create_app(engine, sharepoint=service))


def test_not_configured_reports_and_refuses(engine):
    with _client(engine, None) as client:
        assert client.get("/api/sharepoint/status").json() == {"configured": False}
        assert client.post("/api/sharepoint/sign-in").status_code == 422
        assert client.post("/api/sharepoint/import/dry-run").status_code == 422


def test_sign_in_returns_code_and_status(engine):
    with _client(engine, FakeSharePoint()) as client:
        code = client.post("/api/sharepoint/sign-in").json()
        assert code["user_code"] == "ABCD1234"
        status = client.get("/api/sharepoint/status").json()
        assert status["signed_in"] is True and status["account"]


def test_sharepoint_dry_run_then_commit_uses_the_same_rules(engine):
    with _client(engine, FakeSharePoint()) as client:
        dry = client.post("/api/sharepoint/import/dry-run").json()
        assert dry["rows"] == 1 and dry["committed"] is False
        assert dry["source"] == "SharePoint: Inventario.xlsx"

        committed = client.post("/api/sharepoint/import/commit").json()
        assert committed["committed"] is True and committed["new_items"] == 1
    with session_factory(engine)() as s:
        assert s.get(Item, 700).brand == "HARTING"


def test_settings_change_the_link_and_persist_it(engine, tmp_path):
    config_file = tmp_path / "sharepoint.json"
    service = sp.SharePointService(SharePointConfig(), cache_path=tmp_path / "c.bin", config_path=config_file)
    new_url = "https://contoso.sharepoint.com/sites/Armazem/Shared%20Documents/Inventario.xlsx"
    with TestClient(create_app(engine, sharepoint=service)) as client:
        response = client.put("/api/sharepoint/settings", json={"share_url": f"  {new_url}  "})
        assert response.status_code == 200
    assert service.config.share_url == new_url
    saved = json.loads(config_file.read_text(encoding="utf-8"))
    assert saved["share_url"] == new_url and saved["client_id"] == sp.DEFAULT_CLIENT_ID
    assert SharePointConfig.load(config_file).share_url == new_url


def test_settings_reject_non_sharepoint_links(engine, tmp_path):
    service = sp.SharePointService(SharePointConfig(), cache_path=tmp_path / "c.bin", config_path=tmp_path / "s.json")
    with TestClient(create_app(engine, sharepoint=service)) as client:
        for bad in ["http://bridgepointeng.sharepoint.com/x", "https://example.com/file.xlsx", "não é um link"]:
            assert client.put("/api/sharepoint/settings", json={"share_url": bad}).status_code == 422


def test_sign_out_clears_account_and_cache(engine, tmp_path):
    cache = tmp_path / "c.bin"
    cache.write_text("{}", encoding="utf-8")
    service = sp.SharePointService(SharePointConfig(), cache_path=cache, config_path=tmp_path / "s.json")
    with TestClient(create_app(engine, sharepoint=service)) as client:
        response = client.post("/api/sharepoint/sign-out")
        assert response.status_code == 200
        assert response.json()["signed_in"] is False
    assert not cache.exists()


def test_import_requires_sign_in(engine):
    with _client(engine, FakeSharePoint(signed_in=False)) as client:
        response = client.post("/api/sharepoint/import/commit")
        assert response.status_code == 422
        assert "Inicie sessão" in response.json()["detail"]


def test_share_id_is_url_safe_base64_without_padding():
    token = share_id(DEFAULT_SHARE_URL)
    assert token.startswith("u!") and "=" not in token and "/" not in token and "+" not in token
    body = token[2:] + "=" * (-len(token[2:]) % 4)
    assert base64.urlsafe_b64decode(body).decode("utf-8") == DEFAULT_SHARE_URL


def test_config_works_without_a_file_and_allows_overrides(tmp_path):
    path = tmp_path / "sharepoint.json"
    config = SharePointConfig.load(path)
    assert config.client_id == sp.DEFAULT_CLIENT_ID and config.share_url == DEFAULT_SHARE_URL
    path.write_text(json.dumps({"client_id": "  "}), encoding="utf-8")
    assert SharePointConfig.load(path).client_id == sp.DEFAULT_CLIENT_ID
    path.write_text(json.dumps({"client_id": "abc-123"}), encoding="utf-8")
    assert SharePointConfig.load(path).client_id == "abc-123"


class _Resp:
    def __init__(self, status=200, payload=None, content=b""):
        self.status_code = status
        self._payload = payload
        self.content = content
        self.response = self

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)

    def json(self):
        return self._payload


def test_download_maps_graph_calls_and_permission_errors(monkeypatch, tmp_path):
    service = sp.SharePointService(
        SharePointConfig(client_id="abc"), cache_path=tmp_path / "cache.bin"
    )
    calls = []

    def fake_get(url, headers=None, timeout=None, allow_redirects=None):
        calls.append(url)
        if "/shares/" in url:
            return _Resp(payload={"id": "item1", "name": "Inventario.xlsx",
                                  "parentReference": {"driveId": "drv"}})
        return _Resp(content=b"bytes")

    monkeypatch.setattr(sp.requests, "get", fake_get)
    name, data = service.download_workbook(token="t")
    assert name == "Inventario.xlsx" and data == b"bytes"
    assert calls[0].startswith(f"{sp.GRAPH}/shares/u!")
    assert calls[1] == f"{sp.GRAPH}/drives/drv/items/item1/content"

    monkeypatch.setattr(sp.requests, "get", lambda *a, **k: _Resp(status=403))
    with pytest.raises(SharePointError, match="Sem permissão"):
        service.download_workbook(token="t")
