import os
from dotenv import load_dotenv

# Загружаем переменные из .env файла.
# Это позволяет запускать приложение локально без Docker,
# прочитав конфигурацию из файла .env.
load_dotenv()




# --- База данных ---
# os.environ[...] выбросит ошибку, если переменная не найдена,
# что предотвратит запуск с неполной конфигурацией.
POSTGRESQL_HOST=os.environ["POSTGRESQL_HOST"]
POSTGRESQL_PORT=os.environ["POSTGRESQL_PORT"]
POSTGRESQL_USER=os.environ["POSTGRESQL_USER"]
POSTGRESQL_PASSWORD=os.environ["POSTGRESQL_PASSWORD"]
POSTGRESQL_DBNAME=os.environ["POSTGRESQL_DBNAME"]





# --- Секретный ключ Flask ---
SECRET_KEY = os.environ['SECRET_KEY']



# Yandex ID #
ClientID=os.environ["ClientID"]
Client_secret=os.environ["Client secret"]



# --- Timeweb AI (AI-агент) ---
OPENAI_URL = os.environ["OPENAI_URL"]
API_KEY = os.environ["API_KEY"]



# --- Админ-панель ---
ADMIN_MASTER_PASSWORD = os.environ["ADMIN_MASTER_PASSWORD"]