from .conftest import register


def test_public_health_and_pillars(client):
    health = client.get("/api/platform/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.json()["database"] == "ok"

    pillars = client.get("/api/platform/pillars")
    assert pillars.status_code == 200
    assert len(pillars.json()) == 6
    assert {pillar["product"] for pillar in pillars.json()} >= {"BriefCase", "The Checkbar"}


def test_register_me_login_and_refresh(client):
    headers = register(client, "owner@example.com", "Owner Firm")
    me = client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["role"] == "owner"
    assert me.json()["email"] == "owner@example.com"

    bad_login = client.post(
        "/api/auth/login",
        json={"email": "owner@example.com", "password": "wrong"},
    )
    assert bad_login.status_code == 401

    login = client.post(
        "/api/auth/login",
        json={"email": "owner@example.com", "password": "StrongPass123!"},
    )
    assert login.status_code == 200
    refresh = client.post(
        "/api/auth/refresh",
        json={"refresh_token": login.json()["refresh_token"]},
    )
    assert refresh.status_code == 200
    assert refresh.json()["access_token"]


def test_auth_required_and_validation_error(client):
    assert client.get("/api/auth/me").status_code == 401
    response = client.post(
        "/api/auth/register",
        json={"tenant_name": "A", "email": "bad", "full_name": "B", "password": "short"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_checkbar_ask_and_history(client):
    headers = register(client, "checkbar@example.com", "Checkbar Firm")
    response = client.post(
        "/api/checkbar/ask",
        headers=headers,
        json={
            "question": "What is the difference between civil and criminal cases?",
            "user_type": "General public",
            "area_of_law": "Understanding a legal concept or procedure",
            "location": "Kenya",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["provider"] == "local"
    assert "not legal advice" in body["disclaimer"]
    assert body["citations"]

    history = client.get("/api/checkbar/history", headers=headers)
    assert history.status_code == 200
    assert history.json()[0]["question"].startswith("What is the difference")


def test_briefcase_workflow_and_tenant_isolation(client):
    headers_a = register(client, "a@example.com", "Firm A")
    headers_b = register(client, "b@example.com", "Firm B")

    client_response = client.post(
        "/api/briefcase/clients",
        headers=headers_a,
        json={"name": "Acme Ltd", "email": "acme@example.com"},
    )
    assert client_response.status_code == 201, client_response.text
    client_id = client_response.json()["id"]

    forbidden = client.get(f"/api/briefcase/clients/{client_id}", headers=headers_b)
    assert forbidden.status_code == 404

    case = client.post(
        "/api/briefcase/cases",
        headers=headers_a,
        json={"title": "Services agreement review", "client_id": client_id},
    )
    assert case.status_code == 201, case.text
    case_id = case.json()["id"]

    time_entry = client.post(
        "/api/briefcase/time-entries",
        headers=headers_a,
        json={"case_id": case_id, "description": "Reviewed draft agreement", "minutes": 90, "rate_cents": 20000},
    )
    assert time_entry.status_code == 201, time_entry.text

    invoice = client.post(
        "/api/briefcase/invoices",
        headers=headers_a,
        json={
            "client_id": client_id,
            "case_id": case_id,
            "items": [{"description": "Legal review", "quantity": 2, "unit_price_cents": 100000}],
        },
    )
    assert invoice.status_code == 201, invoice.text
    assert invoice.json()["total_cents"] == 200000
    assert invoice.json()["number"].startswith("INV-")

    overview = client.get("/api/briefcase/overview", headers=headers_a)
    assert overview.json()["clients"] == 1
    assert overview.json()["cases"] == 1
    assert overview.json()["open_cases"] == 1

    updated = client.patch(
        f"/api/briefcase/invoices/{invoice.json()['id']}/status?status=paid",
        headers=headers_a,
    )
    assert updated.json()["status"] == "paid"


def test_talent_public_opportunities_and_application(client):
    headers = register(client, "talent@example.com", "Talent Firm")
    opportunity = client.post(
        "/api/talent/opportunities",
        headers=headers,
        json={"title": "Legal Intern", "organization": "LegAlly", "category": "internship"},
    )
    assert opportunity.status_code == 201, opportunity.text
    opportunity_id = opportunity.json()["id"]

    public_list = client.get("/api/talent/opportunities")
    assert any(row["id"] == opportunity_id for row in public_list.json())

    application = client.post(
        f"/api/talent/opportunities/{opportunity_id}/apply",
        json={"name": "Jane Doe", "email": "jane@example.com", "cover_letter": "Interested"},
    )
    assert application.status_code == 201, application.text
    assert application.json()["status"] == "submitted"

    applications = client.get("/api/talent/applications", headers=headers)
    assert len(applications.json()) == 1


def test_education_enrollment_and_progress(client):
    headers = register(client, "edu@example.com", "Academy Firm")
    resource = client.post(
        "/api/education/resources",
        headers=headers,
        json={"title": "Kenya legal system", "category": "guide", "level": "beginner"},
    )
    assert resource.status_code == 201, resource.text
    resource_id = resource.json()["id"]

    enrollment = client.post(
        "/api/education/enrollments",
        headers=headers,
        json={"resource_id": resource_id},
    )
    assert enrollment.status_code == 201, enrollment.text
    enrollment_id = enrollment.json()["id"]

    progress = client.patch(
        f"/api/education/enrollments/{enrollment_id}/progress?progress=100",
        headers=headers,
    )
    assert progress.status_code == 200
    assert progress.json()["status"] == "completed"
    assert progress.json()["progress"] == 100


def test_innovation_submit_and_review(client):
    headers = register(client, "innovate@example.com", "Innovation Firm")
    submission = client.post(
        "/api/innovation/",
        headers=headers,
        json={"title": "Contract review agent", "sector": "legal tech", "stage": "mvp"},
    )
    assert submission.status_code == 201, submission.text
    innovation_id = submission.json()["id"]

    review = client.patch(
        f"/api/innovation/{innovation_id}/status?status=accepted",
        headers=headers,
    )
    assert review.status_code == 200
    assert review.json()["status"] == "accepted"


def test_ai_draft_with_mocked_pico(client, monkeypatch):
    import importlib

    ai_router = importlib.import_module("app.modules.ai.router")

    async def fake_stream(app_id, prompt, on_chunk):
        assert app_id
        assert "Draft" in prompt
        return "DRAFTED LEGAL DOCUMENT"

    monkeypatch.setattr(ai_router, "stream_pico", fake_stream)
    headers = register(client, "ai@example.com", "AI Firm")
    response = client.post(
        "/api/ai/ask",
        headers=headers,
        json={"preset": "document", "prompt": "Draft a services agreement for a Kenyan startup."},
    )
    assert response.status_code == 200, response.text
    assert response.json()["provider"] == "pico"
    assert response.json()["answer"] == "DRAFTED LEGAL DOCUMENT"


def test_platform_metrics_and_audit_logs(client):
    headers = register(client, "metrics@example.com", "Metrics Firm")
    client.post(
        "/api/briefcase/clients",
        headers=headers,
        json={"name": "Metrics Client"},
    )
    metrics = client.get("/api/platform/metrics", headers=headers)
    assert metrics.status_code == 200
    assert metrics.json()["counts"]["clients"] == 1

    logs = client.get("/api/platform/audit-logs", headers=headers)
    assert logs.status_code == 200
    assert any(log["action"] == "briefcase.client.create" for log in logs.json())


def test_static_ui_served(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "LegAlly" in response.text
    assert "The Checkbar" in response.text
