# AI News Agent - Backend

This is the **Python Intelligence Engine** for the AI News Platform.

## How to Run

Open a terminal inside `ai-news-agent-backend/` and run:

```bash
# Install dependencies (first time only)
pip install -r requirements.txt

# Start the Backend Server (port 8000)
python main.py
```

The backend will start on: **http://127.0.0.1:8000**

It automatically serves the frontend templates from the `ai-news-agent-frontend/templates/` folder
and static assets from `ai-news-agent-frontend/static/`.

## Available Commands

```bash
# Run once - manually trigger news collection cycle
python main.py run-once

# Initialize database
python main.py init-db
```

## API Health Check

Visit: http://127.0.0.1:8000/health

## Notes

- The `.env` file must be present with your API keys.
- The `service-account.json` file must be present for Firebase.
- The `data/` folder contains the SQLite database and is shared with the frontend.
