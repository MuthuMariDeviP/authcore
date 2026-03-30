import sqlite3

DB_PATH = "../authcore_sms.db"

def init_db():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    with open("models.sql", "r") as f:
        cur.executescript(f.read())

    con.commit()
    con.close()
    print("Database initialized successfully")

if __name__ == "__main__":
    init_db()
    