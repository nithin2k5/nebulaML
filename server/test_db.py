import mysql.connector
from app.core.config import settings

def test_connection():
    try:
        print(f"Connecting to {settings.db_host}:{settings.db_port} as {settings.db_user}...")
        connection = mysql.connector.connect(
            host=settings.db_host,
            port=settings.db_port,
            user=settings.db_user,
            password=settings.db_password
        )
        print("✓ Successfully connected to MySQL server!")
        connection.close()
    except Exception as e:
        print(f"✗ Failed to connect: {e}")

if __name__ == "__main__":
    test_connection()
