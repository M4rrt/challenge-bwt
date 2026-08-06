# 14 — Validate email format and password strength on auth endpoints

**What to build:** `POST /auth/register` rejects malformed email addresses and weak passwords with a 422 and a clear error message. `POST /auth/login` rejects malformed email addresses with a 422 (password complexity is NOT re-validated at login, since existing users must still be able to log in with passwords that predate this rule).

**Blocked by:** None — can start immediately

**Priority:** High

**Status:** done

- [x] `UserCreate.email` and `UserLogin.email` use a real email-format validator (e.g. Pydantic `EmailStr`) instead of plain `str`
- [x] `UserCreate.password` enforces a minimum length plus a mix of uppercase, lowercase, and digit/symbol characters
- [x] `UserLogin.password` stays unconstrained beyond "non-empty" — it must not reject existing users whose stored password predates the new complexity rule
- [x] Register: test that an invalid email is rejected (422), a weak password is rejected (422), and a valid email + strong password succeeds
- [x] Login: test that an invalid email is rejected (422) and a valid email format is accepted regardless of password complexity

## Comments

Password policy confirmed with the user: minimum 8 characters, must contain at least one uppercase letter, one lowercase letter, and one digit-or-symbol character.

Implemented TDD (red-green per cycle) in `app/schemas/user.py`: `EmailStr` on both `UserCreate.email` and `UserLogin.email` (added `email-validator` dependency), a `field_validator` on `UserCreate.password` enforcing the confirmed policy. `UserLogin.password` untouched — login never re-checks strength, covered by a test that logs in a user inserted directly with a weak legacy password. Added `email-validator` to `pyproject.toml`/`uv.lock`. Updated existing `test_auth.py` fixture passwords (`senha-forte-123` → `Senha-Forte-123`, etc.) to stay compliant with the new rule — 10/10 tests passing.
