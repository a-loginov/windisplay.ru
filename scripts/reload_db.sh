#!/usr/bin/env bash
#
# Сброс/миграция схемы базы данных windisplay.
#
# Использование:  sudo bash scripts/reload_db.sh
#
# Что делает:
#   1. Устанавливает/обновляет зависимости, если нужно (пропуск через флаг --no-install)
#   2. Запускает migrations.migrate() — идемпотентная миграция:
#      - создаёт ВСЕ недостающие таблицы  (db.create_all())
#      - добавляет недостающие колонки в уже существующие таблицы
#        (через ALTER TABLE с проверкой наличия)
#      - строит недостающие индексы
#   3. Печатает итог и при необходимости перезапускает сервис
#
# Флаги:
#   --no-install          не обновлять pip-зависимости
#   --no-restart          не перезапускать сервис windisplay
#   --restart             перезапустить сервис windisplay (по умолчанию выключен)
#   --env <path>          путь к файлу .env (по умолчанию $APP_DIR/.env)
#   --env-file <path>     то же самое, что --env
#   --app-dir <path>      корень проекта с venv и кодом (по умолчанию рядом со скриптом)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(dirname "$SCRIPT_DIR")"
APP_SERVICE="windisplay"

DO_INSTALL=1
DO_RESTART=0
ENV_FILE=""

parse_args() {
    local prev=""
    for arg in "$@"; do
        if [[ "$prev" == "--env" || "$prev" == "--env-file" ]]; then
            ENV_FILE="$arg"
            prev=""
            continue
        fi
        if [[ "$prev" == "--app-dir" ]]; then
            APP_DIR="$arg"
            prev=""
            continue
        fi
        case "$arg" in
            --no-install) DO_INSTALL=0 ;;
            --restart)    DO_RESTART=1 ;;
            --no-restart) DO_RESTART=0 ;;
            --env|--env-file|--app-dir) prev="${arg}" ;;
            *) echo "Неизвестный флаг: $arg"; exit 1 ;;
        esac
    done
    if [[ -n "$prev" ]]; then
        echo "Ошибка: флагу $prev нужно значение"; exit 1
    fi
}
parse_args "$@"

# Если --env не задан — берём рядом с проектом
if [[ -z "$ENV_FILE" ]]; then
    ENV_FILE="$APP_DIR/.env"
fi

log() { echo -e "\033[1;32m[reload_db]\033[0m $*"; }
die() { echo -e "\033[1;31m[error]\033[0m $*" >&2; exit 1; }

need_root() {
    if [[ "$(id -u)" -ne 0 ]]; then
        die "Запустите скрипт от root:  sudo bash $0"
    fi
}

main() {
    need_root

    if [[ ! -f "$ENV_FILE" ]]; then
        die "Файл .env не найден: $ENV_FILE. Укажите путь через --env <path>"
    fi

    if [[ "$DO_INSTALL" -eq 1 && -x "$APP_DIR/venv/bin/pip" ]]; then
        log "Обновляю зависимости Python ..."
        "$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt"
    fi

    if [[ ! -x "$APP_DIR/venv/bin/python" ]]; then
        die "venv не найден в $APP_DIR/venv"
    fi

    # Пути передаются в Python, чтобы .env читался через python-dotenv
    # (source .env в bash небезопасен из-за спецсимволов в значениях).
    log "Запускаю миграцию базы данных ..."
    APP_DIR="$APP_DIR" ENV_FILE="$ENV_FILE" "$APP_DIR/venv/bin/python" - <<'EOF'
import os
import sys

app_dir = os.environ["APP_DIR"]
env_file = os.environ["ENV_FILE"]
if not os.path.isabs(env_file):
    env_file = os.path.join(app_dir, env_file)

sys.path.insert(0, app_dir)

from dotenv import load_dotenv
load_dotenv(env_file)

import sqlalchemy as sa
from sqlalchemy import inspect, text
from db_manager import app, db

# Все модели должны быть импортированы, чтобы попасть в db.metadata
from db_manager import (
    User, OrgInvite, WebAuthnCredential, QrLoginSession,
    ProjectSetting, DailySummary, MediaAsset, Device, PlaylistItem,
)


def sql_literal(value):
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def main_migrate():
    with app.app_context():
        engine = db.engine
        insp = inspect(engine)

        existing_tables = set(insp.get_table_names())
        missing_tables = [
            table.name for table in db.metadata.sorted_tables if table.name not in existing_tables
        ]

        db.create_all()
        print(f"[migrate] Созданы/проверены таблицы. Отсутствовавших ранее: {sorted(missing_tables) or 'нет'}")

        added_columns = []
        with engine.begin() as conn:
            dialect = engine.dialect
            for table in db.metadata.sorted_tables:
                if table.name not in existing_tables:
                    continue  # только что создана — колонки уже на месте
                existing_cols = {c["name"] for c in insp.get_columns(table.name)}
                for col in table.columns:
                    if col.name in existing_cols:
                        continue
                    coltype = col.type.compile(dialect=dialect)
                    ddl = f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {coltype}'
                    # Для NOT NULL без DB-default добавляем DEFAULT, чтобы
                    # существующие строки получили значение (иначе ALTER упадёт).
                    if not col.nullable and not col.server_default:
                        default = None
                        if col.default is not None:
                            default = getattr(col.default, "arg", None)
                        if default is None:
                            default = col.type.python_type() if hasattr(col.type, "python_type") else None
                            if default is not None:
                                try:
                                    default = default()
                                except Exception:
                                    default = None
                        if default is None:
                            default = "" if str(coltype).upper().startswith("VARCHAR") else (0 if "INT" in coltype.upper() else False)
                        ddl += f" DEFAULT {sql_literal(default)}"
                        ddl += " NOT NULL"
                    elif not col.nullable and col.server_default is not None:
                        ddl += " NOT NULL"
                    conn.execute(text(ddl))
                    added_columns.append(f"{table.name}.{col.name}")

        print(f"[migrate] Добавлены колонки: {added_columns or 'нет'}")

        insp2 = inspect(engine)
        all_tables = sorted(insp2.get_table_names())
        print(f"[migrate] Всего таблиц в БД: {len(all_tables)}")
        for t in all_tables:
            print(f"  - {t}")

if __name__ == "__main__":
    main_migrate()
EOF

    if [[ "$DO_RESTART" -eq 1 ]]; then
        log "Перезапускаю сервис $APP_SERVICE ..."
        systemctl daemon-reload
        systemctl restart "$APP_SERVICE"
        log "Сервис перезапущен"
    fi

    log "Готово. Миграция завершена."
}

main "$@"
