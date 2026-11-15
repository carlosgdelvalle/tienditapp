"""v2 App Links: invite HTML page and Android assetlinks.json."""

from __future__ import annotations

from server.tests.conftest import employee_headers


def test_invite_page_offers_the_deep_link_and_redirects(client):
    created = client.post(
        "/api/employees/invites",
        headers=employee_headers(1),
        json={"name": "Beto"},
    ).json()
    token = created["token"]

    page = client.get(f"/invite/{token}")
    assert page.status_code == 200
    assert page.headers["content-type"].startswith("text/html")
    assert token in page.text
    assert "abarpay://empleado/" + token in page.text
    assert "Abarpay" in page.text
    # Minimal redirect straight to the app.
    assert "window.location.href" in page.text


def test_assetlinks_json_matches_the_android_app(client):
    response = client.get("/.well-known/assetlinks.json")
    assert response.status_code == 200
    assert response.json() == [
        {
            "relation": ["delegate_permission/common.handle_all_urls"],
            "target": {
                "namespace": "android_app",
                "package_name": "mx.abarpay.mobile",
                "sha256_cert_fingerprints": [
                    "f5219d47c4ac345bb4671d546653038a9ca949018ec47e713d2a6f06a4482618"
                ],
            },
        }
    ]
