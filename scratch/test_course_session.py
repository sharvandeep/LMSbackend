import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import SessionLocal
from app import models

def main():
    db = SessionLocal()
    try:
        course = db.query(models.Course).filter(models.Course.course_id == 7).first()
        if course:
            print(f"Course 7 found: {course.title}")
            print(f"Teacher ID: {course.teacher_id}")
            # Query all teachers
            teachers = db.query(models.User).filter(models.User.role == "teacher").all()
            print("Teachers in DB:")
            for t in teachers:
                print(f"ID: {t.user_id}, Name: {t.full_name}, Email: {t.email}")
        else:
            print("Course 7 NOT found!")
    finally:
        db.close()

if __name__ == "__main__":
    main()
