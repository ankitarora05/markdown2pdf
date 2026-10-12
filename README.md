# markdown2pdf — Markdown to PDF Converter

Convert Markdown to polished PDF documents with a responsive editor, live sanitized preview, and one-click downloads. markdown2pdf is built with FastAPI and [`markdown-pdf`](https://pypi.org/project/markdown-pdf/), and deploys on Railway using Docker.

## Features

- Live Markdown preview with server-side parsing and HTML sanitization
- 16 PDF themes: Paper, GitHub, Midnight, Academic, Minimal, Nord, Solarized, Warm, Dracula, Monokai, Ocean, Forest, Rose, Sepia, High Contrast, and Corporate
- Theme files discovered automatically from `themes/*.css`
- Browser-local draft saving; document content is not stored on the server
- Keyboard shortcut: **⌘ Enter** on macOS or **Ctrl Enter** elsewhere
- Health endpoint for Railway and container health checks
- Request-size validation and security response headers
- Search-ready metadata, JSON-LD structured data, `robots.txt`, and XML sitemap

## Run locally

Requires Python 3.11 or newer and pip.

1. Create and activate a virtual environment.
2. Install the app and test dependencies: `pip install -r requirements-dev.txt`
3. Start the server: `uvicorn app.main:app --reload`
4. Open `http://127.0.0.1:8000`.

For a production-like local run, use `uvicorn app.main:app --host 0.0.0.0 --port 8000`.

## Verify

Run `pytest`. The tests check health and UI routes, automatic theme discovery, preview sanitization, request validation, and that conversion returns PDF bytes.

## Docker

Build and start the container with Docker Compose not required:

- `docker build -t markdown2pdf .`
- `docker run --rm -p 8000:8000 -e PORT=8000 markdown2pdf`

Then visit `http://127.0.0.1:8000` or check `http://127.0.0.1:8000/health`.

## Deploy to Railway

1. Push this project to a GitHub repository.
2. Create a Railway project from that repository.
3. Railway uses `railway.json` and the root `Dockerfile`; it supplies the `PORT` environment variable automatically.
4. Wait for the `/health` health check to pass, then open the generated public domain.

No extra Railway port setting is needed.

### Search engine setup

The homepage includes a canonical URL, Open Graph and X/Twitter metadata, WebSite/WebApplication/FAQPage JSON-LD, and a crawlable, server-rendered product explanation. `/robots.txt` links search crawlers to `/sitemap.xml`; the sitemap lists the canonical homepage only.

After assigning the production domain, set `PUBLIC_SITE_URL` to its HTTPS origin (for example, `https://your-domain.example`) in Railway. If unset, the app derives the origin from the incoming request. Then verify the canonical URL, sitemap, and robots file on the live domain; add the domain to Google Search Console and Bing Webmaster Tools and submit the sitemap. Use real usage data to improve the page and performance over time. SEO metadata cannot guarantee rankings or outrank established competitors; rankings depend on the domain, product quality, competition, links, and user experience.

## Project layout

- `app/main.py` — FastAPI routes, preview sanitization, and PDF generation
- `app/static/` — browser editor, styling, and client-side interactions
- `themes/` — PDF stylesheet themes
- `tests/` — API and end-to-end conversion smoke tests
- `Dockerfile`, `railway.json` — container build and Railway deployment configuration

## Add a PDF theme

Add a CSS file under `themes/`; the server discovers added or edited theme files automatically and applies it to exported PDFs. Theme names come from filenames. For a custom live preview and a human-readable label, add the matching preview rules in `app/static/app.css` and display name in `app/static/app.js`. The bundled picker offers 16 curated styles, and this file-based design supports adding more.

## Limits and privacy

Markdown requests are limited to 250,000 characters. Conversion is performed in memory and content is not persisted by the application. As with any internet-facing upload/conversion endpoint, deploy behind appropriate platform limits and monitor resource use if you expect untrusted, high-volume traffic.

For safety in a public conversion service, PDF exports reject Markdown image references so an uploaded document cannot make the renderer read arbitrary local files. Images remain unsupported in exported PDFs.
