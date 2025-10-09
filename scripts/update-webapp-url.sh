#!/bin/bash
# Update WEBAPP_URL in .env with current ngrok URL

set -e

NGROK_API="http://localhost:4040/api/tunnels"
ENV_FILE=".env"

# Check if .env exists
if [ ! -f "$ENV_FILE" ]; then
    echo "❌ .env file not found"
    echo "Copy .env.example to .env first:"
    echo "   cp .env.example .env"
    exit 1
fi

# Get ngrok URL
NGROK_URL=$(curl -s "$NGROK_API" | grep -o '"public_url":"https://[^"]*' | head -1 | cut -d'"' -f4)

if [ -z "$NGROK_URL" ]; then
    echo "❌ Could not get ngrok URL"
    echo "Make sure ngrok is running:"
    echo "   docker compose --profile ngrok up -d ngrok"
    exit 1
fi

# Backup .env
cp "$ENV_FILE" "$ENV_FILE.backup"

# Update or add WEBAPP_URL
if grep -q "^WEBAPP_URL=" "$ENV_FILE"; then
    # Update existing
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        sed -i '' "s|^WEBAPP_URL=.*|WEBAPP_URL=$NGROK_URL|" "$ENV_FILE"
    else
        # Linux
        sed -i "s|^WEBAPP_URL=.*|WEBAPP_URL=$NGROK_URL|" "$ENV_FILE"
    fi
    echo "✅ Updated WEBAPP_URL in .env"
else
    # Add new line
    echo "" >> "$ENV_FILE"
    echo "# Ngrok public URL (auto-updated)" >> "$ENV_FILE"
    echo "WEBAPP_URL=$NGROK_URL" >> "$ENV_FILE"
    echo "✅ Added WEBAPP_URL to .env"
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📍 WEBAPP_URL: $NGROK_URL"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "🔄 Restart services to apply changes:"
echo "   docker compose restart bot api"
echo ""
echo "💾 Backup saved: .env.backup"
