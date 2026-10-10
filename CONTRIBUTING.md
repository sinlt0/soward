# Contributing to Soward

Thanks for your interest in contributing!

## Before You Start

Soward is licensed under the **Apache License 2.0** (see `LICENSE` and
`NOTICE`). By submitting a contribution you agree it is licensed under the same
terms, and that the attribution requirements (crediting Sinlt as original
author) continue to apply.

## Project Structure

```
main.py        entry point
config.py      tunable constants
cogs/          one file per feature, auto-loaded
events/        cross-system listeners, auto-loaded
utils/         shared helpers (db, security, components, ...)
emoji/         emoji dictionaries merged by EmojiManager
dashboard/     Flask site and web dashboard (separate process)
```

Dropping a file into `cogs/` or `events/` is enough to register it.

## Getting Set Up

```bash
git clone https://github.com/sinlt0/soward.git && cd soward
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env              # add your own bot token
# edit devs.json and swap in your own Discord ID for local testing
python main.py
```

Never commit `.env` or `data/`, and don't commit changes to the IDs in `devs.json`.

## Making Changes

- Keep PRs focused: one feature or fix each.
- Match the existing style. Use `utils/emoji_manager` for emoji (no raw Unicode
  emoji in bot output) and the Components V2 helpers in `utils/components.py`
  for new UI.
- Don't swallow errors with a bare `except: pass` — log them.
- Check that the code compiles and lints before pushing:
  ```bash
  python -m compileall -q cogs events utils web main.py config.py
  pip install ruff && ruff check --select E9,F63,F7,F82 .
  ```
- Test against a real test server and say what you tested in the PR.

## Submitting a Pull Request

1. Fork the repository and create a feature branch.
2. Commit with clear, descriptive messages.
3. Open a PR describing what changed and why.
4. Respond to review feedback.

## Reporting Issues

Include expected vs. actual behavior, reproduction steps, and logs with secrets
redacted. Security issues go through [SECURITY.md](./SECURITY.md) instead.

## Code of Conduct

By participating you agree to follow the [Code of Conduct](./CODE_OF_CONDUCT.md).

## License & Attribution Reminder

Any fork or redistribution must retain `LICENSE` and `NOTICE` and the required
attribution to the original author, Sinlt.
