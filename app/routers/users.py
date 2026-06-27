from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from ..database import get_db
from .. import models, schemas, security
from .auth import get_current_user, require_admin

router = APIRouter(prefix="/users", tags=["Users"])

def get_student_avg_grade(student_id: int, db: Session) -> float:
    # Get all graded submissions for assignments
    submissions = db.query(models.Submission).filter(
        models.Submission.student_id == student_id,
        models.Submission.marks.isnot(None)
    ).all()
    
    # Get all quiz attempts
    quiz_attempts = db.query(models.QuizAttempt).filter(
        models.QuizAttempt.student_id == student_id,
        models.QuizAttempt.score.isnot(None)
    ).all()
    
    total_percent = 0.0
    count = 0
    
    for sub in submissions:
        assignment = sub.assignment
        if assignment and assignment.total_marks and assignment.total_marks > 0:
            total_percent += (float(sub.marks) / float(assignment.total_marks)) * 100.0
            count += 1
            
    for attempt in quiz_attempts:
        quiz = attempt.quiz
        if quiz and quiz.total_marks and quiz.total_marks > 0:
            total_percent += (float(attempt.score) / float(quiz.total_marks)) * 100.0
            count += 1
            
    if count > 0:
        return round(total_percent / count, 1)
    return 0.0

def map_user(user: models.User, db: Session = None) -> dict:
    if not user:
        return None
    
    avg_grade = 0.0
    if user.role == "student" and db:
        avg_grade = get_student_avg_grade(user.user_id, db)
        
    return {
        "user_id": user.user_id,
        "full_name": user.full_name,
        "email": user.email,
        "role": user.role,
        "branch_id": user.branch_id,
        "semester_id": user.semester_id,
        "branch": user.branch.name if user.branch else None,
        "semester_name": user.semester.name if user.semester else None,
        "average_grade": avg_grade,
        "created_at": user.created_at,
        "updated_at": user.updated_at
    }

@router.get("/me", response_model=schemas.UserResponse)
def get_me(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    return map_user(current_user, db)

# ----------------- ADMIN ONLY CRUD ENDPOINTS -----------------

@router.get("", response_model=List[schemas.UserResponse])
def get_all_users(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    users = db.query(models.User).order_by(models.User.user_id).all()
    return [map_user(u, db) for u in users]

@router.get("/{user_id}", response_model=schemas.UserResponse)
def get_user_by_id(user_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    user = db.query(models.User).filter(models.User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return map_user(user, db)

@router.post("", response_model=schemas.UserResponse, status_code=status.HTTP_201_CREATED)
def create_user_account(payload: schemas.UserRegister, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    # Check if email is already registered
    db_user = db.query(models.User).filter(models.User.email == payload.email).first()
    if db_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email is already registered")
        
    # Verify branch exists
    branch = db.query(models.Branch).filter(models.Branch.branch_id == payload.branch_id).first()
    if not branch:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid branch_id specified")
        
    role = payload.role or "student"
    if role not in ["student", "teacher", "admin"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid role specified")
        
    semester_id = None
    if role == "student":
        if not payload.semester_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="semester_id is required for student role")
        semester = db.query(models.Semester).filter(models.Semester.semester_id == payload.semester_id).first()
        if not semester:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid semester_id specified")
        semester_id = payload.semester_id
        
    hashed_password = security.get_password_hash(payload.password)
    new_user = models.User(
        full_name=payload.full_name,
        email=payload.email,
        password_hash=hashed_password,
        role=role,
        branch_id=payload.branch_id,
        semester_id=semester_id,
        is_verified=True
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    # ----------------- STUDENT ONLY: TEACHER ALLOCATION & BATCHING LOGIC -----------------
    if role == "student":
        capacity_setting = db.query(models.Setting).filter(models.Setting.setting_key == "teacher_capacity").first()
        capacity = int(capacity_setting.setting_value) if capacity_setting else 7

        teachers = db.query(models.User).filter(
            models.User.branch_id == new_user.branch_id,
            models.User.role == "teacher"
        ).all()
        
        if teachers:
            assigned_batch = None
            for teacher in teachers:
                batch = db.query(models.Batch).filter(
                    models.Batch.branch_id == new_user.branch_id,
                    models.Batch.semester_id == new_user.semester_id,
                    models.Batch.teacher_id == teacher.user_id
                ).first()
                
                if batch:
                    student_count = db.query(models.Enrollment.student_id).filter(
                        models.Enrollment.batch_id == batch.batch_id
                    ).distinct().count()
                    
                    if student_count < capacity:
                        assigned_batch = batch
                        break

            if not assigned_batch:
                selected_teacher = None
                min_students = float('inf')
                
                for teacher in teachers:
                    batch = db.query(models.Batch).filter(
                        models.Batch.branch_id == new_user.branch_id,
                        models.Batch.semester_id == new_user.semester_id,
                        models.Batch.teacher_id == teacher.user_id
                    ).first()
                    
                    if not batch:
                        selected_teacher = teacher
                        break
                    else:
                        student_count = db.query(models.Enrollment.student_id).filter(
                            models.Enrollment.batch_id == batch.batch_id
                        ).distinct().count()
                        if student_count < min_students:
                            min_students = student_count
                            selected_teacher = teacher
                            
                assigned_batch = models.Batch(
                    branch_id=new_user.branch_id,
                    semester_id=new_user.semester_id,
                    teacher_id=selected_teacher.user_id
                )
                db.add(assigned_batch)
                db.commit()
                db.refresh(assigned_batch)

            courses = db.query(models.Course).filter(
                models.Course.branch_id == new_user.branch_id,
                models.Course.semester_id == new_user.semester_id
            ).all()
            
            for course in courses:
                enrollment = models.Enrollment(
                    student_id=new_user.user_id,
                    course_id=course.course_id,
                    batch_id=assigned_batch.batch_id
                )
                db.add(enrollment)
            
            db.commit()
            
    return map_user(new_user, db)

@router.put("/{user_id}", response_model=schemas.UserResponse)
def update_user_account(user_id: int, payload: schemas.UserRegister, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    user = db.query(models.User).filter(models.User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        
    # Verify branch exists
    branch = db.query(models.Branch).filter(models.Branch.branch_id == payload.branch_id).first()
    if not branch:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid branch_id specified")
        
    role = payload.role or user.role
    if role not in ["student", "teacher", "admin"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid role specified")
        
    semester_id = None
    if role == "student":
        if not payload.semester_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="semester_id is required for student role")
        semester = db.query(models.Semester).filter(models.Semester.semester_id == payload.semester_id).first()
        if not semester:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid semester_id specified")
        semester_id = payload.semester_id
        
    user.full_name = payload.full_name
    user.email = payload.email
    if payload.password:
        user.password_hash = security.get_password_hash(payload.password)
    user.branch_id = payload.branch_id
    user.semester_id = semester_id
    user.role = role
    
    db.commit()
    db.refresh(user)
    return map_user(user, db)

@router.delete("/{user_id}", status_code=status.HTTP_200_OK)
def delete_user_account(user_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    user = db.query(models.User).filter(models.User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        
    # Clean up student enrollments, submissions, quiz attempts, activity logs, notifications
    db.query(models.Enrollment).filter(models.Enrollment.student_id == user_id).delete()
    db.query(models.Submission).filter(models.Submission.student_id == user_id).delete()
    db.query(models.QuizAttempt).filter(models.QuizAttempt.student_id == user_id).delete()
    db.query(models.ActivityLog).filter(models.ActivityLog.user_id == user_id).delete()
    db.query(models.Notification).filter(models.Notification.user_id == user_id).delete()
    db.query(models.Certificate).filter(models.Certificate.student_id == user_id).delete()
    db.query(models.Review).filter(models.Review.student_id == user_id).delete()
    
    # If teacher, also clean up batches or verify they have no active courses
    if user.role == "teacher":
        db.query(models.Batch).filter(models.Batch.teacher_id == user_id).delete()
        courses_count = db.query(models.Course).filter(models.Course.teacher_id == user_id).count()
        if courses_count > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot delete teacher. They are teaching {courses_count} courses. Reassign courses first."
            )
        
    db.delete(user)
    db.commit()
    return {"message": "deleted"}
