# 14 — Validate email format and password strength on auth endpoints

**What to build:** `POST /auth/register` rejects malformed email addresses and weak passwords with a 422 and a clear error message. `POST /auth/login` rejects malformed email addresses with a 422 (password complexity is NOT re-validated at login, since existing users must still be able to log in with passwords that predate this rule).

**Blocked by:** None — can start immediately

**Priority:** High

**Status:** ready-for-agent

- [ ] `UserCreate.email` and `UserLogin.email` use a real email-format validator (e.g. Pydantic `EmailStr`) instead of plain `str`
- [ ] `UserCreate.password` enforces a minimum length plus a mix of uppercase, lowercase, and digit/symbol characters
- [ ] `UserLogin.password` stays unconstrained beyond "non-empty" — it must not reject existing users whose stored password predates the new complexity rule
- [ ] Register: test that an invalid email is rejected (422), a weak password is rejected (422), and a valid email + strong password succeeds
- [ ] Login: test that an invalid email is rejected (422) and a valid email format is accepted regardless of password complexity
