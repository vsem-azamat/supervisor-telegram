# Bot for moderating chats in Telegram
For moderating educational chats in the Czech Republic on Telegram. The bot is currently in the development stage.🚧

## Content
- [Links to get familiar with the bot](#links-to-get-familiar-with-the-bot)
- [Features](#features)
- [Setup and Run](#setup-and-run)
  - [Development](#development)
  - [Production](#production)
- [Commands for moderating](#commands-for-moderating)


## Links to get familiar with the bot
- Bot: @konnekt_moder_bot
- One of the chats with the bot: @cvut_chat


## Features

* ✅ - implemented
* ❌ - will be implemented
* 🚧 - in progress

| Feature | Description | Status |
|---------|-------------|--------|
| Moderating | Base commands for moderating the chat (mute, ban, etc.) | ✅ |
| Welcome message | Sending a welcome message to new chat members | ✅ |
| Saving messages history | Saving messages history to the database | ✅ |
| Captcha | Checking if the user is a bot | ❌ |
| Report | Sending a report to the admins | ❌ |
| ML model | Detecting spam messages | ❌ |

## Architecture

The project now follows a layered Domain-Driven approach:

- `app/domain` contains domain models.
- `app/infrastructure` provides infrastructure code like database repositories.
- `app/application` holds application services.
- `app/presentation` includes the Telegram interface with handlers and middlewares.

Run the bot with:

```bash
python -m app.presentation.telegram
```


## Setup and Run

### Development

1) **Set up environment variables:**
```bash
cp .env.example .env
```

2) **Create virtual environment and install dependencies:**
```bash
uv venv .venv
uv sync --dev
source .venv/bin/activate
```

3) **Fill in the `.env` file** with your bot token and other required values.

4) **Run in development mode** (includes hot-reload, ngrok for HTTPS, adminer for DB):
```bash
docker compose up --build
```

This automatically loads `docker-compose.override.yml` which includes:
- 🔄 Hot-reload for bot and API
- 🌐 ngrok for HTTPS tunneling (required for Telegram WebApp)
- 🗄️ Adminer database UI at `http://localhost:8080`
- 📡 ngrok Web UI at `http://localhost:4040`

Get your public ngrok URL:
```bash
./scripts/get-ngrok-url.sh
```

### Production

1) **Set up production environment:**
```bash
cp .env.prod.example .env
```

2) **Configure required variables in `.env`:**
   - `BOT_TOKEN` - Your Telegram bot token
   - `ADMIN_SUPER_ADMINS` - Comma-separated admin user IDs
   - `DB_PASSWORD` - Strong database password
   - `WEBAPP_URL` - Your HTTPS domain (e.g., `https://bot.yourdomain.com`)
   - `WEBAPP_API_SECRET` - Secure API secret key

3) **Set up HTTPS reverse proxy:**

The bot **requires HTTPS** for Telegram WebApp. Configure your nginx/reverse proxy to:
- Forward `https://yourdomain.com/*` → `http://your-server:80` (webapp + api)
- Use SSL certificates (Let's Encrypt, Cloudflare, etc.)

Example nginx config:
```nginx
server {
    listen 443 ssl http2;
    server_name bot.yourdomain.com;

    ssl_certificate /path/to/fullchain.pem;
    ssl_certificate_key /path/to/privkey.pem;

    location / {
        proxy_pass http://localhost:80;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Or use **Nginx Proxy Manager**, **Caddy**, **Traefik**, or **Cloudflare Tunnel**.

4) **Deploy the stack:**
```bash
docker compose -f docker-compose.yaml up --build -d
```

This runs production mode without dev overrides:
- ✅ Optimized production builds
- ✅ No hot-reload or dev tools
- ✅ Runs as non-root user
- ✅ Persistent database volume

5) **Verify deployment:**
```bash
# Check services are running
docker compose ps

# Check logs
docker compose logs -f bot
docker compose logs -f api

# Health check
curl https://yourdomain.com/health
```

### Tests

Run tests locally:
```bash
uv run -m pytest
```

Or use Make commands:
```bash
make test           # All tests
make test-fast      # Skip slow tests
make test-cov       # With coverage report
```


## Commands for moderating

* ✅ - implemented
* ❌ - will be implemented
* 🚧 - in progress
* 👮 - admins
* 🧑‍🎓 - user

| Command | Description | Status | For whom |
|---------|-------------|--------|----------|
| `/mute *int*` | Mutes a user in the chat for the specified time in minutes. Default: 5 minutes. | ✅ | 👮 |
| `/unmute` | Unmutes a user in the chat. | ✅ | 👮 |
| `/ban` | Bans a user from the chat and adds to the blacklist. | ✅ | 👮 |
| `/unban` | Unbans a user from the blacklist. | ✅ | 👮 |
| `black` | Adds a user to the blacklist for all chats. | ✅ | 👮 |
| `/blacklist` | Shows blacklisted users with unban buttons. | ✅ | 👮 |
| `welcome` | Enables a welcome message for new chat members. | ✅ | 👮 |
| `welcome <text>` | Changes the welcome message. | ✅ | 👮 |
| `welcome -t <int>` | Changes the time for auto-deleting the welcome message. | 🚧 | 👮 |
| `welcome -b` | Enables a simple button for checking if the user is a bot in the welcome message. | ❌ | 👮 |
| `welcome -c` | Enables a captcha button for checking if the user is a bot in the welcome message. | ❌ | 👮 |
| `welcome -s` | Shows the current settings for the welcome message. | ❌ | 👮 |
| `/chats` | Sends a list of educational chats from the `ChatLinks` table in the `/db/moder_bot.db` database. | ✅ | 🧑‍🎓 |
| `report` | Sends a report to the admins | ❌ | 🧑‍🎓 |
