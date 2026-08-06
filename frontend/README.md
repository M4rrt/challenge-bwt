# frontend

React SPA (Vite + TypeScript) for chat-app.

## Stack

- Vite + React + TypeScript
- TanStack Query for server state
- React Router for routing (active conversation lives in the URL, no global store)

See `docs/decisions.md` in the repo root for the reasoning behind these choices.

## Running locally

```bash
npm install
npm run dev
```

The dev server runs at `http://localhost:5173`.

## Build

```bash
npm run build
```

Type-checks with `tsc -b` and outputs a production bundle to `dist/`.
