from db_manager import app, db

with app.app_context():
    db.create_all()
    print("Таблицы созданы (или уже существуют): users, media_assets, devices, playlist_items")