# 21 — Refactor frontend directory structure

**What to build:** Restructure `frontend/src` so routing, pages, and shared UI each live in a predictable place, and ownership of route-private code is visible on disk.

Rules:

- `routes/` is removed as a concept. The `<Routes>` tree is declared in `src/AppRoutes.tsx` — it only wires `path` → `element`, importing pages from `components/`. No component logic lives in a routing file. `App.tsx` keeps only the provider tree (Theme, QueryClient, Auth, `BrowserRouter`) and renders `<AppRoutes />`. (Revised during implementation — see Comments.)
- Every component/page gets its own folder named after it, with the file repeating the folder name (PascalCase): `components/Login/Login.tsx`, not `components/Login.tsx` or an `index.tsx`. No flat `.tsx` files directly inside `components/`.
- Colocate a component's test next to it in the same folder (`Login/Login.test.tsx`).
- A component/page used only by one other component nests inside that owner's folder (no intermediate `components/` subfolder — just directly inside, e.g. `ConversasLayout/Sidebar/Sidebar.tsx`). A component used by 2+ unrelated pages (`AuthLayout`, used by `Login` and `Register`) stays a direct child of `components/`.
- Same ownership rule applies to `lib/` files: a lib file used by exactly one component moves into that component's folder. A lib file shared by siblings under the same owner nests at their nearest common ancestor's folder. A lib file used broadly across the app (`api.ts`) or app-wide context (`auth/`) stays at top-level `src/lib/`.

Target structure:

```
src/
  App.tsx
  AppRoutes.tsx
  components/
    Home/
      Home.tsx
      Home.test.tsx
    Login/
      Login.tsx
      Login.test.tsx
    Register/
      Register.tsx
      Register.test.tsx
    AuthLayout/
      AuthLayout.tsx
    RequireAuth/
      RequireAuth.tsx
      RequireAuth.test.tsx
    WebhookTestPage/
      WebhookTestPage.tsx
      WebhookTestPage.test.tsx
      webhookSignature.ts
      webhookSignature.test.ts
    ConversasLayout/
      ConversasLayout.tsx
      ConversasLayout.test.tsx
      lastSeen.ts
      Sidebar/
        Sidebar.tsx
        Sidebar.test.tsx
        useUserSocket.ts
      Conversa/
        Conversa.tsx
        Conversa.test.tsx
        messageGrouping.ts
        messageGrouping.test.ts
        useConversationSocket.ts
      ConversaEmptyState/
        ConversaEmptyState.tsx
  lib/
    api.ts
    api.test.ts
    auth/
      AuthContext.tsx
      AuthContext.test.tsx
  theme.ts
  main.tsx
  index.css
```

File moves from current state:

- `routes/Home.tsx(.test)` → `components/Home/Home.tsx(.test)`
- `routes/Login.tsx(.test)` → `components/Login/Login.tsx(.test)`
- `routes/Register.tsx(.test)` → `components/Register/Register.tsx(.test)`
- `components/AuthLayout.tsx` → `components/AuthLayout/AuthLayout.tsx`
- `routes/RequireAuth.tsx(.test)` → `components/RequireAuth/RequireAuth.tsx(.test)`
- `routes/WebhookTestPage.tsx(.test)` → `components/WebhookTestPage/WebhookTestPage.tsx(.test)`
- `lib/webhookSignature.ts(.test)` → `components/WebhookTestPage/webhookSignature.ts(.test)`
- `routes/ConversasLayout.tsx(.test)` → `components/ConversasLayout/ConversasLayout.tsx(.test)`
- `lib/lastSeen.ts` → `components/ConversasLayout/lastSeen.ts`
- `routes/Sidebar.tsx(.test)` → `components/ConversasLayout/Sidebar/Sidebar.tsx(.test)`
- `lib/useUserSocket.ts` → `components/ConversasLayout/Sidebar/useUserSocket.ts`
- `routes/Conversa.tsx(.test)` → `components/ConversasLayout/Conversa/Conversa.tsx(.test)`
- `lib/messageGrouping.ts(.test)` → `components/ConversasLayout/Conversa/messageGrouping.ts(.test)`
- `lib/useConversationSocket.ts` → `components/ConversasLayout/Conversa/useConversationSocket.ts`
- `routes/ConversaEmptyState.tsx` → `components/ConversasLayout/ConversaEmptyState/ConversaEmptyState.tsx`
- `lib/api.ts(.test)` stays at `lib/api.ts(.test)`
- `lib/auth/AuthContext.tsx(.test)` stays at `lib/auth/AuthContext.tsx(.test)`

The `<Routes>` tree structure and paths are unchanged — only the import paths for `Home`, `Register`, `ConversasLayout`, `ConversaEmptyState`, `Conversa`, `RequireAuth`, `WebhookTestPage` are updated to point at their new `components/` locations, and the tree itself now lives in `AppRoutes.tsx` instead of `App.tsx`.

Purely mechanical move — no behavior, markup, or logic changes to any file beyond updated import paths.

**Blocked by:** 22

**Status:** done

- [x] `frontend/src/routes/` directory no longer exists; `AppRoutes.tsx` is the sole place declaring the `<Routes>` tree, `App.tsx` holds only the provider tree
- [x] No flat `.tsx` files directly inside `components/` — every entry is a folder named after its component, containing `ComponentName.tsx`
- [x] `Sidebar`, `Conversa`, `ConversaEmptyState` nest inside `components/ConversasLayout/` per the target structure above; `AuthLayout` stays a direct child of `components/`
- [x] `lastSeen.ts`, `messageGrouping.ts`, `useConversationSocket.ts`, `useUserSocket.ts`, `webhookSignature.ts` moved to the owning component's folder per the mapping above; `api.ts` and `lib/auth/` remain at top-level `lib/`
- [x] All existing test files moved alongside their subject and still passing (`npm run test` in `frontend/`)
- [x] `npm run build` and `npm run lint` pass in `frontend/` with no new errors
- [x] No behavior/markup changes — this is a pure file-move + import-path refactor

## Comments

Implemented as a purely mechanical `git mv` + import-path-update pass, verified with `tsc --noEmit`, `npm run test` (91/91 passing throughout), `npm run build`, and `npm run lint` (0 errors; the one pre-existing oxlint warning on `AuthContext.tsx` is untouched by this change) after every batch of moves.

Two deviations from the ticket's literal text, both confirmed before implementing:

- The spec's target tree listed a separate `Login/` folder and a `routes/Login.tsx → components/Login/Login.tsx` move, but the codebase has no `routes/Login.tsx` — the login form was merged into `Home.tsx` and `/login` removed back in commit `c24f983`, predating this ticket. Treated as stale spec drift; only `Home.tsx` was moved.
- Several files predate this ticket and aren't in its explicit file-moves list: `AvatarFrame.tsx`, `WindowChrome.tsx`, `msnButtonStyle.ts`, `scrollbarStyle.ts`, `textFieldStyle.ts`, `conversationLabel.ts`, `jwt.ts`. Placed by applying the ticket's own ownership rules to their actual usage: `AvatarFrame` and `WindowChrome` are each used by 2+ unrelated pages → stayed direct children of `components/`; `msnButtonStyle`, `scrollbarStyle`, `textFieldStyle`, `conversationLabel` are shared by `Sidebar` and `Conversa` (siblings under `ConversasLayout`) → nested at `components/ConversasLayout/`; `jwt.ts` is used only by `lib/api.ts` → stayed at top-level `lib/`.

Mid-implementation, the `<Routes>` tree was further extracted out of `App.tsx` into its own `src/AppRoutes.tsx` (at the user's request, overriding the ticket's original "`App.tsx` is the single place the `<Routes>` tree is declared" rule) — `App.tsx` now holds only the provider tree (`ThemeProvider`, `QueryClientProvider`, `AuthProvider`, `BrowserRouter`) and renders `<AppRoutes />`. Rule text, target tree, and checklist above were updated to reflect this before implementing it.

Reviewed with `/code-review` (Standards + Spec axes, run against the uncommitted working-tree diff since nothing had been committed yet) — both axes reported zero findings.
