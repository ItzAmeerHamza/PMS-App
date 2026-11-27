# Vercel deployment (owner dashboard)

Written in phase 08. **Nothing has been deployed.** Deploying needs the owner's Vercel account, an explicit go-ahead, and a check of Vercel's current pricing and commercial-use terms. The Hobby plan is not the assumption for a pharmacy business: confirm a paid plan before real patient records are shown there.

The app is `dashboard/`. It is a Next.js server. The browser talks only to that server. The server calls the Railway API. The browser never receives `DATABASE_URL`, a device secret, or the owner's cloud session token.

## Build

| Setting | Value |
| --- | --- |
| Root directory | `dashboard` |
| Framework | Next.js |
| Install command | `npm install` |
| Build command | `npm run build` |
| Output | Next.js default (no static export) |
| Node | 20 or newer (developed on 24) |

Do not set the output to a static export. Login, MFA, and the read APIs run on the server.

## Environment variables

Set these on the Vercel project, not in the repository.

| Name | Value |
| --- | --- |
| `CLOUD_API_URL` | The Railway API origin, `https://<service>.up.railway.app`, with no path and no password in the URL |

There is no `DATABASE_URL` on Vercel. There is no owner password and no device secret.

`NODE_ENV=production` (Vercel sets this) makes the session cookie `Secure`.

## Cookies

| Cookie | Who sets it | Flags | Contents |
| --- | --- | --- | --- |
| `pharmacare_session` | Next.js, after a correct TOTP code | HttpOnly, SameSite=Lax, Secure in production, Path=/, 12 hours | The cloud session token. JavaScript on the page cannot read it. |
| `pharmacare_csrf` | Next.js, before the login form | SameSite=Lax, Secure in production, Path=/ | A random value the login, code, and sign-out forms must send back. |

Sign-in, the authentication-code step, and sign-out are refused when the form value does not match the CSRF cookie.

The cloud API also sets `pharmacare_owner` (HttpOnly) and `pharmacare_csrf` on its own origin. The dashboard server uses the cloud CSRF only while it is calling Railway. The browser is not pointed at Railway.

On Railway, set `COOKIE_SECURE=true` so the cloud's own cookie is marked Secure. Local tests leave it false because they use `http://`.

## Railway API the server calls

`CLOUD_API_URL` plus:

- `GET /api/v1/owner/csrf`, `POST /api/v1/owner/login`, `POST /api/v1/owner/totp`, `POST /api/v1/owner/logout`
- `GET /api/v1/admin/shops`, `/overview`, `/inventory`, `/patients`, `/prescriptions`, `/movements`, `/sync-status`, and the inventory and patient detail routes

Every admin call sends `Authorization: Bearer` from the HttpOnly session. A shop device token is still rejected by those routes.

Set the cloud service's `CORS_ORIGINS` only if a browser will call Railway directly. This dashboard does not.

## Before going live

- Create the owner with `python -m app.cli create-owner` on Railway, then enroll TOTP on the first sign-in. The authenticator key is shown once.
- Confirm Vercel's paid-plan terms for a commercial pharmacy dashboard.
- Do not put real patient data on a Hobby deployment while that check is open.
