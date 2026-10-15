import json
import re
import secrets

import pymupdf
from fastapi.testclient import TestClient

from app.main import app, render_pdf


client = TestClient(app)
STRONG_PASSWORD = "Horizon!River8Lighthouse"


def signup_payload(username: str | None = None) -> dict[str, object]:
    chosen_username = username or f"reader{secrets.token_hex(5)}"
    return {
        "username": chosen_username,
        "email": f"{chosen_username}@example.com",
        "first_name": "Anya",
        "last_name": "Reader",
        "password": STRONG_PASSWORD,
        "accept_terms": True,
        "acknowledge_privacy": True,
        "acknowledge_cookies": True,
    }


def signed_in_headers() -> dict[str, str]:
    response = client.post("/api/auth/signup", json=signup_payload())
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_health_check() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_refresh_without_a_session_is_a_no_content_response() -> None:
    response = client.post("/api/auth/refresh")
    assert response.status_code == 204


def test_google_search_console_verification_file_is_served_at_site_root() -> None:
    response = client.get("/google4d282da7d3423ef3.html")
    assert response.status_code == 200
    assert response.text.strip() == (
        "google-site-verification: google4d282da7d3423ef3.html"
    )

def test_indexnow_verification_file_is_served_at_site_root() -> None:
    response = client.get("/7aede77d8fe54188b41db7c7991a01e7.txt")
    assert response.status_code == 200
    assert response.text.strip() == (
        "7aede77d8fe54188b41db7c7991a01e7"
    )


def test_index_is_served() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "Markdown to PDF" in response.text
    assert "markdown2pdf" in response.text
    assert "16 themes" in response.text
    assert '<form id="convertForm" action="/convert" method="post"></form>' in response.text
    assert 'name="markdown" form="convertForm"' in response.text
    assert 'name="theme" form="convertForm"' in response.text
    assert 'id="signupForm"' in response.text
    assert "Sign in or create a free account to export" in response.text
    assert 'href="/terms-of-service" target="_blank" rel="noopener noreferrer"' in response.text
    assert 'id="cookiePreferencesButton"' in response.text
    assert "Your privacy, your choice" in response.text
    for theme_id in (
        "default",
        "github",
        "dark",
        "academic",
        "minimal",
        "nord",
        "solarized",
        "warm",
        "dracula",
        "monokai",
        "ocean",
        "forest",
        "rose",
        "sepia",
        "contrast",
        "corporate",
    ):
        assert f'<option value="{theme_id}">' in response.text
    assert 'rel="canonical" href="http://testserver/"' in response.text
    assert "{{SITE_URL_JSON}}" not in response.text
    structured_data = re.search(
        r'<script type="application/ld\+json">(.*?)</script>',
        response.text,
        re.DOTALL,
    )
    assert structured_data is not None
    graph = json.loads(structured_data.group(1))["@graph"]
    assert {item["@type"] for item in graph} >= {
        "WebSite",
        "WebApplication",
        "FAQPage",
    }


def test_robots_and_sitemap_are_served() -> None:
    robots_response = client.get("/robots.txt")
    assert robots_response.status_code == 200
    assert "Sitemap: http://testserver/sitemap.xml" in robots_response.text
    sitemap_response = client.get("/sitemap.xml")
    assert sitemap_response.status_code == 200
    assert "http://testserver/" in sitemap_response.text


def test_public_site_url_sets_canonical_domain(monkeypatch) -> None:
    monkeypatch.setenv("PUBLIC_SITE_URL", "https://markdown2pdf.example/")
    response = client.get("/")
    assert 'rel="canonical" href="https://markdown2pdf.example/"' in response.text
    assert '"url": "https://markdown2pdf.example/"' in response.text


def test_legal_pages_are_readable_and_cross_linked() -> None:
    expected_sections = {
        "/terms-of-service": ("Terms of Service", "Acceptable use", "Ankit Arora"),
        "/privacy-policy": ("Privacy Policy", "International processing", "cookie"),
        "/cookie-policy": ("Cookie Policy", "Essential only", "No advertising or analytics cookies are active"),
    }
    for path, expected_phrases in expected_sections.items():
        response = client.get(path)
        assert response.status_code == 200
        assert 'rel="stylesheet" href="/static/legal.css' in response.text
        assert all(phrase.casefold() in response.text.casefold() for phrase in expected_phrases)
        assert "/terms-of-service" in response.text
        assert "/privacy-policy" in response.text
        assert "/cookie-policy" in response.text


def test_cookie_consent_records_essential_only_or_optional_categories() -> None:
    essential_response = client.post(
        "/api/auth/cookie-consent",
        json={"essential": True, "analytics": False, "advertising": False},
    )
    assert essential_response.status_code == 200
    assert essential_response.json()["essential"] is True
    assert essential_response.json()["analytics"] is False

    optional_response = client.post(
        "/api/auth/cookie-consent",
        json={"essential": True, "analytics": True, "advertising": True},
    )
    assert optional_response.status_code == 200
    assert optional_response.json()["advertising"] is True
    assert client.post(
        "/api/auth/cookie-consent",
        json={"essential": False, "analytics": True, "advertising": True},
    ).status_code == 422


def test_themes_are_discovered() -> None:
    response = client.get("/api/themes")
    assert response.status_code == 200
    assert {theme["id"] for theme in response.json()["themes"]} >= {
        "academic",
        "default",
        "dark",
        "dracula",
        "contrast",
        "corporate",
        "forest",
        "github",
        "minimal",
        "monokai",
        "nord",
        "ocean",
        "rose",
        "sepia",
        "solarized",
        "warm",
    }


def test_preview_renders_and_sanitizes_html() -> None:
    response = client.post(
        "/api/preview",
        json={"markdown": "# Hello\n\n<script>alert(1)</script>"},
    )
    assert response.status_code == 200
    assert "<h1>Hello</h1>" in response.json()["html"]
    assert "<script>" not in response.json()["html"]


def test_empty_markdown_is_rejected() -> None:
    response = client.post(
        "/convert",
        data={"markdown": "  \n  "},
        headers=signed_in_headers(),
    )
    assert response.status_code == 422


def test_conversion_uses_posted_html_form_not_json_api() -> None:
    assert client.get("/convert").status_code == 405
    assert client.post("/api/convert", json={"markdown": "# Test"}).status_code == 404


def test_pdf_export_rejects_image_references() -> None:
    response = client.post(
        "/convert",
        data={"markdown": "![private file](/etc/passwd)"},
        headers=signed_in_headers(),
    )
    assert response.status_code == 422


def test_conversion_returns_pdf() -> None:
    response = client.post(
        "/convert",
        data={"markdown": "# PDF test\n\nThis is a test.", "theme": "github"},
        headers=signed_in_headers(),
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "markdown2pdf-document.pdf" in response.headers["content-disposition"]
    assert response.content.startswith(b"%PDF-")


def test_generated_pdf_has_centered_footer_on_every_page() -> None:
    markdown = "\n\n".join(
        f"Paragraph {index}: This repeated content makes the generated document span several pages."
        for index in range(100)
    )
    document = pymupdf.open(
        stream=render_pdf(markdown, "default"),
        filetype="pdf",
    )
    assert len(document) > 1
    for page in document:
        footer_span = next(
            span
            for block in page.get_text("dict")["blocks"]
            if "lines" in block
            for line in block["lines"]
            for span in line["spans"]
            if span["text"] == "markdown2pdf © Markdown to PDF Converter"
        )
        footer_center = (footer_span["bbox"][0] + footer_span["bbox"][2]) / 2
        assert abs(footer_center - page.rect.width / 2) < 1


def test_pdf_with_h2_as_first_heading_keeps_selected_theme() -> None:
    response = client.post(
        "/convert",
        data={
            "markdown": "## First section\n\n### A subsection\n\nBody text.\n\n## Second section",
            "theme": "corporate",
        },
        headers=signed_in_headers(),
    )
    assert response.status_code == 200
    assert "x-pdf-theme-fallback" not in response.headers
    document = pymupdf.open(stream=response.content, filetype="pdf")
    assert document.get_toc()[0][:2] == [1, "First section"]
    first_heading = next(
        span
        for block in document[0].get_text("dict")["blocks"]
        if "lines" in block
        for line in block["lines"]
        for span in line["spans"]
        if span["text"] == "First section"
    )
    assert first_heading["color"] == 0x183653


def test_conversion_falls_back_when_selected_theme_renderer_fails(monkeypatch) -> None:
    def fail_themed_render(markdown: str, theme: str) -> bytes:
        raise RuntimeError("simulated theme renderer error")

    monkeypatch.setattr("app.main.render_pdf", fail_themed_render)
    response = client.post(
        "/convert",
        data={
            "markdown": "# Fallback PDF\n\nKeep this content in the generated file.",
            "theme": "minimal",
        },
        headers=signed_in_headers(),
    )
    assert response.status_code == 200
    assert response.headers["x-pdf-theme-fallback"] == "plain"
    assert response.content.startswith(b"%PDF-")
    document = pymupdf.open(stream=response.content, filetype="pdf")
    assert "Keep this content" in document[0].get_text()
    assert all("markdown2pdf © Markdown to PDF Converter" in page.get_text() for page in document)


def test_midnight_pdf_has_dark_page_background() -> None:
    document = pymupdf.open(
        stream=render_pdf("# Midnight\n\nDark theme test.", "dark"),
        filetype="pdf",
    )
    pixel = document[0].get_pixmap(alpha=False).samples[:3]
    assert tuple(pixel) == (23, 26, 33)


def test_light_color_themes_have_their_page_backgrounds() -> None:
    expected_backgrounds = {
        "dracula": (40, 42, 54),
        "monokai": (39, 40, 34),
        "ocean": (237, 248, 252),
        "forest": (240, 247, 240),
        "rose": (255, 244, 247),
        "nord": (236, 239, 244),
        "solarized": (253, 246, 227),
        "sepia": (245, 234, 213),
        "warm": (255, 248, 237),
        "corporate": (241, 245, 249),
    }
    for theme, expected_color in expected_backgrounds.items():
        document = pymupdf.open(
            stream=render_pdf("# Background", theme),
            filetype="pdf",
        )
        pixel = document[0].get_pixmap(alpha=False).samples[:3]
        assert tuple(pixel) == expected_color


def test_pdf_theme_styles_change_heading_colors() -> None:
    expected_colors = {
        "academic": 0x24211F,
        "contrast": 0x000000,
        "corporate": 0x183653,
        "default": 0x171A21,
        "dracula": 0xFF79C6,
        "forest": 0x234B36,
        "github": 0x1F2328,
        "dark": 0xF5F6FA,
        "minimal": 0x20252A,
        "monokai": 0xA6E22E,
        "nord": 0x2E3440,
        "ocean": 0x123C56,
        "rose": 0x713B54,
        "sepia": 0x4A3524,
        "solarized": 0x073642,
        "warm": 0x50382F,
    }
    for theme, expected_color in expected_colors.items():
        document = pymupdf.open(
            stream=render_pdf("# Theme check", theme),
            filetype="pdf",
        )
        heading = next(
            span
            for block in document[0].get_text("dict")["blocks"]
            if "lines" in block
            for line in block["lines"]
            for span in line["spans"]
            if span["text"] == "Theme check"
        )
        assert heading["color"] == expected_color


def test_footer_links_to_ankit_arora_linkedin() -> None:
    response = client.get("/")
    assert 'href="https://www.linkedin.com/in/ankit-arora-86a7b237/"' in response.text
    assert ">Ankit Arora</a>" in response.text


def test_pdf_export_requires_a_signed_in_user() -> None:
    response = client.post("/convert", data={"markdown": "# Private export"})
    assert response.status_code == 401


def test_signup_and_login_return_access_token_and_set_http_only_refresh_cookie() -> None:
    payload = signup_payload()
    signup_response = client.post("/api/auth/signup", json=payload)
    assert signup_response.status_code == 200
    assert signup_response.json()["user"]["username"] == payload["username"]
    assert signup_response.json()["token_type"] == "bearer"
    assert client.cookies.get("markdown2pdf_refresh")
    assert "httponly" in signup_response.headers["set-cookie"].lower()
    assert "password_hash" not in signup_response.text

    login_response = client.post(
        "/api/auth/login",
        json={"username": payload["username"].upper(), "password": STRONG_PASSWORD},
    )
    assert login_response.status_code == 200
    assert login_response.json()["access_token"]


def test_signup_rejects_duplicate_case_insensitive_username_and_weak_password() -> None:
    payload = signup_payload()
    assert client.post("/api/auth/signup", json=payload).status_code == 200
    duplicate = {**payload, "username": str(payload["username"]).upper(), "email": "another@example.com"}
    assert client.post("/api/auth/signup", json=duplicate).status_code == 409

    weak_password = {**signup_payload(), "password": "short"}
    assert client.post("/api/auth/signup", json=weak_password).status_code == 422
    username_in_password = {
        **signup_payload("SampleUser"),
        "password": "SampleUser!234567",
    }
    assert client.post("/api/auth/signup", json=username_in_password).status_code == 422
    terms_not_accepted = {**signup_payload(), "accept_terms": False}
    assert client.post("/api/auth/signup", json=terms_not_accepted).status_code == 422
    privacy_not_acknowledged = {**signup_payload(), "acknowledge_privacy": False}
    assert client.post("/api/auth/signup", json=privacy_not_acknowledged).status_code == 422


def test_refresh_token_is_rotated_and_replay_revokes_its_family() -> None:
    signup_response = client.post("/api/auth/signup", json=signup_payload())
    assert signup_response.status_code == 200
    original_cookie = client.cookies.get("markdown2pdf_refresh")
    assert original_cookie

    refresh_response = client.post("/api/auth/refresh")
    assert refresh_response.status_code == 200
    rotated_cookie = client.cookies.get("markdown2pdf_refresh")
    assert rotated_cookie and rotated_cookie != original_cookie

    client.cookies.set("markdown2pdf_refresh", original_cookie, path="/api/auth")
    replay_response = client.post("/api/auth/refresh")
    assert replay_response.status_code == 401


def test_password_reset_uses_email_link_and_invalidates_existing_sessions(monkeypatch) -> None:
    sent_messages = []

    class FakeSMTP:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def ehlo(self):
            return None

        def starttls(self):
            return None

        def login(self, *args):
            return None

        def send_message(self, message):
            sent_messages.append(message)

    monkeypatch.setattr("app.auth.smtplib.SMTP", FakeSMTP)
    monkeypatch.setenv("SMTP_HOST", "smtp.example.test")
    monkeypatch.setenv("SMTP_FROM", "accounts@example.test")
    monkeypatch.setenv("SMTP_USE_TLS", "false")
    payload = signup_payload()
    signup_response = client.post("/api/auth/signup", json=payload)
    assert signup_response.status_code == 200
    previous_access_token = signup_response.json()["access_token"]

    forgot_response = client.post(
        "/api/auth/forgot-password",
        json={"email": payload["email"]},
    )
    assert forgot_response.status_code == 200
    assert sent_messages
    reset_link = re.search(r"\?reset=([A-Za-z0-9_-]+)", sent_messages[0].get_content())
    assert reset_link is not None

    reset_response = client.post(
        "/api/auth/reset-password",
        json={"token": reset_link.group(1), "password": "New!Password8Riverbank"},
    )
    assert reset_response.status_code == 200
    assert client.post(
        "/convert",
        data={"markdown": "# Old access token"},
        headers={"Authorization": f"Bearer {previous_access_token}"},
    ).status_code == 401
    assert client.post(
        "/api/auth/login",
        json={"username": payload["username"], "password": "New!Password8Riverbank"},
    ).status_code == 200
