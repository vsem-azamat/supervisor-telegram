#!/bin/sh
set -eu

env_file="${1:-.env}"
template_file="${2:-.env.production.example}"

if [ ! -f "$env_file" ]; then
  echo "env file not found: $env_file" >&2
  exit 2
fi

if [ ! -f "$template_file" ]; then
  echo "template file not found: $template_file" >&2
  exit 2
fi

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

env_keys="$tmp_dir/env.keys"
template_keys="$tmp_dir/template.keys"

awk -F= '/^[A-Z][A-Z0-9_]*=/{print $1}' "$env_file" | sort -u > "$env_keys"
awk -F= '/^[A-Z][A-Z0-9_]*=/{print $1}' "$template_file" | sort -u > "$template_keys"

value_of() {
  awk -F= -v key="$1" '
    $1 == key {
      sub(/^[^=]*=/, "")
      print
      found = 1
      exit
    }
    END { if (!found) exit 1 }
  ' "$env_file" 2>/dev/null || true
}

has_key() {
  grep -qx "$1" "$env_keys"
}

is_true() {
  value="$(value_of "$1" | tr '[:upper:]' '[:lower:]')"
  [ "$value" = "true" ] || [ "$value" = "1" ] || [ "$value" = "yes" ]
}

is_empty() {
  [ -z "$(value_of "$1")" ]
}

section() {
  printf '\n%s\n' "$1"
}

print_keys_or_ok() {
  if [ -s "$1" ]; then
    sed 's/^/  - /' "$1"
  else
    echo "  ok"
  fi
}

section "Missing keys from production template"
comm -13 "$env_keys" "$template_keys" > "$tmp_dir/missing.keys"
print_keys_or_ok "$tmp_dir/missing.keys"

section "Keys not present in production template"
comm -23 "$env_keys" "$template_keys" > "$tmp_dir/extra.keys"
print_keys_or_ok "$tmp_dir/extra.keys"

section "Dev-only or stale values"
: > "$tmp_dir/dev.keys"
[ "$(value_of APP_ENVIRONMENT)" = "development" ] && echo "APP_ENVIRONMENT=development" >> "$tmp_dir/dev.keys"
[ "$(value_of APP_DEBUG)" = "true" ] && echo "APP_DEBUG=true" >> "$tmp_dir/dev.keys"
[ "$(value_of WEBAPI_SESSION_COOKIE_SECURE)" = "false" ] && echo "WEBAPI_SESSION_COOKIE_SECURE=false" >> "$tmp_dir/dev.keys"
case "$(value_of WEBAPI_ALLOWED_ORIGINS)" in
  *localhost:5173*) echo "WEBAPI_ALLOWED_ORIGINS contains localhost:5173" >> "$tmp_dir/dev.keys" ;;
esac
case "$(value_of WEBAPI_PUBLIC_URL)" in
  *localhost:5173*) echo "WEBAPI_PUBLIC_URL contains localhost:5173" >> "$tmp_dir/dev.keys" ;;
esac
has_key WEBAPI_DEV_BYPASS_AUTH && echo "WEBAPI_DEV_BYPASS_AUTH is obsolete" >> "$tmp_dir/dev.keys"
has_key TELETHON_ENABLED && echo "TELETHON_ENABLED is obsolete" >> "$tmp_dir/dev.keys"
has_key TELETHON_PHONE && echo "TELETHON_PHONE should be removed after first login" >> "$tmp_dir/dev.keys"
print_keys_or_ok "$tmp_dir/dev.keys"

section "Required empty values"
: > "$tmp_dir/empty.keys"
for key in IMAGE_TAG MODERATOR_BOT_TOKEN ADMIN_SUPER_ADMINS DB_USER DB_PASSWORD DB_HOST DB_NAME WEBAPI_PUBLIC_URL WEBAPI_ALLOWED_ORIGINS; do
  if ! has_key "$key" || is_empty "$key"; then
    echo "$key" >> "$tmp_dir/empty.keys"
  fi
done

if is_true MODERATION_ENABLED || is_true CHANNEL_ENABLED || is_true ASSISTANT_BOT_ENABLED; then
  if ! has_key OPENROUTER_API_KEY || is_empty OPENROUTER_API_KEY; then
    echo "OPENROUTER_API_KEY (required by enabled LLM features)" >> "$tmp_dir/empty.keys"
  fi
fi

if is_true ASSISTANT_BOT_ENABLED && { ! has_key ASSISTANT_BOT_TOKEN || is_empty ASSISTANT_BOT_TOKEN; }; then
  echo "ASSISTANT_BOT_TOKEN (required by ASSISTANT_BOT_ENABLED=true)" >> "$tmp_dir/empty.keys"
fi

if is_true CHANNEL_BRAVE_DISCOVERY_ENABLED && { ! has_key BRAVE_API_KEY || is_empty BRAVE_API_KEY; }; then
  echo "BRAVE_API_KEY (required by CHANNEL_BRAVE_DISCOVERY_ENABLED=true)" >> "$tmp_dir/empty.keys"
fi

if [ "$(value_of TELETHON_API_ID)" = "0" ] || is_empty TELETHON_API_HASH; then
  echo "TELETHON_API_ID/TELETHON_API_HASH" >> "$tmp_dir/empty.keys"
fi

if is_true SPONSORED_ADS_ENABLED; then
  if [ "$(value_of SPONSORED_ADS_MODERATOR_CHAT_ID)" = "0" ] || is_empty SPONSORED_ADS_SALES_CONTACT; then
    echo "SPONSORED_ADS_MODERATOR_CHAT_ID/SPONSORED_ADS_SALES_CONTACT (required by SPONSORED_ADS_ENABLED=true)" >> "$tmp_dir/empty.keys"
  fi
fi
print_keys_or_ok "$tmp_dir/empty.keys"
