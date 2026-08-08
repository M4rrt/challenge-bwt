# frontend

React SPA (Vite + TypeScript) for chat-app.

## Stack

- Vite + React + TypeScript
- TanStack Query for server state
- React Router for routing (active conversation lives in the URL, no global store)

See `docs/decisions.md` in the repo root for the reasoning behind these choices.

## Running locally

1. Copy the env file and adjust if needed: `cp .env.example .env`
2. Install dependencies: `npm install`
3. Run the dev server: `npm run dev`

The dev server runs at `http://localhost:5173`.

## Environment variables

- `VITE_API_URL` — base URL of the backend API.
- `VITE_WEBHOOK_TEST_SECRET` — must match the backend's `WEBHOOK_HMAC_SECRET` for the `/webhook` test page (see `docs/adr/0005-client-side-hmac-webhook-test-page.md` in the repo root) to sign requests correctly. Test-page-only: this secret ships in the frontend bundle, so never set it to a real production secret. Do not commit a real value here — `.env` is gitignored.

## Build

```bash
npm run build
```

Type-checks with `tsc -b` and outputs a production bundle to `dist/`.

## Tests

```bash
npm run test
```

Runs the Vitest + React Testing Library suite.
