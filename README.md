# Bounty Coders

Bounty Coders is a Flask application with server-rendered HTML templates, static media, a PostgreSQL production database, and a local SQLite development fallback.

- Deployment steps: [DEPLOYMENT.md](DEPLOYMENT.md)
- Render Blueprint: [render.yaml](render.yaml)
- Backend and frontend environment examples: [config](config)

## Local development

Install Python 3.14.10, then run:

```powershell
py -m pip install -r requirements-dev.txt
py app.py
```

The app creates a local `bountycoders.db` database and seeds the built-in course data on first startup. The local code runner executes submitted programs on the development computer. Use it only with trusted code; production deployments disable arbitrary code execution until an isolated runner is available.
