# 21 — Refactor frontend directory structure

**What to build:** Restructure `frontend/src` so routing, pages, and shared UI each live in a predictable place, and ownership of route-private code is visible on disk.

Rules:

- `routes/` is removed as a concept. `App.tsx` is the single place the `<Routes>` tree is declared — it only wires `path` → `element`, importing pages from `components/`. No component logic lives in a routing file.
- Every component/page gets its own folder named after it, with the file repeating the folder name (PascalCase): `components/Login/Login.tsx`, not `components/Login.tsx` or an `index.tsx`. No flat `.tsx` files directly inside `components/`.
- Colocate a component's test next to it in the same folder (`Login/Login.test.tsx`).
- A component/page used only by one other component nests inside that owner's folder (no intermediate `components/` subfolder — just directly inside, e.g. `ConversasLayout/Sidebar/Sidebar.tsx`). A component used by 2+ unrelated pages (`AuthLayout`, used by `Login` and `Register`) stays a direct child of `components/`.
- Same ownership rule applies to `lib/` files: a lib file used by exactly one component moves into that component's folder. A lib file shared by siblings under the same owner nests at their nearest common ancestor's folder. A lib file used broadly across the app (`api.ts`) or app-wide context (`auth/`) stays at top-level `src/lib/`.

Target structure:

```
src/
  App.tsx
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

`App.tsx`'s `<Routes>` tree structure and paths are unchanged — only the import paths for `Home`, `Login`, `Register`, `ConversasLayout`, `ConversaEmptyState`, `Conversa`, `RequireAuth`, `WebhookTestPage` are updated to point at their new `components/` locations.

Purely mechanical move — no behavior, markup, or logic changes to any file beyond updated import paths.

**Blocked by:** 22

**Status:** ready-for-agent

- [ ] `frontend/src/routes/` directory no longer exists; `App.tsx` is the sole place declaring the `<Routes>` tree
- [ ] No flat `.tsx` files directly inside `components/` — every entry is a folder named after its component, containing `ComponentName.tsx`
- [ ] `Sidebar`, `Conversa`, `ConversaEmptyState` nest inside `components/ConversasLayout/` per the target structure above; `AuthLayout` stays a direct child of `components/`
- [ ] `lastSeen.ts`, `messageGrouping.ts`, `useConversationSocket.ts`, `useUserSocket.ts`, `webhookSignature.ts` moved to the owning component's folder per the mapping above; `api.ts` and `lib/auth/` remain at top-level `lib/`
- [ ] All existing test files moved alongside their subject and still passing (`npm run test` in `frontend/`)
- [ ] `npm run build` and `npm run lint` pass in `frontend/` with no new errors
- [ ] No behavior/markup changes — this is a pure file-move + import-path refactor
