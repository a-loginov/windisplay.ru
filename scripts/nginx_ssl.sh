#!/usr/bin/env bash
#
# Настройка nginx: поиск SSL-сертификата (Let's Encrypt) и подключение HTTPS
# с принудительным редиректом с http на https.
#
# Использование:  sudo bash scripts/nginx_ssl.sh [домен]
#   домен (необязательно) - по умолчанию panel.windisplay.ru
#
# Что делает:
#   1. Ищет сертификат в /etc/letsencrypt/live/<домен>/fullchain.pem
#   2. Если сертификат найден - генерирует /etc/nginx/conf.d/<домен>.conf
#      с HTTPS-сервером и редиректом HTTP -> HTTPS
#   3. Если сертификат НЕ найден - выдаёт предупреждение и оставляет
#      только HTTP-конфиг, советуя выпустить SSL через certbot.

set -euo pipefail

DOMAIN="${1:-panel.windisplay.ru}"
APP_BACKEND="http://127.0.0.1:9019"
STATIC_DIR="/opt/windisplay/static"
NGINX_CONF="/etc/nginx/conf.d/${DOMAIN}.conf"
LE_DIR="/etc/letsencrypt/live/${DOMAIN}"

log()  { echo -e "\033[1;32m[nginx-ssl]\033[0m $*"; }
warn() { echo -e "\033[1;33m[warn]\033[0m $*"; }
die()  { echo -e "\033[1;31m[error]\033[0m $*" >&2; exit 1; }

need_root() {
    if [[ "$(id -u)" -ne 0 ]]; then
        die "Запустите скрипт от root:  sudo bash $0"
    fi
}

reload_nginx() {
    log "Проверяю конфигурацию nginx ..."
    if nginx -t 2>/dev/null; then
        systemctl reload nginx
        log "nginx перезагружен"
    else
        warn "nginx -t не прошёл. Проверьте конфиг вручную."
    fi
}

# ---------------------------------------------------------------------------
# Поиск SSL-сертификата
# ---------------------------------------------------------------------------
find_ssl() {
    local cert="$LE_DIR/fullchain.pem"
    local key="$LE_DIR/privkey.pem"

    if [[ -f "$cert" && -f "$key" ]]; then
        log "Найден сертификат Let's Encrypt для $DOMAIN:"
        log "  cert: $cert"
        log "  key:  $key"
        SSL_CERT="$cert"
        SSL_KEY="$key"
        return 0
    fi

    # Резервный поиск: полный обход все каталогов letsencrypt
    if [[ -d /etc/letsencrypt/live ]]; then
        log "Сертификата для $DOMAIN нет, ищу любой сертификат в letsencrypt ..."
        for d in /etc/letsencrypt/live/*/; do
            local c="${d}fullchain.pem"
            local k="${d}privkey.pem"
            if [[ -f "$c" && -f "$k" ]]; then
                SSL_CERT="$c"
                SSL_KEY="$k"
                log "Найден подходящий сертификат: ${d%/}"
                return 0
            fi
        done
    fi

    return 1
}

# ---------------------------------------------------------------------------
# Генерация конфига с HTTPS и редиректом
# ---------------------------------------------------------------------------
write_config_https() {
    log "Генерирую HTTPS-конфиг: $NGINX_CONF"
    cat > "$NGINX_CONF" <<EOF
# Конфигурация nginx для ${DOMAIN} (HTTPS + редирект с HTTP)
# Сгенерировано скриптом scripts/nginx_ssl.sh

# HTTP -> HTTPS редирект
server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN};

    return 301 https://\$host\$request_uri;
}

# HTTPS-сервер
server {
    listen 443 ssl;
    listen [::]:443 ssl;
    http2 on;

    server_name ${DOMAIN};

    ssl_certificate     ${SSL_CERT};
    ssl_certificate_key ${SSL_KEY};
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;

    # Адрес приложения (gunicorn)
    location / {
        proxy_pass ${APP_BACKEND};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 300s;
    }

    location /static/ {
        alias ${STATIC_DIR}/;
        expires 30d;
    }
}
EOF
    log "Конфиг записан"
}

# ---------------------------------------------------------------------------
# Запасной вариант: только HTTP (без сертификата)
# ---------------------------------------------------------------------------
write_config_http() {
    warn "SSL-сертификат для $DOMAIN не найден."
    warn "Выпустите его через certbot:  certbot --nginx -d $DOMAIN"
    warn "или добавьте свои сертификаты в $LE_DIR"

    log "Оставляю HTTP-конфиг (без редиректа на https)"
    cat > "$NGINX_CONF" <<EOF
# Конфигурация nginx для ${DOMAIN} (только HTTP, без SSL)
# SSL-сертификат не найден - выпустите через certbot и запустите этот скрипт снова.

server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN};

    # Адрес приложения (gunicorn)
    location / {
        proxy_pass ${APP_BACKEND};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 300s;
    }

    location /static/ {
        alias ${STATIC_DIR}/;
        expires 30d;
    }
}
EOF
    log "HTTP-конфиг записан"
}

# ---------------------------------------------------------------------------
# Главная логика
# ---------------------------------------------------------------------------
main() {
    need_root

    echo
    log "Настраиваю nginx с SSL для домена: $DOMAIN"

    if find_ssl; then
        write_config_https
    else
        write_config_http
    fi

    reload_nginx

    echo
    log "Готово."
    if [[ -n "${SSL_CERT:-}" ]]; then
        log "Сайт доступен по адресу: https://${DOMAIN}"
        log "HTTP автоматически редиректит на HTTPS"
    else
        log "Сертификат не найден, сайт доступен по адресу: http://${DOMAIN}"
    fi
}

main "$@"
