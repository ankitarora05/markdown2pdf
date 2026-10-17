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

> **Live demo:** [Try markdown2pdf](https://markdown2pdf-5am3.onrender.com/)

Convert Markdown to polished PDF documents with a responsive editor, live sanitized preview, and one-click downloads. markdown2pdf is built with FastAPI and [`markdown-pdf`](https://pypi.org/project/markdown-pdf/) and deploys as a Docker Space on Hugging Face.

## Features

- Live Markdown preview with server-side parsing and HTML sanitization
- PDF export through a same-site authenticated POST, returning the PDF as a download rather than a JSON API response
- Signup with username, email, first and last name; email confirmation is not required
- Case-insensitive unique usernames and email addresses, Argon2 password hashing, strong-password validation, and accepted-terms tracking
- PDF export requires an account and a current login; access JWTs are short-lived and HttpOnly refresh tokens rotate automatically for up to 30 days
- Email-based, single-use password reset links
- Public, versioned Terms of Service, Privacy Policy, and Cookie Policy pages; signup links open each policy in a new tab
- First-visit cookie-choice panel with an essential-only path; optional analytics/advertising choices are recorded separately from agreeing to the Terms
- 16 PDF themes: Paper, GitHub, Midnight, Academic, Minimal, Nord, Solarized, Warm, Dracula, Monokai, Ocean, Forest, Rose, Sepia, High Contrast, and Corporate
- Falls back to a readable plain PDF if the selected theme renderer fails
- Theme files discovered automatically from `themes/*.css`
- Browser-local draft saving; document content is not stored on the server
- Keyboard shortcut: **⌘ Enter** on macOS or **Ctrl Enter** elsewhere
- Health endpoint and container health checks
- Request-size validation and security response headers
- Search-ready metadata, JSON-LD structured data, `robots.txt`, and XML sitemap

## Run locally

Requires Python 3.11 or newer and Docker Desktop for Mac (which includes Docker Compose). Install Docker Desktop from [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/) and launch it. A separate PostgreSQL installer is not needed: Compose downloads and runs PostgreSQL 18 or newer in a container.

From the repository root, create a Python environment, install dependencies, and start the database and app:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
sh scripts/start-local.sh
```

When Uvicorn reports that it is running, open `http://127.0.0.1:8000`. Stop the app with **Ctrl+C**. The PostgreSQL container remains running; stop it separately with `docker compose stop postgres`.

The script starts PostgreSQL with Docker Compose, waits for its health check, and connects the app to `127.0.0.1:5433` (mapped to PostgreSQL's container port `5432`). The local app listens on port `8000`. The development database is `markdown2pdf`, with local-only username/password `markdown2pdf` / `markdown2pdf_local`; do not use these credentials in a deployed environment. Data persists in the `local_postgres_data` Docker volume. Stop the database with `docker compose stop postgres`; restart it by running the startup script again. To remove the database and permanently delete its local data, run `docker compose down --volumes`. Without `DATABASE_URL`, a direct `uvicorn` run uses the SQLite database at `data/auth.sqlite3` (ignored by Git).

In production, set `DATABASE_URL` to the connection URL provided by your managed PostgreSQL service, for example `postgresql+psycopg://user:password@host:5432/database`. The deployed app listens on the platform-provided `PORT` (7860 on Hugging Face Spaces); PostgreSQL runs separately and its host/port come from that connection URL. Set a persistent, random `JWT_SECRET` in every deployed environment; otherwise sessions are invalidated whenever the process restarts. Refresh cookies are HttpOnly and Secure in the production Docker image.

Configure `SMTP_HOST`, `SMTP_PORT` (default `587`), `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`, and optionally `SMTP_USE_TLS` for password-reset email delivery. Signup itself does not require email confirmation. The reset endpoint intentionally returns the same message whether or not the email belongs to an account.

For a production-like local app port, use `uvicorn app.main:app --host 0.0.0.0 --port 7860`.

## Verify

Run `pytest`. The tests check health and UI routes, authentication and refresh-token rotation, password recovery, automatic theme discovery, preview sanitization, request validation, and authenticated PDF conversion.

## Docker

Build and start the production app container (Docker Compose is not required):

- `docker build -t markdown2pdf .`
- `docker run --rm -p 7860:7860 -e PORT=7860 markdown2pdf`

Then visit `http://127.0.0.1:7860` or check `http://127.0.0.1:7860/health`.

## Deploy to Hugging Face Spaces

### One-time setup

1. Create a **Docker** Space on Hugging Face. Its Space ID should be `ankitarora-05/markdown2pdf` to match the Space you provided.
2. Create a Hugging Face access token with **write** permission for that Space.
3. In GitHub, open **Settings → Secrets and variables → Actions**. Add the newly created token as the `HF_TOKEN` secret and set the `HF_SPACE_ID` variable to `ankitarora-05/markdown2pdf`.
4. In the Space settings, add `DATABASE_URL` for a persistent PostgreSQL database and a strong, stable `JWT_SECRET`. Add `SMTP_HOST`, `SMTP_FROM`, and the provider credentials if password-reset email is required. The container's local SQLite fallback is not a durable production database.
5. In GitHub **Actions**, run **Deploy to Hugging Face Spaces** once using **Run workflow**. Later pushes to `main` run tests and then sync the repository to the Space.
6. Hugging Face builds the Space from the Dockerfile and README metadata (`sdk: docker`, `app_port: 7860`). When the build finishes, the app is available at `https://<your-username>-<space-name>.hf.space` (check the Space page for its exact URL).

To use a custom domain, configure it in the Space settings if available for your account and plan, then set the `PUBLIC_SITE_URL` Space variable to the final HTTPS origin. The default Hugging Face Space URL works without this variable.

Keep the access token in GitHub Secrets; never commit it. The Docker image can also be deployed to other container hosts using their provider-specific workflow.

### Search engine setup

The homepage includes a canonical URL, Open Graph and X/Twitter metadata, WebSite/WebApplication/FAQPage JSON-LD, and a crawlable, server-rendered product explanation. `/robots.txt` links search crawlers to `/sitemap.xml`; the sitemap lists the canonical homepage only.

After the Space is public, optionally set `PUBLIC_SITE_URL` to its public HTTPS origin. If unset, the app derives the origin from the incoming request. Verify the canonical URL, sitemap, and robots file on the live Space; add the site to Google Search Console and Bing Webmaster Tools and submit the sitemap. Use real usage data to improve the page and performance over time. SEO metadata cannot guarantee rankings; rankings depend on the domain, product quality, competition, links, and user experience.

## Project layout

- `app/main.py` — FastAPI routes, authenticated PDF export, preview sanitization, and PDF generation
- `app/auth.py` — PostgreSQL/SQLite account models, password hashing, JWT/refresh sessions, and password recovery
- `data/` — local SQLite account database (ignored by Git; configure `DATABASE_URL` for PostgreSQL)
- `app/static/` — browser editor, styling, and client-side interactions
- `themes/` — PDF stylesheet themes
- `tests/` — API and end-to-end conversion smoke tests
- `Dockerfile`, `.github/workflows/deploy-huggingface.yml` — container and automated Space deployment

## Add a PDF theme

Add a CSS file under `themes/`; the server discovers added or edited theme files automatically and applies it to exported PDFs. Theme names come from filenames. For a custom live preview and a human-readable label, add the matching preview rules in `app/static/app.css` and display name in `app/static/app.js`. The bundled picker offers 16 curated styles, and this file-based design supports adding more.

## Legal notices and cookie choices

The current policy drafts are available at `/terms-of-service`, `/privacy-policy`, and `/cookie-policy`, and are linked from the signup form and site footer. New accounts record the accepted Terms version and the Privacy/Cookie Policy acknowledgment timestamps. Cookie category choices are recorded separately; essential-only is a complete choice and does not enable optional tracking. The current application does not load analytics or advertising trackers. Keep policy text, database practices, hosting providers, and consent controls aligned whenever deployment or monetization changes.

These are general product-policy drafts, not legal advice or a certification of compliance. No single set of terms guarantees compliance worldwide. Before public commercial use, have qualified counsel review the actual operator identity/contact details, governing law, consumer rules, age requirements, privacy notices, international data transfers, tax, accessibility, advertising/affiliate disclosures, and local cookie-consent requirements for every target market. Add the correct legal entity/address and operational privacy-request channel if required.

## Limits and privacy

Markdown requests are limited to 250,000 characters. Conversion is performed in memory and document content is not persisted by the application. Live preview is public, but PDF export requires a valid signed-in account. Account records and password-reset/session metadata are persisted in the configured database. Deploy behind appropriate platform limits and add rate limiting for public authentication endpoints.

For safety in a public conversion service, PDF exports reject Markdown image references so an uploaded document cannot make the renderer read arbitrary local files. Images remain unsupported in exported PDFs.
