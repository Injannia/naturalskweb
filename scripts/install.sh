#!/usr/bin/env bash
# NaturalskWeb installer — fresh VPS bootstrap.
# Idempotent: re-running won't duplicate the tunnel/DNS or overwrite .env.
#
# Usage:
#   ./scripts/install.sh                 # interactive prompts
#   APP_DOMAIN=app.example.com CF_API_TOKEN=xxx ./scripts/install.sh
#   ./scripts/install.sh --enable-access  # also gate domain behind Cloudflare Access
set -euo pipefail

TUNNEL_NAME="naturalskweb"
ENABLE_ACCESS=0
for arg in "$@"; do
  case "$arg" in
    --enable-access) ENABLE_ACCESS=1 ;;
    -h|--help) grep '^#' "$0" | sed 's/^# \?//'; exit 0 ;;
    *) echo "Unknown flag: $arg" >&2; exit 2 ;;
  esac
done

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." &>/dev/null && pwd)"
cd "$REPO_ROOT"

log()  { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
err()  { printf '\033[1;31mERROR:\033[0m %s\n' "$*" >&2; }
die()  { err "$*"; exit 1; }

# --- Step 0: preflight ---------------------------------------------------
apt_install() {
  command -v apt-get >/dev/null 2>&1 || die "Не apt-дистрибутив. Установи вручную: $*"
  [ "$(id -u)" -eq 0 ] || die "Нужны root-права для установки пакетов ($*). Запусти через sudo."
  apt-get update -y
  apt-get install -y "$@"
}

ensure_cmd() {
  local cmd="$1" pkg="${2:-$1}"
  command -v "$cmd" >/dev/null 2>&1 && return 0
  log "Устанавливаю $pkg (нет $cmd)"
  apt_install "$pkg"
}

install_docker() {
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    return 0
  fi
  log "Устанавливаю Docker + compose plugin"
  [ "$(id -u)" -eq 0 ] || die "Нужны root-права для установки Docker. Запусти через sudo."
  curl -fsSL https://get.docker.com | sh
  docker compose version >/dev/null 2>&1 || apt_install docker-compose-plugin
}

log "Preflight: проверяю хост-зависимости"
ensure_cmd git
ensure_cmd curl
ensure_cmd openssl
ensure_cmd jq
install_docker

# --- Step 1: параметры ---------------------------------------------------
APP_DOMAIN="${APP_DOMAIN:-}"
CF_API_TOKEN="${CF_API_TOKEN:-}"
if [ -z "$APP_DOMAIN" ]; then
  read -rp "Домен (например app.example.com): " APP_DOMAIN
fi
if [ -z "$CF_API_TOKEN" ]; then
  read -rsp "Cloudflare API token: " CF_API_TOKEN
  echo
fi
[ -n "$APP_DOMAIN" ]   || die "Домен обязателен"
[ -n "$CF_API_TOKEN" ] || die "CF API token обязателен"

CF_API="https://api.cloudflare.com/client/v4"
cf() {  # cf METHOD PATH [JSON-body]
  local method="$1" path="$2" body="${3:-}"
  local args=(-fsS -X "$method" "${CF_API}${path}"
              -H "Authorization: Bearer ${CF_API_TOKEN}"
              -H "Content-Type: application/json")
  [ -n "$body" ] && args+=(--data "$body")
  curl "${args[@]}"
}
cf_ok() { jq -e '.success == true' >/dev/null 2>&1; }

# Корневой домен (zone) = последние две метки. Для multi-level TLD (example.co.uk) поправь вручную.
ROOT_DOMAIN="$(echo "$APP_DOMAIN" | awk -F. '{print $(NF-1)"."$NF}')"

# --- Step 2: ранняя валидация (resolve zone) -----------------------------
log "Проверяю токен и зону для $ROOT_DOMAIN"
ZONE_RESP="$(cf GET "/zones?name=${ROOT_DOMAIN}")" || die "CF API недоступен / токен невалиден"
echo "$ZONE_RESP" | cf_ok || die "CF API вернул ошибку: $(echo "$ZONE_RESP" | jq -c '.errors')"
ZONE_ID="$(echo "$ZONE_RESP" | jq -r '.result[0].id // empty')"
ACCOUNT_ID="$(echo "$ZONE_RESP" | jq -r '.result[0].account.id // empty')"
[ -n "$ZONE_ID" ]    || die "Зона $ROOT_DOMAIN не найдена в этом аккаунте. Делегируй домен на Cloudflare NS."
[ -n "$ACCOUNT_ID" ] || die "Не удалось определить account id"

# --- Step 3: туннель (idempotent) ----------------------------------------
log "Создаю/переиспользую туннель $TUNNEL_NAME"
LIST="$(cf GET "/accounts/${ACCOUNT_ID}/cfd_tunnel?name=${TUNNEL_NAME}&is_deleted=false")"
TUNNEL_ID="$(echo "$LIST" | jq -r '.result[0].id // empty')"
if [ -z "$TUNNEL_ID" ]; then
  CREATE="$(cf POST "/accounts/${ACCOUNT_ID}/cfd_tunnel" \
            "{\"name\":\"${TUNNEL_NAME}\",\"config_src\":\"cloudflare\"}")"
  echo "$CREATE" | cf_ok || die "Не удалось создать туннель: $(echo "$CREATE" | jq -c '.errors')"
  TUNNEL_ID="$(echo "$CREATE" | jq -r '.result.id')"
fi
TUNNEL_TOKEN="$(cf GET "/accounts/${ACCOUNT_ID}/cfd_tunnel/${TUNNEL_ID}/token" | jq -r '.result')"
[ -n "$TUNNEL_TOKEN" ] && [ "$TUNNEL_TOKEN" != "null" ] || die "Не удалось получить tunnel token"

log "Настраиваю ingress туннеля → http://app:8000"
cf PUT "/accounts/${ACCOUNT_ID}/cfd_tunnel/${TUNNEL_ID}/configurations" \
   "{\"config\":{\"ingress\":[{\"hostname\":\"${APP_DOMAIN}\",\"service\":\"http://app:8000\"},{\"service\":\"http_status:404\"}]}}" \
   | cf_ok || die "Не удалось задать ingress"

log "Создаю/обновляю DNS CNAME $APP_DOMAIN"
CNAME_CONTENT="${TUNNEL_ID}.cfargotunnel.com"
EXISTING="$(cf GET "/zones/${ZONE_ID}/dns_records?name=${APP_DOMAIN}&type=CNAME")"
REC_ID="$(echo "$EXISTING" | jq -r '.result[0].id // empty')"
DNS_BODY="{\"type\":\"CNAME\",\"name\":\"${APP_DOMAIN}\",\"content\":\"${CNAME_CONTENT}\",\"proxied\":true}"
if [ -n "$REC_ID" ]; then
  cf PUT "/zones/${ZONE_ID}/dns_records/${REC_ID}" "$DNS_BODY" | cf_ok || die "Не удалось обновить DNS"
else
  cf POST "/zones/${ZONE_ID}/dns_records" "$DNS_BODY" | cf_ok || die "Не удалось создать DNS"
fi

# --- Step 4: .env (не перетираем существующий) ---------------------------
if [ -f .env ]; then
  log ".env уже есть — обновляю TUNNEL_TOKEN/CORS_ORIGINS/APP_DOMAIN, SECRET_KEY сохраняю"
  tmp="$(mktemp)"
  grep -v -E '^(TUNNEL_TOKEN|CORS_ORIGINS|APP_DOMAIN)=' .env > "$tmp" || true
  {
    echo "CORS_ORIGINS=https://${APP_DOMAIN}"
    echo "APP_DOMAIN=${APP_DOMAIN}"
    echo "TUNNEL_TOKEN=${TUNNEL_TOKEN}"
  } >> "$tmp"
  mv "$tmp" .env
  chmod 600 .env
else
  log "Генерирую .env"
  cat > .env <<EOF
SECRET_KEY=$(openssl rand -hex 32)
CORS_ORIGINS=https://${APP_DOMAIN}
APP_DOMAIN=${APP_DOMAIN}
TUNNEL_TOKEN=${TUNNEL_TOKEN}
EOF
  chmod 600 .env
fi

# --- Step 5: (опц.) Cloudflare Access ------------------------------------
if [ "$ENABLE_ACCESS" -eq 1 ]; then
  read -rp "Email'ы для Access (через запятую): " ACCESS_EMAILS
  log "Настраиваю Cloudflare Access для $APP_DOMAIN"
  APP_RESP="$(cf POST "/accounts/${ACCOUNT_ID}/access/apps" \
    "{\"name\":\"NaturalskWeb\",\"domain\":\"${APP_DOMAIN}\",\"type\":\"self_hosted\",\"session_duration\":\"24h\"}")"
  echo "$APP_RESP" | cf_ok || die "Не удалось создать Access app: $(echo "$APP_RESP" | jq -c '.errors')"
  ACCESS_APP_ID="$(echo "$APP_RESP" | jq -r '.result.id // empty')"
  [ -n "$ACCESS_APP_ID" ] || die "Не удалось определить Access app id"
  INCLUDE="$(echo "$ACCESS_EMAILS" | tr ',' '\n' | sed 's/^ *//;s/ *$//' \
            | jq -R '{email:{email:.}}' | jq -s '.')"
  cf POST "/accounts/${ACCOUNT_ID}/access/apps/${ACCESS_APP_ID}/policies" \
    "{\"name\":\"allow-listed-emails\",\"decision\":\"allow\",\"include\":${INCLUDE}}" \
    | cf_ok || die "Не удалось создать Access policy"
fi

# --- Step 6: поднять стек ------------------------------------------------
log "Собираю и поднимаю стек (первый build долгий — torch + libreoffice)"
docker compose build
docker compose up -d

log "Готово. Приложение: https://${APP_DOMAIN}"
log "Стартовый superadmin-пароль появится в: data/initial_admin_password.txt (после старта app)"
log "Логи: docker compose logs -f app"
