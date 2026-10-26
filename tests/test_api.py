from fastapi.testclient import TestClient

from gpo_rag.api import app

client = TestClient(app)


def test_chat_ui_served():
    r = client.get("/")
    assert r.status_code == 200 and "GPO Report Assistant" in r.text


def test_only_configured_pdfs_served():
    assert client.get("/files/2025_annualreport.pdf").headers["content-type"] == "application/pdf"
    assert client.get("/files/secret.pdf").status_code == 404
    assert client.get("/files/..%2F..%2Fpyproject.pdf").status_code == 404


def test_ask_validates_input():
    assert client.post("/ask", json={"question": "hi"}).status_code == 422
    assert client.post("/ask", json={"question": "Revenue?", "top_k": 99}).status_code == 422
