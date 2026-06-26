import datetime
from app.database import SessionLocal, engine
from app import models, security

def seed_database():
    db = SessionLocal()
    try:
        print("Resetting database (dropping and recreating all tables)...")
        models.Base.metadata.drop_all(bind=engine)
        models.Base.metadata.create_all(bind=engine)
        print("Database tables successfully recreated.")

        # 1. Seed Branches
        branches_data = ["CSE", "AI&DS", "AI&ML", "IT", "ECE", "EEE", "ME"]
        branches = {}
        for b_name in branches_data:
            branch = models.Branch(name=b_name)
            db.add(branch)
            db.commit()
            db.refresh(branch)
            print(f"Created Branch: {b_name}")
            branches[b_name] = branch

        # 2. Seed Semesters
        semesters_db = {}
        for i in range(1, 9):
            status = "Active" if i <= 4 else "Planned"
            sem = models.Semester(number=i, name=f"Semester {i}", status=status)
            db.add(sem)
            db.commit()
            db.refresh(sem)
            print(f"Created Semester: {sem.name} ({status})")
            semesters_db[i] = sem

        # 3. Seed Settings
        setting_key = "teacher_capacity"
        setting = models.Setting(setting_key=setting_key, setting_value="7")
        db.add(setting)
        db.commit()
        print("Created Global Setting: teacher_capacity = 7")

        # 4. Seed Admin (Required for admin dashboard access and course allocation)
        hashed_admin_pass = security.get_password_hash("admin123")
        admin = models.User(
            full_name="System Admin",
            email="admin@lms.com",
            password_hash=hashed_admin_pass,
            role="admin",
            branch_id=branches["CSE"].branch_id,
            semester_id=None
        )
        db.add(admin)
        db.commit()
        print("Created Admin User: System Admin (admin@lms.com)")

        # 5. Mapped Semester-wise Courses (Complete Curriculum)
        curriculum = {
            "CSE": {
                1: ["Mathematics I", "Engineering Physics", "Programming in C", "Basic Electrical Engineering", "English Communication"],
                2: ["Mathematics II", "Data Structures", "Digital Logic Design", "Environmental Science", "Python Programming"],
                3: ["Object Oriented Programming", "Database Management Systems", "Operating Systems", "Computer Organization", "Discrete Mathematics"],
                4: ["Design and Analysis of Algorithms", "Software Engineering", "Web Technologies", "Computer Networks", "Probability and Statistics"]
            },
            "AI&DS": {
                1: ["Mathematics I", "Programming in C", "Engineering Physics", "English Communication"],
                2: ["Python Programming", "Statistics", "Data Structures", "Environmental Science"],
                3: ["DBMS", "Machine Learning Fundamentals", "Data Analytics", "OOP"],
                4: ["Deep Learning", "Data Mining", "Big Data Analytics", "Computer Networks"]
            },
            "AI&ML": {
                1: ["Mathematics I", "Programming in C", "Physics"],
                2: ["Python", "Data Structures", "Statistics"],
                3: ["Machine Learning", "DBMS", "OOP"],
                4: ["Deep Learning", "Natural Language Processing", "Computer Vision"]
            },
            "IT": {
                1: ["Mathematics I", "Programming in C", "Physics"],
                2: ["Data Structures", "Python", "Statistics"],
                3: ["DBMS", "Operating Systems", "OOP"],
                4: ["Web Technologies", "Software Engineering", "Computer Networks"]
            },
            "ECE": {
                1: ["Mathematics I", "Physics", "Basic Electronics"],
                2: ["Digital Electronics", "Signals and Systems", "Mathematics II"],
                3: ["Analog Circuits", "Microprocessors", "Communication Systems"],
                4: ["Embedded Systems", "VLSI Design", "Digital Signal Processing"]
            },
            "EEE": {
                1: ["Mathematics I", "Physics", "Basic Electrical Engineering"],
                2: ["Circuit Theory", "Electrical Machines", "Mathematics II"],
                3: ["Power Systems", "Control Systems", "Electrical Measurements"],
                4: ["Power Electronics", "Renewable Energy Systems", "Smart Grids"]
            },
            "ME": {
                1: ["Mathematics I", "Engineering Mechanics", "Physics"],
                2: ["Thermodynamics", "Engineering Drawing", "Materials Science"],
                3: ["Fluid Mechanics", "Manufacturing Processes", "Strength of Materials"],
                4: ["Heat Transfer", "Machine Design", "CAD/CAM"]
            }
        }

        seeded_courses_count = 0
        for b_name, semesters in curriculum.items():
            branch_id = branches[b_name].branch_id
            for sem_num, course_list in semesters.items():
                for c_name in course_list:
                    course = models.Course(
                        title=c_name,
                        description=f"Standard syllabus course of {c_name} for {b_name} department.",
                        branch_id=branch_id,
                        semester_id=semesters_db[sem_num].semester_id,
                        teacher_id=None # Nullable: freshly registered teachers will be assigned later
                    )
                    db.add(course)
                    seeded_courses_count += 1
        
        db.commit()
        print(f"Successfully seeded {seeded_courses_count} department curriculum courses (no faculty assigned yet).")
        print("Database fully reset to a clean state and seeded successfully!")
    except Exception as e:
        db.rollback()
        print(f"Error during seeding: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    seed_database()
