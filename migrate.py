import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from app.models import Base as ModelsBase

# Load environment variables
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:admin123@localhost:5432/lms_db")

def run_migration():
    print(f"Connecting to database at: {DATABASE_URL}")
    engine = create_engine(DATABASE_URL)
    
    with engine.connect() as conn:
        # 1. Alter users table
        print("Checking/updating 'users' table...")
        try:
            # Check if columns exist
            res_verified = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='users' AND column_name='is_verified'")).fetchone()
            if not res_verified:
                print("Adding column 'is_verified' to 'users'...")
                conn.execute(text("ALTER TABLE users ADD COLUMN is_verified BOOLEAN DEFAULT FALSE NOT NULL"))
                
            res_token = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='users' AND column_name='verification_token'")).fetchone()
            if not res_token:
                print("Adding column 'verification_token' to 'users'...")
                conn.execute(text("ALTER TABLE users ADD COLUMN verification_token VARCHAR(255)"))
                
            # Set existing users as verified so they don't get locked out!
            print("Marking existing users as verified...")
            conn.execute(text("UPDATE users SET is_verified = TRUE"))
            
            # Commit the transaction
            conn.execute(text("COMMIT"))
        except Exception as e:
            print(f"Error migrating 'users' table: {e}")

        # 2. Alter courses table
        print("Checking/updating 'courses' table...")
        try:
            res_archived = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='courses' AND column_name='is_archived'")).fetchone()
            if not res_archived:
                print("Adding column 'is_archived' to 'courses'...")
                conn.execute(text("ALTER TABLE courses ADD COLUMN is_archived BOOLEAN DEFAULT FALSE NOT NULL"))
                conn.execute(text("COMMIT"))
        except Exception as e:
            print(f"Error migrating 'courses' table: {e}")
            
    # 3. Create all new tables using SQLAlchemy
    print("Creating any new tables defined in models...")
    try:
        ModelsBase.metadata.create_all(bind=engine)
        print("SQLAlchemy create_all completed successfully.")
    except Exception as e:
        print(f"Error creating new tables: {e}")

    print("Migration completed successfully!")

if __name__ == "__main__":
    run_migration()
