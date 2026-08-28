from db_manager import app, db, User

with app.app_context():
    db.create_all()
    print("Таблица users создана (или уже существует)")
