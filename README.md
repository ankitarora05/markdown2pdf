---
title: markdown2pdf - Markdown to PDF Converter
emoji: 📄
colorFrom: purple
colorTo: blue
sdk: docker
app_port: 7860
short_description: Convert Markdown to beautiful PDFs with 16 themes.
---

# markdown2pdf — Markdown to PDF Converter

Convert Markdown to polished PDF documents with a responsive editor, live sanitized preview, and one-click downloads. markdown2pdf is built with FastAPI and [`markdown-pdf`](https://pypi.org/project/markdown-pdf/) and deploys as a Docker Space on Hugging Face.

## Features

- Live Markdown preview with server-side parsing and HTML sanitization
- 16 PDF themes: Paper, GitHub, Midnight, Academic, Minimal, Nord, Solarized, Warm, Dracula, Monokai, Ocean, Forest, Rose, Sepia, High Contrast, and Corporate
- Falls back to a readable plain PDF if the selected theme renderer fails
- Theme files discovered automatically from `themes/*.css`
- Browser-local draft saving; document content is not stored on the server
- Keyboard shortcut: **⌘ Enter** on macOS or **Ctrl Enter** elsewhere
- Health endpoint and container health checks
- Request-size validation and security response headers
- Search-ready metadata, JSON-LD structured data, `robots.txt`, and XML sitemap

## Run locally

Requires Python 3.11 or newer and pip.

1. Create and activate a virtual environment.
2. Install the app and test dependencies: `pip install -r requirements-dev.txt`
3. Start the server: `uvicorn app.main:app --reload --port 7860`
4. Open `http://127.0.0.1:7860`.

For a production-like local run, use `uvicorn app.main:app --host 0.0.0.0 --port 7860`.

## Verify

Run `pytest`. The tests check health and UI routes, automatic theme discovery, preview sanitization, request validation, and that conversion returns PDF bytes.

## Docker

Build and start the container with Docker Compose not required:

- `docker build -t markdown2pdf .`
- `docker run --rm -p 7860:7860 -e PORT=7860 markdown2pdf`

Then visit `http://127.0.0.1:7860` or check `http://127.0.0.1:7860/health`.

## Deploy to Hugging Face Spaces

### One-time setup

1. Create a **Docker** Space on Hugging Face. Its Space ID should be `ankitarora-05/markdown2pdf` to match the Space you provided.
2. Create a Hugging Face access token with **write** permission for that Space.
3. In GitHub, open **Settings → Secrets and variables → Actions**. Add the newly created token as the `HF_TOKEN` secret and set the `HF_SPACE_ID` variable to `ankitarora-05/markdown2pdf`.
4. In GitHub **Actions**, run **Deploy to Hugging Face Spaces** once using **Run workflow**. Later pushes to `main` run tests and then sync the repository to the Space.
5. Hugging Face builds the Space from the Dockerfile and README metadata (`sdk: docker`, `app_port: 7860`). When the build finishes, the app is available at `https://<your-username>-<space-name>.hf.space` (check the Space page for its exact URL).

To use a custom domain, configure it in the Space settings if available for your account and plan, then set the `PUBLIC_SITE_URL` Space variable to the final HTTPS origin. The default Hugging Face Space URL works without this variable.

Keep the access token in GitHub Secrets; never commit it. The Docker image can also be deployed to other container hosts using their provider-specific workflow.

### Search engine setup

The homepage includes a canonical URL, Open Graph and X/Twitter metadata, WebSite/WebApplication/FAQPage JSON-LD, and a crawlable, server-rendered product explanation. `/robots.txt` links search crawlers to `/sitemap.xml`; the sitemap lists the canonical homepage only.

After the Space is public, optionally set `PUBLIC_SITE_URL` to its public HTTPS origin. If unset, the app derives the origin from the incoming request. Verify the canonical URL, sitemap, and robots file on the live Space; add the site to Google Search Console and Bing Webmaster Tools and submit the sitemap. Use real usage data to improve the page and performance over time. SEO metadata cannot guarantee rankings; rankings depend on the domain, product quality, competition, links, and user experience.

## Project layout

- `app/main.py` — FastAPI routes, preview sanitization, and PDF generation
- `app/static/` — browser editor, styling, and client-side interactions
- `themes/` — PDF stylesheet themes
- `tests/` — API and end-to-end conversion smoke tests
- `Dockerfile`, `.github/workflows/deploy-huggingface.yml` — container and automated Space deployment

## Add a PDF theme

Add a CSS file under `themes/`; the server discovers added or edited theme files automatically and applies it to exported PDFs. Theme names come from filenames. For a custom live preview and a human-readable label, add the matching preview rules in `app/static/app.css` and display name in `app/static/app.js`. The bundled picker offers 16 curated styles, and this file-based design supports adding more.

## Limits and privacy

Markdown requests are limited to 250,000 characters. Conversion is performed in memory and content is not persisted by the application. As with any internet-facing upload/conversion endpoint, deploy behind appropriate platform limits and monitor resource use if you expect untrusted, high-volume traffic.

For safety in a public conversion service, PDF exports reject Markdown image references so an uploaded document cannot make the renderer read arbitrary local files. Images remain unsupported in exported PDFs.
