# Bounty Coders

Bounty Coders is a Flask application with server-rendered HTML templates, static media, a PostgreSQL production database, and a local SQLite development fallback.

- Deployment steps: [DEPLOYMENT.md](DEPLOYMENT.md)
- Render Blueprint: [render.yaml](render.yaml)
- Backend and frontend environment examples: [config](config)
- Local environment template: [.env.example](.env.example)

## Local development

Install Python 3.14.10, then run:

```powershell
py -m pip install -r requirements-dev.txt
py app.py
```

The app creates a local `bountycoders.db` database and seeds the built-in course data on first startup. Copy `.env.example` to `.env` for local configuration. To use Supabase, put its Session Pooler connection string in `DATABASE_URL` and keep `DB_SSLMODE=require`. The app loads `.env` automatically; `.env` is ignored by Git. Never paste database or provider keys into source files or frontend settings.

Python, Java, and C snippets run only through the server-side OnlineCompiler.io API. `Run Code` only displays execution output. `Submit Answer` grades the active question and is the only action that can change hearts or bounty. Set `ONLINECOMPILER_API_KEY` privately; without it, code runs return a service-configuration message and do not penalize the player. HTML/CSS remains checked by the app's structural evaluator.

Each difficulty attempt starts with three hearts. Correct answers earn 5 million berries on Easy, 10 million on Medium, and 15 million on Hard. Incorrect submissions subtract 1 million (never taking the account total below zero). Using all three hearts ends that difficulty attempt and clears its attempt bounty; completed difficulties and best records remain. Overall leaderboard score is the user's best completed Easy + Medium + Hard bounty.

The local test suite isolates itself from `.env` and the Supabase database. Run it with `py -m pytest` after installing `requirements-dev.txt`.
