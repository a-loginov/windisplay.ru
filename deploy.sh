#!/usr/bin/env bash
#
# Деплой panel.windisplay.ru
#
# Режимы работы:
#   1) ПЕРВЫЙ ЗАПУСК (полная настройка сервера):
#      - устанавливает python, nginx, docker, postgresql (если их нет)
#      - клонирует/обновляет репозиторий в /opt/windisplay
#      - настраивает .env, виртуальное окружение и запускает приложение
#      - подключает домен panel.windisplay.ru и выпускает SSL-сертификат
#   2) ОБНОВЛЕНИЕ (когда сервер уже настроен):
#      - просто подтягивает изменения из git и перезапускает сервер
#
# Использование:  sudo bash deploy.sh
#
# Перед первым запуском:
#   - на DNS домена panel.windisplay.ru должна указывать A-запись на IP сервера
#   - на сервере должен лежать файл конфигурации .env

set -euo pipefail

# ---------------------------------------------------------------------------
# Параметры
# ---------------------------------------------------------------------------
DOMAIN="panel.windisplay.ru"
APP_DIR="/opt/windisplay"
APP_SERVICE="windisplay"
DEFAULT_ENV_PATH="${APP_DIR}/.env"
VENV_DIR="${APP_DIR}/venv"
APP_PORT=9019

# Ветка, которую тянем
GIT_BRANCH="main"
# Ремоторий
GIT_REPO="https://github.com/a-loginov/windisplay.ru.git"

# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------
log()  { echo -e "\033[1;32m[deploy]\033[0m $*"; }
warn() { echo -e "\033[1;33m[warn]\033[0m $*"; }
die()  { echo -e "\033[1;31m[error]\033[0m $*" >&2; exit 1; }

need_root() {
    if [[ "$(id -u)" -ne 0 ]]; then
        die "Запустите скрипт от root:  sudo bash deploy.sh"
    fi
}

# Проверка наличия пакета
package_installed() { dpkg -s "$1" >/dev/null 2>&1; }

# Установка, если ещё не установлено
ensure_apt_pkg() {
    local pkg="$1"
    if package_installed "$pkg"; then
        log "Пакет $pkg уже установлен"
    else
        log "Устанавливаю $pkg ..."
        DEBIAN_FRONTEND=noninteractive apt-get install -y "$pkg"
        log "$pkg установлен"
    fi
}

# Проверка наличия команды
cmd_exists() { command -v "$1" >/dev/null 2>&1; }

# ---------------------------------------------------------------------------
# Обновление кода приложения (общий для обоих режимов)
# ---------------------------------------------------------------------------
update_code() {
    log "Подтягиваю изменения из git ($GIT_BRANCH) ..."
    cd "$APP_DIR"
    git fetch --all --prune
    git checkout "$GIT_BRANCH"
    git pull origin "$GIT_BRANCH" --ff-only
    log "Код обновлён до commit: $(git rev-parse --short HEAD)"
}

# Переустановка зависимостей Python (при изменении requirements.txt)
update_requirements() {
    log "Обновляю зависимости Python ..."
    cd "$APP_DIR"
    "$VENV_DIR/bin/pip" install -r requirements.txt
}

# Перезапуск приложения через systemd
restart_app() {
    log "Перезапускаю сервис $APP_SERVICE ..."
    systemctl daemon-reload
    systemctl enable --now "$APP_SERVICE"
    systemctl restart "$APP_SERVICE"
    log "Сервис перезапущен"
}

reload_nginx() {
    log "Перезагружаю nginx ..."
    nginx -t
    systemctl reload nginx
}

# ---------------------------------------------------------------------------
# ПОЛНАЯ НАСТРОЙКА (первый запуск)
# ---------------------------------------------------------------------------
setup_full() {
    log "=== Полная настройка сервера началась ==="

    # Обновляем список пакетов
    log "Обновляю список пакетов ..."
    apt-get update
    apt-get install -y apt-transport-https ca-certificates curl software-properties-common \
        gnupg lsb-release git

    # --- Python ---
    if cmd_exists python3 && python3 -V >/dev/null 2>&1; then
        log "Python уже установлен: $(python3 -V)"
    else
        log "Python не найден, устанавливаю ..."
        ensure_apt_pkg python3
    fi
    ensure_apt_pkg python3-pip
    ensure_apt_pkg python3-venv

    # --- nginx ---
    if cmd_exists nginx; then
        log "nginx уже установлен"
    else
        log "nginx не найден, устанавливаю ..."
        ensure_apt_pkg nginx
    fi

    # --- Docker ---
    if cmd_exists docker; then
        log "Docker уже установлен"
    else
        log "Docker не найден, устанавливаю ..."
        curl -fsSL https://get.docker.com | sh
        systemctl enable --now docker
        log "Docker установлен"
    fi

    # --- PostgreSQL ---
    install_postgresql

    # --- Расположение кода ---
    log "Обновляю код приложения ..."
    mkdir -p "$APP_DIR"
    if [[ -d "$APP_DIR/.git" ]]; then
        update_code
    else
        cd "$APP_DIR"
        log "Клонирую репозиторий ..."
        git clone "$GIT_REPO" .
        git checkout "$GIT_BRANCH"
    fi

    # --- Скрипты для раздачи прав на .env и статику из gitignore ---
    # Если скрипт запущен из папки проекта — подкладываем недостающие файлы
    if [[ -f "$DEFAULT_ENV_PATH" ]]; then
        log ".env уже существует"
    else
        log ".env не найден. Поместите файл .env в $APP_DIR и запустите скрипт снова."
        warn "Без .env приложение не запустится."
        die "Поместите .env в $APP_DIR и запустите deploy.sh повторно."
    fi

    # --- Виртуальное окружение и зависимости ---
    if [[ ! -d "$VENV_DIR" ]]; then
        log "Создаю виртуальное окружение ..."
        python3 -m venv "$VENV_DIR"
    fi
    update_requirements

    # --- systemd-сервис ---
    install_systemd

    # --- nginx + SSL ---
    setup_nginx_and_ssl

    # --- Запуск ---
    restart_app

    log "=== Полная настройка завершена ==="
    log "Сайт доступен по адресу: https://${DOMAIN}"
}

# ---------------------------------------------------------------------------
# Установка PostgreSQL
# ---------------------------------------------------------------------------
install_postgresql() {
    if systemctl is-active --quiet postgresql 2>/dev/null; then
        log "PostgreSQL уже установлен и работает"
        return
    fi
    if cmd_exists psql; then
        log "PostgreSQL установлен"
    else
        log "PostgreSQL не найден, устанавливаю ..."
        ensure_apt_pkg postgresql postgresql-contrib
    fi
    systemctl enable --now postgresql
    log "PostgreSQL запущен"
}

# ---------------------------------------------------------------------------
# systemd-сервис приложения
# ---------------------------------------------------------------------------
install_systemd() {
    log "Настраиваю systemd-сервис $APP_SERVICE ..."
    cat > "/etc/systemd/system/${APP_SERVICE}.service" <<EOF
[Unit]
Description=Windisplay panel (Flask)
After=network.target postgresql.service

[Service]
Type=simple
User=root
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=$VENV_DIR/bin/gunicorn --workers 3 --bind 127.0.0.1:${APP_PORT} main:app
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
    log "systemd-сервис создан"
}

# ---------------------------------------------------------------------------
# nginx + SSL через certbot
# ---------------------------------------------------------------------------
setup_nginx_and_ssl() {
    log "Настраиваю nginx для домена $DOMAIN ..."

    # Проверка, что DNS указывает на сервер
    log "Проверяю DNS запись для $DOMAIN ..."
    local server_ip
    server_ip="$(curl -4 -s https://api.ipify.org || true)"
    local domain_ip
    domain_ip="$(getent ahostsv4 "$DOMAIN" | awk '{print $1; exit}' 2>/dev/null || true)"
    if [[ -n "$domain_ip" && -n "$server_ip" && "$domain_ip" != "$server_ip" ]]; then
        warn "DNS $DOMAIN ($domain_ip) не совпадает с IP сервера ($server_ip)."
        warn "SSL-сертификат может не выпуститься."
    fi

    # Копируем конфиг проекта в /etc/nginx/conf.d/ (он подключается автоматически)
    local local_conf="$(dirname "$0")/nginx.conf"
    cp "$local_conf" "/etc/nginx/conf.d/${DOMAIN}.conf"

    # Удаляем дефолтный сайт nginx
    rm -f /etc/nginx/sites-enabled/default

    # Пробуем перезагрузить nginx (может падать, пока нет сертификатов в SSL-блоке)
    if nginx -t 2>/dev/null; then
        systemctl reload nginx 2>/dev/null || true
    fi

    # --- Выпуск SSL-сертификата (certbot) ---
    if ! cmd_exists certbot; then
        log "certbot не найден, устанавливаю ..."
        ensure_apt_pkg certbot
        ensure_apt_pkg python3-certbot-nginx
    fi

    if [[ -f "/etc/letsencrypt/live/${DOMAIN}/fullchain.pem" ]]; then
        log "SSL-сертификат уже выпущен"
    else
        log "Выпускаю SSL-сертификат для $DOMAIN ..."
        certbot --nginx -d "$DOMAIN" --redirect --non-interactive \
            --agree-tos --register-unsafely-without-email || {
                warn "Не удалось выпустить сертификат автоматически."
                warn "Запустите вручную: certbot --nginx -d $DOMAIN"
            }
    fi

    reload_nginx
    log "nginx и SSL настроены"
}

# ---------------------------------------------------------------------------
# ОБНОВЛЕНИЕ (сервер уже настроен)
# ---------------------------------------------------------------------------
setup_update() {
    log "=== Режим обновления ==="

    # Переходим в каталог приложения
    cd "$APP_DIR"

    # Считаем старый и новый HEAD
    local old_head
    old_head="$(git rev-parse HEAD 2>/dev/null || true)"

    update_code

    local new_head
    new_head="$(git rev-parse HEAD 2>/dev/null || true)"

    # if requirements changed, reinstall
    if ! git diff --quiet "$old_head" "$new_head" -- requirements.txt; then
        update_requirements
    fi

    restart_app

    if [[ "$old_head" == "$new_head" ]]; then
        log "Изменений в git нет, сервер перезапущен (без изменений кода)"
    else
        log "Код обновлён с $old_head на $new_head"
    fi
}

# ---------------------------------------------------------------------------
# Главная логика
# ---------------------------------------------------------------------------
main() {
    need_root

    echo
    log "Деплой ${DOMAIN}"
    log "Каталог приложения: ${APP_DIR}"
    log "Режим: $([ -d "${APP_DIR}/.git" ] && echo 'обновление' || echo 'полная настройка')"
    echo

    if [[ -d "${APP_DIR}/.git" && -f "/etc/systemd/system/${APP_SERVICE}.service" ]]; then
        # Сервер уже настроен — просто обновляем
        setup_update
    else
        # Полная настройка
        setup_full
    fi

    echo
    log "Готово. https://${DOMAIN}"
}

main "$@"
