# Trading Game

This repository is being reorganized for a new responsive hosted version.

- `streamlit_version/` contains the existing Streamlit implementation.
- The new version can be built at the repository root with a separate stack.

See [streamlit_version/README.md](streamlit_version/README.md) for the current Streamlit app instructions.

## Deployment Handoff Notes

The current delivery target is Streamlit Community Cloud with Neon Postgres.

Required Streamlit secrets:

```toml
DATABASE_URL = "postgresql+psycopg://USER:PASSWORD@HOST/DB?sslmode=require"
PROFESSOR_PASSWORD = "change-this-password"
PROFESSOR_EMAILS = ["professor@example.com"]
```

Do not commit secrets. To rotate the Neon credential, create or reveal a new Neon connection string, replace `DATABASE_URL` in Streamlit secrets, and restart the app. To change professor access, replace `PROFESSOR_PASSWORD` and `PROFESSOR_EMAILS` in Streamlit secrets.

Local development can use SQLite fallback by omitting `DATABASE_URL`, or by running commands with `TRADING_GAME_FORCE_SQLITE=1`. Demo seeding is development-only and should not run automatically in production.
