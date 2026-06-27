import os
import sys

# Ensure backend directory is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import Base, engine
from app import models

def main():
    print("Initializing ClassroomSession table creation...")
    try:
        # This will safely check which tables exist, and only create missing ones (i.e. classroom_sessions)
        Base.metadata.create_all(bind=engine)
        print("Success: ClassroomSession table successfully created (or already exists) in PostgreSQL.")
    except Exception as e:
        print(f"Error creating table: {e}")

if __name__ == "__main__":
    main()
