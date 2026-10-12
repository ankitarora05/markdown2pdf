# Project guidance

- Keep the FastAPI app and static UI self-contained; serve browser assets from `app/static/`.
- Keep PDF themes in `themes/`; backend theme discovery is automatic.
- Validate user input and sanitize preview HTML; never trust Markdown-rendered HTML directly.
- Run `pytest` after changing API or conversion behavior.
- Deploy the Docker app to Hugging Face Spaces; keep the README Space metadata and Docker `PORT` at 7860.
