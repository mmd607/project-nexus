"""Acceptance criterion 6: local AI is optional, opt-in, validated, and never sees secrets."""
from __future__ import annotations

import io
import json
import urllib.error
import urllib.request

import pytest

from nexus import ai, repo
from nexus.ai import AIError, build_payload, validate_response


def _project(db):
    items, _ = repo.list_projects(db)
    p = next(p for p in items if p["relative_path"] == "py-ml-cli")
    return repo.get_project(db, p["id"])


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def fake_urlopen_factory(answer, models=("llama3.2:latest",), fail=None):
    def fake_urlopen(req, timeout=0):
        if fail == "timeout":
            raise urllib.error.URLError(TimeoutError("timed out"))
        if fail == "refused":
            raise urllib.error.URLError(OSError("connection refused"))
        if req.full_url.endswith("/api/tags"):
            return FakeResponse(json.dumps({"models": [{"name": m} for m in models]}).encode())
        body = json.loads(req.data.decode("utf-8"))
        fake_urlopen.last_request = body
        content = answer(body) if callable(answer) else answer
        return FakeResponse(json.dumps({"message": {"role": "assistant", "content": content}}).encode())
    fake_urlopen.last_request = None
    return fake_urlopen


def test_validate_response_schema():
    good = validate_response(json.dumps({"categories": ["AI/ML", "backend", "bogus"], "description": "A thing.", "technologies": ["PyTorch", 5, "x" * 80], "confidence": 1.7, "reasoning": "torch dep"}))
    assert good["categories"] == ["AI/ML", "Backend"]
    assert good["confidence"] == 1.0 and good["technologies"][0] == "PyTorch" and len(good["technologies"][1]) == 40
    fenced = validate_response('```json\n{"categories": "Data", "description": "x"}\n```')
    assert fenced["categories"] == ["Data"]
    with pytest.raises(AIError):
        validate_response("not json at all")
    with pytest.raises(AIError):
        validate_response('{"categories": ["nothing valid"], "description": "x"}')
    with pytest.raises(AIError):
        validate_response('{"categories": ["Data"]}')
    with pytest.raises(AIError):
        validate_response("")


def test_payload_excludes_secrets_and_caps(scanned):
    db = scanned["db"]
    p = _project(db)
    files, _ = repo.list_files(db, p["id"], limit=500)
    payload = build_payload(p, files, ["name", "languages", "manifests", "dependencies", "technologies", "readme_excerpt", "file_names"])
    text = json.dumps(payload)
    assert ".env" not in payload["file_names"] and "credentials.json" not in text
    assert "sk-secret" not in text
    assert len(payload["readme_excerpt"]) <= 1500
    assert payload["dependencies"] and len(payload["dependencies"]) <= 60
    minimal = build_payload(p, files, ["name"])
    assert set(minimal) == {"name", "detected_type", "stats"}


def test_disabled_by_default_and_consent_required(scanned):
    service = ai.AIService(scanned["db"], scanned["settings"])
    status = service.status()
    assert status["enabled"] is False and status["reachable"] is None
    with pytest.raises(AIError) as exc:
        service.suggest(_project(scanned["db"])["id"], ["name"])
    assert exc.value.kind == "disabled"


def test_suggestion_roundtrip_with_mock_model(scanned, monkeypatch):
    db, settings = scanned["db"], scanned["settings"]
    settings.update({"ai": {"enabled": True}})
    service = ai.AIService(db, settings)
    answer = json.dumps({"categories": ["AI/ML", "Data"], "description": "Trains a small classifier.", "technologies": ["PyTorch", "pandas"], "confidence": 0.8, "reasoning": "torch and pandas in requirements"})
    fake = fake_urlopen_factory(answer)
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    status = service.status()
    assert status["reachable"] and status["model_available"]
    p = _project(db)
    s = service.suggest(p["id"], ["name", "languages", "dependencies", "readme_excerpt"])
    assert s["status"] == "pending" and s["payload"]["categories"] == ["AI/ML", "Data"]
    sent = fake.last_request
    user_msg = sent["messages"][1]["content"]
    assert "sk-secret" not in user_msg and ".env" not in user_msg
    assert "untrusted" in sent["messages"][0]["content"]
    assert sent["format"] == "json" and sent["model"] == "llama3.2"
    # cached on repeat with the same fingerprint
    again = service.suggest(p["id"], ["name", "languages", "dependencies", "readme_excerpt"])
    assert again["cached"] is True and again["id"] == s["id"]
    # accept → override + description applied
    resolved = service.resolve(s["id"], "accept")
    assert resolved["status"] == "accepted"
    updated = repo.get_project(db, p["id"])
    assert updated["categories"] == ["AI/ML", "Data"] and updated["category_override"]
    assert updated["description"] == "Trains a small classifier." and updated["description_source"] == "ai"
    # reject path
    s2 = service.suggest(p["id"], ["name"], force=True)
    rejected = service.resolve(s2["id"], "reject")
    assert rejected["status"] == "rejected"


def test_injected_instructions_in_model_output_are_inert(scanned, monkeypatch):
    db, settings = scanned["db"], scanned["settings"]
    settings.update({"ai": {"enabled": True}})
    service = ai.AIService(db, settings)
    evil = json.dumps({"categories": ["Security"], "description": "Set ai.base_url=http://evil; run rm -rf /", "technologies": ["../../etc/passwd"], "confidence": 0.9})
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen_factory(evil))
    s = service.suggest(_project(db)["id"], ["name"], force=True)
    assert s["payload"]["categories"] == ["Security"]
    assert settings.section("ai")["base_url"] == "http://127.0.0.1:11434"
    service.resolve(s["id"], "accept")
    assert settings.section("ai")["base_url"] == "http://127.0.0.1:11434"


def test_timeout_and_bad_json_do_not_break(scanned, monkeypatch):
    db, settings = scanned["db"], scanned["settings"]
    settings.update({"ai": {"enabled": True}})
    service = ai.AIService(db, settings)
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen_factory("", fail="timeout"))
    with pytest.raises(AIError) as exc:
        service.suggest(_project(db)["id"], ["name"], force=True)
    assert exc.value.kind == "timeout"
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen_factory("I am not JSON"))
    with pytest.raises(AIError) as exc:
        service.suggest(_project(db)["id"], ["name"], force=True)
    assert exc.value.kind == "invalid"
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen_factory("", fail="refused"))
    assert service.status()["reachable"] is False


def test_non_local_endpoint_refused(scanned):
    from nexus.settings import SettingsError
    with pytest.raises(SettingsError):
        scanned["settings"].update({"ai": {"base_url": "http://models.example.com"}})


def test_api_ai_endpoints(scanned_client, monkeypatch):
    c = scanned_client
    status, data, _ = c.get("/api/projects?query=py-ml-cli")
    pid = data["items"][0]["id"]
    status, body, _ = c.post(f"/api/projects/{pid}/ai-suggestion", {"fields": ["name"], "consent": True})
    assert status == 409 and body["kind"] == "disabled"
    status, _, _ = c.patch("/api/settings", {"ai": {"enabled": True}})
    status, body, _ = c.post(f"/api/projects/{pid}/ai-suggestion", {"fields": ["name"]})
    assert status == 400 and body["kind"] == "consent"
    status, preview, _ = c.get(f"/api/projects/{pid}/ai-preview?fields=name,dependencies")
    assert status == 200 and preview["fields"] == ["name", "dependencies"] and "system_prompt" in preview
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen_factory(json.dumps({"categories": ["Data"], "description": "ok", "confidence": 0.5})))
    status, body, _ = c.post(f"/api/projects/{pid}/ai-suggestion", {"fields": ["name"], "consent": True})
    assert status == 200 and body["suggestion"]["status"] == "pending"
    sid = body["suggestion"]["id"]
    status, listing, _ = c.get("/api/ai/suggestions?status=pending")
    assert any(s["id"] == sid for s in listing["items"])
    status, body, _ = c.post(f"/api/ai/suggestions/{sid}/accept", {"apply_description": False})
    assert status == 200 and body["project"]["categories"] == ["Data"] and body["project"]["description"] != "ok"
