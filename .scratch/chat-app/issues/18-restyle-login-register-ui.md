# 18 — Restyle login and register screens (UI)

**What to build:** The login and register screens get a centered, MUI-styled card layout instead of the current plain unstyled HTML forms, matching the visual language already used on the conversas screens (Sidebar, Conversa).

Extract a shared `AuthLayout` component (centered card, page background) used by both screens, since they're visually identical apart from their fields.

- Login: email + password fields, centered vertically and horizontally on the page, link below to the register screen.
- Register: username + email + password fields, centered vertically and horizontally on the page, link below to the login screen.

Existing behavior (mutations, error messages, navigation on success) is unchanged — this is a visual restyle only.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] Shared `AuthLayout` (or equivalent) component renders a centered MUI `Paper`/`Card` on the page background, reused by both Login and Register
- [ ] Login screen: email + password `TextField`s, submit `Button`, centered on the page, existing error/loading states preserved, link to `/register` below the form
- [ ] Register screen: username + email + password `TextField`s, submit `Button`, centered on the page, existing error/loading states preserved, link to `/login` below the form
- [ ] Existing Login/Register tests still pass (updated for the new markup as needed); no change to `lib/api.ts` or auth flow behavior
