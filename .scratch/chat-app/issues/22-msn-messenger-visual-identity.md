# 22 — MSN Messenger visual identity for Login, Register and Webhook test page

**What to build:** Replace the current generic MUI look on `AuthLayout` (Login/Register) and `WebhookTestPage` with a nostalgic MSN Messenger identity — an expanded MUI theme plus shared "window chrome" styling, applied consistently across all three screens. This supersedes the visual outcome of tickets 18 and 20. Existing behavior (mutations, error handling, navigation, webhook signing/submission) is unchanged — visual only, with two explicit exceptions noted below where the ticket deliberately diverges from the prototype.

Reference (from a prototype, HTML/Tailwind — decisions to port into MUI, not literal markup):

**Shared identity:**
- Window chrome: a rounded, shadowed container (`msn-window`) with a titlebar strip (`msn-titlebar`) taking an icon + label on the left and optional actions/dots on the right.
- Avatar frame: a circular, bordered avatar container (`msn-avatar-frame`), with an optional bottom-right online-status dot (emerald).
- Inputs/buttons: rounded, small-text (`text-xs`) inputs with a left-aligned icon slot (`msn-input`), matching rounded button style (`msn-button`).
- Palette: sky-blue as primary/chrome color, emerald and amber as accent colors (status/warning), slate for body text.
- Typography: bold small labels, bold headings in the primary dark-blue tone (`text-sky-900`).

**Login:**
- Titlebar: user-circle icon + "Entrar no MSN Messenger", small sky/amber dots on the right.
- Large circular avatar (with status dot) above the form.
- Heading: "Informe suas credenciais para entrar".
- Fields: email — icon-prefixed, labeled "E-mail (Windows Live ID)"; password — icon-prefixed (key icon).
- A "Lembrar minhas credenciais" checkbox.
- Submit button "Entrar" (sign-in icon).
- Footer: "Ainda não possui uma conta? Cadastre-se aqui" linking to Register.

**Register:**
- Titlebar: user-plus icon + "Criar nova conta Passport / MSN".
- Smaller circular avatar (no status dot).
- Heading: "Cadastro de Novo Usuário".
- Fields: username — icon-prefixed (user icon), labeled "Nome de Usuário (Nick MSN)", nostalgic-nick placeholder; email — icon-prefixed; password — icon-prefixed (lock icon).
- Submit button "Concluir Cadastro" (check-circle icon).
- Footer: "Já possui uma conta MSN? Ir para Tela de Login" linking to Login.

**Webhook test page (two explicit divergences from the prototype, confirmed with the user — see checklist):**
- Full-width layout with large lateral spacing, matching the pattern already established for the conversas screen (ticket 19) — not a centered narrow card like Login/Register.
- Window chrome titlebar: robot icon + "Painel de Integração e Teste de WebHook", with a "Voltar às Conversas" action on the right.
- A "connected user" chip near the top of the form: small avatar + "Usuário Conectado: {username}" + an "Ativo" status badge.
- The existing disclaimer ("essa é apenas uma pagina para teste do WebHook") becomes a highlighted callout (icon + bold lead-in) instead of plain italic text.
- Fields keep their current types (text inputs + textarea for the message) with icon-prefixed `msn-input` styling; submit button restyled as "Enviar WebHook de Teste" (paper-plane icon).
- A footer action below the window to return to the conversas screen.
- Divergence 1: conversation-id field stays free text — no dropdown, no fetching the user's conversation list.
- Divergence 2: feedback area still shows only the latest test result — no persistent/clearable log.

Build as:
- `theme.ts`: palette (primary sky-blue, emerald + amber accents), typography scale, `MuiButton`/`MuiPaper`/`MuiOutlinedInput` style overrides reflecting the shared identity above.
- Reusable window-chrome and avatar-frame components (titlebar with icon/label/actions, rounded/shadowed body; circular avatar with optional status dot), used by `AuthLayout` and `WebhookTestPage`.
- `AuthLayout`, `Login`, `Register`, `WebhookTestPage` updated to use the new theme/components per the references above.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] `theme.ts` defines the MSN Messenger-inspired palette, typography, and component overrides
- [ ] Reusable window-chrome and avatar-frame components exist and are used by `AuthLayout` and `WebhookTestPage`
- [ ] Login screen matches the reference above (titlebar copy, avatar+status dot, credential-themed labels, "remember me" checkbox, footer link to Register)
- [ ] Register screen matches the reference above (titlebar copy, avatar without status dot, nick-themed username label, footer link to Login)
- [ ] Webhook test page matches the reference above (full-width layout, titlebar with back action, connected-user chip, highlighted disclaimer, restyled submit button, footer back-action)
- [ ] Webhook test page keeps the conversation-id field as free text (no dropdown/data-fetch) and keeps showing only the latest result (no persistent log) — deliberate divergences from the prototype
- [ ] Existing Login/Register/WebhookTestPage tests still pass (updated for new markup as needed); no change to `lib/api.ts`, auth flow, or webhook signing/submission behavior
- [ ] `npm run build` and `npm run lint` pass in `frontend/` with no new errors
