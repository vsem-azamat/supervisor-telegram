#!/bin/bash
# Get ngrok public URL from the API

set -e

NGROK_API="http://localhost:4040/api/tunnels"
MAX_RETRIES=30
RETRY_DELAY=1

echo "🔍 Waiting for ngrok to start..."

for i in $(seq 1 $MAX_RETRIES); do
    if curl -s "$NGROK_API" > /dev/null 2>&1; then
        # Get the HTTPS URL
        NGROK_URL=$(curl -s "$NGROK_API" | grep -o '"public_url":"https://[^"]*' | head -1 | cut -d'"' -f4)

        if [ -n "$NGROK_URL" ]; then
            echo ""
            echo "✅ ngrok is ready!"
            echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            echo "📍 Public URL: $NGROK_URL"
            echo "🔧 Web UI:     http://localhost:4040"
            echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            echo ""
            echo "🚀 Services available at:"
            echo "   • WebApp:      $NGROK_URL/"
            echo "   • API:         $NGROK_URL/api/"
            echo "   • Health:      $NGROK_URL/health"
            echo ""
            echo "💡 To update .env automatically, run:"
            echo "   ./scripts/update-webapp-url.sh"
            echo ""
            exit 0
        fi
    fi

    if [ $i -eq $MAX_RETRIES ]; then
        echo "❌ Timeout waiting for ngrok"
        echo "Make sure ngrok service is running:"
        echo "   docker compose --profile ngrok up -d ngrok"
        exit 1
    fi

    printf "."
    sleep $RETRY_DELAY
done
