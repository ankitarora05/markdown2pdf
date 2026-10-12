# Project guidance

- Keep the FastAPI app and static UI self-contained; serve browser assets from `app/static/`.
- Keep PDF themes in `themes/`; backend theme discovery is automatic.
- Validate user input and sanitize preview HTML; never trust Markdown-rendered HTML directly.
- Run `pytest` after changing API or conversion behavior.
- Use the Dockerfile and `railway.json` as the deployment source of truth.
