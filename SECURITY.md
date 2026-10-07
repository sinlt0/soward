# Security Policy

## Reporting a Vulnerability

Soward includes AntiNuke, AutoMod and permission logic, so security reports
matter. Please **do not** open a public issue. Report privately:

- Open a [GitHub Security Advisory](../../security/advisories/new) on this
  repository, **or**
- Contact Sinlt directly via the contact method in the repository's About
  section.

Please include a description and impact, minimal reproduction steps, and any
relevant logs with tokens and IDs redacted.

## Supported Versions

Only the latest version on `main` receives security fixes.

## Secrets

Never commit `SOWARD_TOKEN`, database URIs, Lavalink passwords, API keys,
webhook URLs. Use `.env` (gitignored) and the provided `.env.example`
template.

If you accidentally commit a secret, **rotate it immediately** — deleting it
in a later commit does not remove it from git history. Discord also
auto-revokes bot tokens it detects in public repositories.
