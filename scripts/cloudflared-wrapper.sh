#!/bin/sh
# Wrapper script that runs cloudflared and exposes the tunnel URL via HTTP
# URL target is hardcoded since Docker command passing is problematic

TARGET_URL="http://nginx:80"

# Start HTTP server in background that will serve the URL
(
  while [ ! -f /tmp/tunnel_url.txt ]; do
    sleep 0.5
  done

  while true; do
    URL=$(cat /tmp/tunnel_url.txt 2>/dev/null || echo "")
    printf "HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: %d\r\n\r\n%s" "${#URL}" "$URL" | nc -l -p 8080 -q 1 2>/dev/null || true
  done
) &

# Run cloudflared with explicit --url flag
cloudflared tunnel --no-autoupdate --url "$TARGET_URL" 2>&1 | while IFS= read -r line; do
  echo "$line"
  case "$line" in
    *trycloudflare.com*)
      URL=$(echo "$line" | sed -n 's/.*\(https:\/\/[a-z0-9-]*\.trycloudflare\.com\).*/\1/p')
      if [ -n "$URL" ]; then
        echo "$URL" > /tmp/tunnel_url.txt
        echo "[wrapper] Tunnel URL: $URL"
      fi
      ;;
  esac
done
