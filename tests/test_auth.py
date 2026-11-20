from datetime import timedelta

from flask_jwt_extended import create_access_token

from tests.conftest import PASSWORD


def _register(client, **overrides):
    payload = {"username": "newuser", "email": "new@test.local", "full_name": "New User",
               "password": "Secure123", "role": "relief_coordinator", **overrides}
    return client.post("/api/auth/register", json=payload)


class TestRegistration:
    def test_register_success(self, client):
        resp = _register(client)
        body = resp.get_json()
        assert resp.status_code == 201
        assert body["success"] is True
        assert body["data"]["role"] == "relief_coordinator"
        assert "password" not in body["data"] and "password_hash" not in body["data"]

    def test_password_is_hashed(self, client, app):
        _register(client)
        from app.models import User

        user = User.query.filter_by(username="newuser").one()
        assert user.password_hash != "Secure123"
        assert user.check_password("Secure123")

    def test_register_defaults_to_operator(self, client):
        resp = _register(client, role=None)
        assert resp.status_code == 400  # explicit null role is invalid
        payload = {"username": "op2", "email": "op2@test.local", "full_name": "Op Two", "password": "Secure123"}
        resp = client.post("/api/auth/register", json=payload)
        assert resp.status_code == 201
        assert resp.get_json()["data"]["role"] == "control_room_operator"

    def test_cannot_self_register_as_admin(self, client):
        resp = _register(client, role="admin")
        assert resp.status_code == 403
        assert resp.get_json()["success"] is False

    def test_duplicate_username_conflict(self, client):
        _register(client)
        resp = _register(client, email="other@test.local")
        assert resp.status_code == 409
        assert "username" in resp.get_json()["errors"]

    def test_invalid_input(self, client):
        resp = _register(client, email="not-an-email", username="a", role="superuser")
        body = resp.get_json()
        assert resp.status_code == 400
        assert set(body["errors"]) >= {"email", "username", "role"}

    def test_weak_password_rejected(self, client):
        resp = _register(client, password="short")
        assert resp.status_code == 400
        assert "password" in resp.get_json()["errors"]

    def test_non_json_body(self, client):
        resp = client.post("/api/auth/register", data="not json", content_type="text/plain")
        assert resp.status_code == 400
        assert resp.get_json()["success"] is False


class TestLogin:
    def test_valid_login_returns_tokens(self, client, users):
        resp = client.post("/api/auth/login", json={"username": "operator", "password": PASSWORD})
        data = resp.get_json()["data"]
        assert resp.status_code == 200
        assert data["access_token"] and data["refresh_token"]
        assert data["user"]["role"] == "control_room_operator"

    def test_login_with_email(self, client, users):
        resp = client.post("/api/auth/login", json={"email": "operator@test.local", "password": PASSWORD})
        assert resp.status_code == 200

    def test_invalid_password(self, client, users):
        resp = client.post("/api/auth/login", json={"username": "operator", "password": "wrong-pass1"})
        assert resp.status_code == 401
        assert resp.get_json()["message"] == "Invalid username or password"

    def test_unknown_user(self, client, users):
        resp = client.post("/api/auth/login", json={"username": "ghost", "password": PASSWORD})
        assert resp.status_code == 401

    def test_missing_fields(self, client):
        resp = client.post("/api/auth/login", json={})
        assert resp.status_code == 400
        assert set(resp.get_json()["errors"]) == {"username", "password"}

    def test_deactivated_user_cannot_login(self, client, users, headers):
        client.delete(f"/api/users/{users['operator'].id}", headers=headers("admin"))
        resp = client.post("/api/auth/login", json={"username": "operator", "password": PASSWORD})
        assert resp.status_code == 403


class TestJwt:
    def test_profile_requires_token(self, client):
        resp = client.get("/api/auth/profile")
        assert resp.status_code == 401
        assert resp.get_json()["message"] == "Authorization token is missing"

    def test_profile_with_token(self, client, headers):
        resp = client.get("/api/auth/profile", headers=headers("coordinator"))
        assert resp.status_code == 200
        assert resp.get_json()["data"]["username"] == "coordinator"

    def test_invalid_token(self, client):
        resp = client.get("/api/auth/profile", headers={"Authorization": "Bearer not.a.token"})
        assert resp.status_code == 401

    def test_expired_token(self, client, users, app):
        token = create_access_token(identity=users["operator"], expires_delta=timedelta(seconds=-1))
        resp = client.get("/api/auth/profile", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401
        assert "expired" in resp.get_json()["message"]

    def test_logout_revokes_token(self, client):
        client.post("/api/auth/register", json={"username": "temp", "email": "t@test.local", "full_name": "Temp",
                                                "password": "Secure123"})
        token = client.post("/api/auth/login", json={"username": "temp", "password": "Secure123"}).get_json()[
            "data"]["access_token"]
        auth = {"Authorization": f"Bearer {token}"}
        assert client.post("/api/auth/logout", headers=auth).status_code == 200
        resp = client.get("/api/auth/profile", headers=auth)
        assert resp.status_code == 401
        assert "revoked" in resp.get_json()["message"]

    def test_refresh_token(self, client, users):
        tokens = client.post("/api/auth/login", json={"username": "lead", "password": PASSWORD}).get_json()["data"]
        resp = client.post("/api/auth/refresh", headers={"Authorization": f"Bearer {tokens['refresh_token']}"})
        assert resp.status_code == 200
        assert resp.get_json()["data"]["access_token"]

    def test_access_token_cannot_refresh(self, client, headers):
        resp = client.post("/api/auth/refresh", headers=headers("lead"))
        assert resp.status_code == 401

    def test_deactivated_user_token_rejected(self, client, users, headers):
        client.delete(f"/api/users/{users['coordinator'].id}", headers=headers("admin"))
        resp = client.get("/api/auth/profile", headers=headers("coordinator"))
        assert resp.status_code == 401

    def test_role_change_takes_effect_immediately(self, client, users, headers):
        assert client.get("/api/users", headers=headers("operator")).status_code == 403
        client.put(f"/api/users/{users['operator'].id}", json={"role": "admin"}, headers=headers("admin"))
        assert client.get("/api/users", headers=headers("operator")).status_code == 200


class TestProfile:
    def test_update_profile(self, client, headers):
        resp = client.put("/api/auth/profile", json={"full_name": "Updated Name"}, headers=headers("lead"))
        assert resp.status_code == 200
        assert resp.get_json()["data"]["full_name"] == "Updated Name"

    def test_change_password_requires_current(self, client, headers):
        resp = client.put("/api/auth/profile", json={"password": "NewPass123"}, headers=headers("lead"))
        assert resp.status_code == 400
        resp = client.put("/api/auth/profile", json={"password": "NewPass123", "current_password": PASSWORD},
                          headers=headers("lead"))
        assert resp.status_code == 200
        assert client.post("/api/auth/login", json={"username": "lead", "password": "NewPass123"}).status_code == 200
