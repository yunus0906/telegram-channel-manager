# Telegram Channel Manager

- Keep the FastAPI API under `/api/v1` and use string Telegram IDs on the wire.
- Run database changes through Alembic migrations. Store timestamps in UTC.
- Keep one Telethon client per backend process. Do not put Telegram calls in request handlers when they can be long-running.
- Never log login codes, passwords, API hashes, session files, or private message bodies.
- Frontend code uses Vue 3 Composition API and strict TypeScript.
- Run the backend and frontend checks described in README before claiming a change is complete.

