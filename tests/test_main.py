import json
import re

import pymupdf
from fastapi.testclient import TestClient

from app.main import app, render_pdf


client = TestClient(app)


def test_health_check() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_google_search_console_verification_file_is_served_at_site_root() -> None:
    response = client.get("/google4d282da7d3423ef3.html")
    assert response.status_code == 200
    assert response.text.strip() == (
        "google-site-verification: google4d282da7d3423ef3.html"
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
    response = client.post("/convert", data={"markdown": "  \n  "})
    assert response.status_code == 422


def test_conversion_uses_posted_html_form_not_json_api() -> None:
    assert client.get("/convert").status_code == 405
    assert client.post("/api/convert", json={"markdown": "# Test"}).status_code == 404


def test_pdf_export_rejects_image_references() -> None:
    response = client.post(
        "/convert",
        data={"markdown": "![private file](/etc/passwd)"},
    )
    assert response.status_code == 422


def test_conversion_returns_pdf() -> None:
    response = client.post(
        "/convert",
        data={"markdown": "# PDF test\n\nThis is a test.", "theme": "github"},
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
