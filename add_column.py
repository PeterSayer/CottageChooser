import sqlite3
from pathlib import Path
import time

# Get the database path
DB_PATH = Path(__file__).resolve().parent / "data.db"

max_retries = 5
retry_count = 0

while retry_count < max_retries:
    try:
        # Connect to the database with a timeout
        conn = sqlite3.connect(DB_PATH, timeout=20)
        cursor = conn.cursor()
        break
    except sqlite3.OperationalError as e:
        if "database is locked" in str(e):
            print(f"Database is locked, retrying... ({retry_count + 1}/{max_retries})")
            retry_count += 1
            time.sleep(2)
            if retry_count == max_retries:
                print("Could not access database after multiple retries. Please stop any running Flask application first.")
                exit(1)
        else:
            raise e

try:
    # Check if column exists first to avoid errors
    cursor.execute("PRAGMA table_info(cottages)")
    columns = [col[1] for col in cursor.fetchall()]
    
    if 'ai_review_summary' not in columns:
        # Add the new column
        cursor.execute("ALTER TABLE cottages ADD COLUMN ai_review_summary TEXT;")
        conn.commit()
        print("Successfully added ai_review_summary column")
    else:
        print("Column ai_review_summary already exists")

except Exception as e:
    print(f"Error: {e}")
finally:
    conn.close()