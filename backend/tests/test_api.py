from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)


def test_upload_rejects_unsupported_file_type():
    response = client.post("/api/documents", files={"file": ("essay.docx", b"data")})
    assert response.status_code == 400
    assert "PDF or plain-text" in response.json()["detail"]


def test_upload_rejects_empty_file():
    response = client.post("/api/documents", files={"file": ("essay.txt", b"")})
    assert response.status_code == 400
    assert response.json()["detail"] == "The selected file is empty."


def test_question_validation_rejects_short_question():
    response = client.post("/api/documents/missing/questions", json={"question": "?"})
    assert response.status_code == 422