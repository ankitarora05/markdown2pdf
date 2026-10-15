from __future__ import annotations

import asyncio
import html
import io
import json
import logging
import os
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit, urlunsplit

import bleach
import pymupdf
from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from markdown_it import MarkdownIt
from markdown_pdf import MarkdownPdf, Section
from pydantic import BaseModel, ConfigDict, Field
from app.auth import User, require_current_user, router as auth_router

logger = logging.getLogger(__name__)
ROOT_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = Path(__file__).resolve().parent / "static"
THEMES_DIR = ROOT_DIR / "themes"
MAX_MARKDOWN_LENGTH = 250_000
PDF_PAGE_BACKGROUNDS = {
    "dark": "171a21",
    "dracula": "282a36",
    "monokai": "272822",
    "ocean": "edf8fc",
    "forest": "f0f7f0",
    "rose": "fff4f7",
    "nord": "eceff4",
    "solarized": "fdf6e3",
    "sepia": "f5ead5",
    "warm": "fff8ed",
    "corporate": "f1f5f9",
}

ALLOWED_TAGS = set(bleach.sanitizer.ALLOWED_TAGS).union(
    {
        "p", "h1", "h2", "h3", "h4", "h5", "h6", "br", "hr", "pre",
        "code", "blockquote", "ul", "ol", "li", "table", "thead", "tbody",
        "tr", "th", "td", "del", "img",
    }
)
ALLOWED_ATTRIBUTES = {
    "a": ["href", "title"],
    "img": ["src", "alt", "title"],
    "th": ["align"],
    "td": ["align"],
}


def load_themes() -> dict[str, str]:
    return {
        css_file.stem: css_file.read_text(encoding="utf-8")
        for css_file in THEMES_DIR.glob("*.css")
    }


def theme_files_signature() -> tuple[tuple[str, int, int], ...]:
    return tuple(
        (css_file.name, css_file.stat().st_mtime_ns, css_file.stat().st_size)
        for css_file in sorted(THEMES_DIR.glob("*.css"))
    )


THEMES = load_themes()
THEME_SIGNATURE = theme_files_signature()
markdown_renderer = MarkdownIt("commonmark", {"html": False}).enable("table")


def get_themes() -> dict[str, str]:
    global THEMES, THEME_SIGNATURE
    signature = theme_files_signature()
    if signature != THEME_SIGNATURE:
        THEMES = load_themes()
        THEME_SIGNATURE = signature
    return THEMES


def add_copyright_footer(pdf_bytes: bytes) -> bytes:
    document = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    footer_text = "markdown2pdf © Markdown to PDF Converter"
    for page in document:
        footer_rect = pymupdf.Rect(
            36,
            page.rect.height - 28,
            page.rect.width - 36,
            page.rect.height - 10,
        )
        page.insert_textbox(
            footer_rect,
            footer_text,
            fontname="helv",
            fontsize=8,
            color=(0.48, 0.50, 0.54),
            align=pymupdf.TEXT_ALIGN_CENTER,
            overlay=True,
        )
    return document.tobytes(garbage=4, deflate=True)


class PreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    markdown: Annotated[str, Field(max_length=MAX_MARKDOWN_LENGTH)]


app = FastAPI(
    title="markdown2pdf © Markdown to PDF Converter",
    version="1.0.0",
    description="Convert Markdown to polished PDF documents with live preview and selectable themes.",
    docs_url=None,
    redoc_url=None,
)
app.include_router(auth_router)


@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; img-src 'self' data: https:; style-src 'self'; "
        "script-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; "
        "frame-ancestors 'none'",
    )
    return response


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/google4d282da7d3423ef3.html", include_in_schema=False)
async def google_search_console_verification() -> FileResponse:
    verification_file = ROOT_DIR / "google4d282da7d3423ef3.html"
    return FileResponse(verification_file, media_type="text/html")

@app.get("/7aede77d8fe54188b41db7c7991a01e7.txt", include_in_schema=False)
async def indexnow_verification() -> FileResponse:
    verification_file = ROOT_DIR / "7aede77d8fe54188b41db7c7991a01e7.txt"
    return FileResponse(verification_file, media_type="text/html")


def get_site_url(request: Request) -> str:
    configured_url = os.getenv("PUBLIC_SITE_URL", "").strip()
    candidate = configured_url or str(request.base_url)
    parsed = urlsplit(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        candidate = str(request.base_url)
        parsed = urlsplit(candidate)
    return urlunsplit((parsed.scheme, parsed.netloc, "", "", "")).rstrip("/")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    index_path = STATIC_DIR / "index.html"
    site_url = get_site_url(request)
    document = index_path.read_text(encoding="utf-8")
    document = document.replace("{{CANONICAL_URL}}", html.escape(f"{site_url}/", quote=True))
    safe_site_url_json = (
        json.dumps(site_url)[1:-1]
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )
    document = document.replace("{{SITE_URL_JSON}}", safe_site_url_json)
    return HTMLResponse(document)


@app.get("/terms-of-service", include_in_schema=False)
async def terms_of_service() -> FileResponse:
    return FileResponse(STATIC_DIR / "terms.html", media_type="text/html")


@app.get("/privacy-policy", include_in_schema=False)
async def privacy_policy() -> FileResponse:
    return FileResponse(STATIC_DIR / "privacy.html", media_type="text/html")


@app.get("/cookie-policy", include_in_schema=False)
async def cookie_policy() -> FileResponse:
    return FileResponse(STATIC_DIR / "cookies.html", media_type="text/html")


@app.get("/robots.txt", include_in_schema=False)
async def robots(request: Request) -> Response:
    site_url = get_site_url(request)
    body = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /api/\n"
        "Disallow: /health\n"
        f"Sitemap: {site_url}/sitemap.xml\n"
    )
    return Response(body, media_type="text/plain; charset=utf-8")


@app.get("/sitemap.xml", include_in_schema=False)
async def sitemap(request: Request) -> Response:
    site_url = get_site_url(request)
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"<url><loc>{html.escape(site_url, quote=True)}/</loc>"
        "<changefreq>weekly</changefreq><priority>1.0</priority></url>"
        f"<url><loc>{html.escape(site_url, quote=True)}/terms-of-service</loc></url>"
        f"<url><loc>{html.escape(site_url, quote=True)}/privacy-policy</loc></url>"
        f"<url><loc>{html.escape(site_url, quote=True)}/cookie-policy</loc></url>"
        "</urlset>"
    )
    return Response(body, media_type="application/xml; charset=utf-8")


@app.get("/api/themes")
async def list_themes() -> dict[str, list[dict[str, str]]]:
    themes = get_themes()
    return {
        "themes": [
            {"id": name, "label": name.replace("-", " ").title()}
            for name in sorted(themes)
        ]
    }


@app.post("/api/preview")
async def preview(req: PreviewRequest) -> dict[str, str]:
    rendered = markdown_renderer.render(req.markdown)
    safe_html = bleach.clean(
        rendered,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols={"http", "https", "mailto"},
        strip=True,
    )
    return {"html": safe_html}


def render_pdf(markdown: str, theme: str) -> bytes:
    themes = get_themes()
    if theme not in themes:
        raise ValueError("Unknown PDF theme")
    pdf = MarkdownPdf(toc_level=2, optimize=True)
    pdf.meta["title"] = "markdown2pdf document"
    pdf.add_section(Section(markdown), user_css=themes[theme])
    if pdf.toc and pdf.toc[0][0] > 1:
        # PyMuPDF requires the first outline entry to be level 1. Documents
        # that start with `##` otherwise fail during save and lose their theme.
        level_offset = pdf.toc[0][0] - 1
        pdf.toc[:] = [
            (max(1, entry[0] - level_offset), *entry[1:])
            for entry in pdf.toc
        ]
    output = io.BytesIO()
    pdf.save_bytes(output)
    pdf_bytes = output.getvalue()
    background_color = PDF_PAGE_BACKGROUNDS.get(theme)
    if background_color is None:
        return add_copyright_footer(pdf_bytes)

    document = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    page_background = tuple(
        int(background_color[index : index + 2], 16) / 255
        for index in (0, 2, 4)
    )
    for page in document:
        page.draw_rect(page.rect, color=None, fill=page_background, overlay=False)
    return add_copyright_footer(document.tobytes(garbage=4, deflate=True))


def render_pdf_fallback(markdown: str) -> bytes:
    """Render a plain PDF without custom CSS or a table of contents."""
    pdf = MarkdownPdf(toc_level=0, optimize=False)
    pdf.meta["title"] = "markdown2pdf document"
    pdf.add_section(Section(markdown))
    output = io.BytesIO()
    pdf.save_bytes(output)
    return add_copyright_footer(output.getvalue())


@app.post("/convert")
async def convert(
    markdown: Annotated[str, Form(min_length=1, max_length=MAX_MARKDOWN_LENGTH)],
    theme: Annotated[str, Form(max_length=64)] = "default",
    _user: User = Depends(require_current_user),
) -> StreamingResponse:
    if not markdown.strip():
        raise HTTPException(status_code=422, detail="Markdown content is empty")
    themes = get_themes()
    if theme not in themes:
        raise HTTPException(status_code=422, detail="Unknown PDF theme")
    if any(
        child.type == "image"
        for token in markdown_renderer.parse(markdown)
        if token.type == "inline" and token.children
        for child in token.children
    ):
        raise HTTPException(
            status_code=422,
            detail="Image references are not supported in PDF exports",
        )

    used_fallback = False
    try:
        pdf_bytes = await asyncio.to_thread(render_pdf, markdown, theme)
    except Exception:
        logger.exception(
            "Themed PDF generation failed; retrying without theme CSS or TOC "
            "(theme=%s, markdown_chars=%d)",
            theme,
            len(markdown),
        )
        try:
            pdf_bytes = await asyncio.to_thread(render_pdf_fallback, markdown)
            used_fallback = True
        except Exception as fallback_error:
            logger.exception(
                "Plain PDF fallback failed (theme=%s, markdown_chars=%d)",
                theme,
                len(markdown),
            )
            raise HTTPException(
                status_code=500,
                detail=f"PDF generation failed ({type(fallback_error).__name__})",
            ) from None

    headers = {
        "Content-Disposition": 'attachment; filename="markdown2pdf-document.pdf"',
        "Content-Length": str(len(pdf_bytes)),
        "Cache-Control": "no-store",
    }
    if used_fallback:
        headers["X-PDF-Theme-Fallback"] = "plain"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers=headers,
    )


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
