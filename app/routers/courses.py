from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List, Optional
import os
import shutil

from ..database import get_db
from .. import models, schemas
from .auth import get_current_user, require_admin, require_teacher

router = APIRouter(tags=["Courses & Modules"])

# Helper to check if user has access to a course (admin or assigned teacher or enrolled student)
def check_course_access(course_id: int, user: models.User, db: Session):
    course = db.query(models.Course).filter(models.Course.course_id == course_id).first()
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
        
    if user.role == "admin":
        return course
    elif user.role == "teacher":
        if course.teacher_id == user.user_id:
            return course
    elif user.role == "student":
        # Check enrollment
        enrollment = db.query(models.Enrollment).filter(
            models.Enrollment.student_id == user.user_id,
            models.Enrollment.course_id == course_id
        ).first()
        if enrollment:
            return course
            
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this course")

# ----------------- COURSE ENDPOINTS -----------------

def get_student_course_progress(student_id: int, course_id: int, db: Session) -> dict:
    # 1. Modules completed (student downloaded/viewed all materials in the module)
    modules = db.query(models.Module).filter(models.Module.course_id == course_id).all()
    modules_total = len(modules)
    modules_completed = 0
    
    for m in modules:
        materials = m.materials
        if not materials:
            # If no materials, consider it completed by default
            modules_completed += 1
            continue
            
        material_ids = [mat.material_id for mat in materials]
        # Check if student has downloaded all of them
        downloaded_count = db.query(models.DownloadHistory).filter(
            models.DownloadHistory.student_id == student_id,
            models.DownloadHistory.material_id.in_(material_ids)
        ).distinct(models.DownloadHistory.material_id).count()
        
        if downloaded_count >= len(materials):
            modules_completed += 1
            
    # 2. Assignments
    assignments = db.query(models.Assignment).filter(models.Assignment.course_id == course_id).all()
    assignments_total = len(assignments)
    assignment_ids = [a.assignment_id for a in assignments]
    assignments_submitted = 0
    if assignment_ids:
        assignments_submitted = db.query(models.Submission).filter(
            models.Submission.student_id == student_id,
            models.Submission.assignment_id.in_(assignment_ids)
        ).count()
        
    # 3. Quizzes
    quizzes = db.query(models.Quiz).filter(models.Quiz.course_id == course_id).all()
    quizzes_total = len(quizzes)
    quiz_ids = [q.quiz_id for q in quizzes]
    quizzes_attempted = 0
    if quiz_ids:
        quizzes_attempted = db.query(models.QuizAttempt).filter(
            models.QuizAttempt.student_id == student_id,
            models.QuizAttempt.quiz_id.in_(quiz_ids)
        ).count()
        
    # 4. Attendance
    attendance_records = db.query(models.Attendance).filter(
        models.Attendance.student_id == student_id,
        models.Attendance.course_id == course_id
    ).all()
    
    attendance_total = len(attendance_records)
    attendance_present = sum(1 for r in attendance_records if r.status == "Present")
    attendance_percentage = (attendance_present / attendance_total * 100) if attendance_total > 0 else 100.0
    
    # 5. Overall Completion Percentage
    ratios = []
    if modules_total > 0:
        ratios.append(modules_completed / modules_total)
    if assignments_total > 0:
        ratios.append(assignments_submitted / assignments_total)
    if quizzes_total > 0:
        ratios.append(quizzes_attempted / quizzes_total)
        
    overall_progress = (sum(ratios) / len(ratios) * 100) if ratios else 0.0
    
    # Cache completion_pct in enrollment table
    try:
        enrollment = db.query(models.Enrollment).filter(
            models.Enrollment.student_id == student_id,
            models.Enrollment.course_id == course_id
        ).first()
        if enrollment:
            enrollment.completion_pct = overall_progress
            db.commit()
    except Exception:
        db.rollback()
        
    return {
        "progress": round(overall_progress, 1),
        "modules_completed": modules_completed,
        "modules_total": modules_total,
        "assignments_submitted": assignments_submitted,
        "assignments_total": assignments_total,
        "quizzes_attempted": quizzes_attempted,
        "quizzes_total": quizzes_total,
        "attendance_percentage": round(attendance_percentage, 1)
    }

def map_course(course: models.Course, progress: float = 0.0, progress_details: dict = None) -> dict:
    if not course:
        return None
        
    details = progress_details or {
        "modules_completed": 0,
        "modules_total": 0,
        "assignments_submitted": 0,
        "assignments_total": 0,
        "quizzes_attempted": 0,
        "quizzes_total": 0,
        "attendance_percentage": 100.0
    }
    
    return {
        "course_id": course.course_id,
        "title": course.title,
        "description": course.description,
        "branch_id": course.branch_id,
        "semester_id": course.semester_id,
        "teacher_id": course.teacher_id,
        "branch": course.branch.name if course.branch else None,
        "semester_name": course.semester.name if course.semester else None,
        "teacher_name": course.teacher.full_name if course.teacher else None,
        "created_at": course.created_at,
        "updated_at": course.updated_at,
        "progress": progress,
        "modules_completed": details["modules_completed"],
        "modules_total": details["modules_total"],
        "assignments_submitted": details["assignments_submitted"],
        "assignments_total": details["assignments_total"],
        "quizzes_attempted": details["quizzes_attempted"],
        "quizzes_total": details["quizzes_total"],
        "attendance_percentage": details["attendance_percentage"]
    }

# ----------------- COURSE ENDPOINTS -----------------

@router.get("/courses", response_model=List[schemas.CourseResponse])
def get_courses(branch_id: Optional[int] = None, semester_id: Optional[int] = None, include_archived: Optional[bool] = False, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    # If student, default filter to their branch and semester, and inject progress
    if current_user.role == "student":
        courses = db.query(models.Course).filter(
            models.Course.branch_id == current_user.branch_id, 
            models.Course.semester_id == current_user.semester_id,
            models.Course.is_archived == False
        ).all()
        
        response_data = []
        for course in courses:
            progress_info = get_student_course_progress(current_user.user_id, course.course_id, db)
            response_data.append(map_course(course, progress=progress_info["progress"], progress_details=progress_info))
        return response_data
        
    elif current_user.role == "teacher":
        courses = db.query(models.Course).filter(
            models.Course.teacher_id == current_user.user_id,
            models.Course.is_archived == False
        ).all()
        return [map_course(course) for course in courses]
        
    query = db.query(models.Course)
    
    # Filter out archived courses for teachers/students or if not explicitly requested by admin
    if not include_archived or current_user.role != "admin":
        query = query.filter(models.Course.is_archived == False)
        
    if branch_id:
        query = query.filter(models.Course.branch_id == branch_id)
    if semester_id:
        query = query.filter(models.Course.semester_id == semester_id)
        
    courses = query.order_by(models.Course.course_id).all()
    return [map_course(course) for course in courses]

@router.get("/courses/{course_id}")
def get_course_details(course_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    course = check_course_access(course_id, current_user, db)
    
    # Fetch nested lists
    modules = db.query(models.Module).filter(models.Module.course_id == course_id).order_by(models.Module.order_num).all()
    assignments = db.query(models.Assignment).filter(models.Assignment.course_id == course_id).all()
    quizzes = db.query(models.Quiz).filter(models.Quiz.course_id == course_id).all()
    
    progress_info = {
        "progress": 0.0,
        "modules_completed": 0,
        "modules_total": 0,
        "assignments_submitted": 0,
        "assignments_total": 0,
        "quizzes_attempted": 0,
        "quizzes_total": 0,
        "attendance_percentage": 100.0
    }
    
    if current_user.role == "student":
        progress_info = get_student_course_progress(current_user.user_id, course_id, db)

    # Return structured course metadata
    return {
        "course_id": course.course_id,
        "title": course.title,
        "description": course.description,
        "branch_id": course.branch_id,
        "semester_id": course.semester_id,
        "semester_name": course.semester.name if course.semester else None,
        "branch": course.branch.name if course.branch else None,
        "teacher_id": course.teacher_id,
        "teacher_name": course.teacher.full_name if course.teacher else "Not Assigned",
        "progress": progress_info["progress"],
        "modules_completed": progress_info["modules_completed"],
        "modules_total": progress_info["modules_total"],
        "assignments_submitted": progress_info["assignments_submitted"],
        "assignments_total": progress_info["assignments_total"],
        "quizzes_attempted": progress_info["quizzes_attempted"],
        "quizzes_total": progress_info["quizzes_total"],
        "attendance_percentage": progress_info["attendance_percentage"],
        "is_archived": course.is_archived,
        "modules": [
            {
                "module_id": m.module_id,
                "title": m.title,
                "description": m.description,
                "order_num": m.order_num,
                "materials": [
                    {
                        "material_id": mat.material_id,
                        "title": mat.title,
                        "file_path": mat.file_path,
                        "file_type": mat.file_type,
                        "uploaded_at": mat.uploaded_at
                    } for mat in m.materials
                ]
            } for m in modules
        ],
        "assignments": [
            {
                "assignment_id": a.assignment_id,
                "title": a.title,
                "due_date": a.due_date,
                "total_marks": a.total_marks
            } for a in assignments
        ],
        "quizzes": [
            {
                "quiz_id": q.quiz_id,
                "title": q.title,
                "total_marks": q.total_marks,
                "time_limit": q.time_limit
            } for q in quizzes
        ]
    }

@router.post("/courses", response_model=schemas.CourseResponse, status_code=status.HTTP_201_CREATED)
def create_course(payload: schemas.CourseCreate, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    teacher_id = payload.teacher_id if payload.teacher_id and payload.teacher_id > 0 else None
    new_course = models.Course(
        title=payload.title,
        description=payload.description,
        branch_id=payload.branch_id,
        semester_id=payload.semester_id,
        teacher_id=teacher_id
    )
    db.add(new_course)
    db.commit()
    db.refresh(new_course)
    return map_course(new_course)

@router.put("/courses/{course_id}", response_model=schemas.CourseResponse)
def update_course(course_id: int, payload: schemas.CourseCreate, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    course = db.query(models.Course).filter(models.Course.course_id == course_id).first()
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
        
    teacher_id = payload.teacher_id if payload.teacher_id and payload.teacher_id > 0 else None
    course.title = payload.title
    course.description = payload.description
    course.branch_id = payload.branch_id
    course.semester_id = payload.semester_id
    course.teacher_id = teacher_id
    
    db.commit()
    db.refresh(course)
    return map_course(course)

from pydantic import BaseModel

class CourseAssign(BaseModel):
    teacher_id: Optional[int] = None

@router.put("/courses/{course_id}/assign", response_model=schemas.CourseResponse)
def assign_course(course_id: int, payload: CourseAssign, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    course = db.query(models.Course).filter(models.Course.course_id == course_id).first()
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
        
    if payload.teacher_id is not None:
        teacher = db.query(models.User).filter(models.User.user_id == payload.teacher_id, models.User.role == "teacher").first()
        if not teacher:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Teacher not found")
            
    course.teacher_id = payload.teacher_id
    db.commit()
    db.refresh(course)
    return map_course(course)

@router.delete("/courses/{course_id}", status_code=status.HTTP_200_OK)
def delete_course(course_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    course = db.query(models.Course).filter(models.Course.course_id == course_id).first()
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
        
    # Delete related enrollments first (cascade delete-orphan on relationship is configured, but let's be safe)
    db.query(models.Enrollment).filter(models.Enrollment.course_id == course_id).delete()
    db.query(models.Certificate).filter(models.Certificate.course_id == course_id).delete()
    db.query(models.Review).filter(models.Review.course_id == course_id).delete()
    
    db.delete(course)
    db.commit()
    return {"message": "deleted"}

# ----------------- MODULE SUBRESOURCE ENDPOINTS -----------------

@router.get("/courses/{course_id}/modules", response_model=List[schemas.ModuleResponse])
def get_course_modules(course_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    check_course_access(course_id, current_user, db)
    return db.query(models.Module).filter(models.Module.course_id == course_id).order_by(models.Module.order_num).all()

@router.post("/courses/{course_id}/modules", response_model=schemas.ModuleResponse, status_code=status.HTTP_201_CREATED)
def create_course_module(course_id: int, payload: schemas.ModuleCreate, db: Session = Depends(get_db), current_user: models.User = Depends(require_teacher)):
    # Verify course belongs to teacher
    course = db.query(models.Course).filter(
        models.Course.course_id == course_id,
        models.Course.teacher_id == current_user.user_id
    ).first()
    if not course:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not own this course")
        
    new_module = models.Module(
        course_id=course_id,
        title=payload.title,
        description=payload.description,
        order_num=payload.order_num
    )
    db.add(new_module)
    db.commit()
    db.refresh(new_module)
    return new_module

@router.put("/modules/{module_id}", response_model=schemas.ModuleResponse)
def update_module(module_id: int, payload: schemas.ModuleCreate, db: Session = Depends(get_db), current_user: models.User = Depends(require_teacher)):
    module = db.query(models.Module).filter(models.Module.module_id == module_id).first()
    if not module:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Module not found")
        
    if module.course.teacher_id != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not own this course")
        
    module.title = payload.title
    module.description = payload.description
    module.order_num = payload.order_num
    db.commit()
    db.refresh(module)
    return module

@router.delete("/modules/{module_id}", status_code=status.HTTP_200_OK)
def delete_module(module_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(require_teacher)):
    module = db.query(models.Module).filter(models.Module.module_id == module_id).first()
    if not module:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Module not found")
        
    if module.course.teacher_id != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not own this course")
        
    db.delete(module)
    db.commit()
    return {"message": "deleted"}

# ----------------- MATERIAL UPLOAD ENDPOINTS -----------------

UPLOAD_DIR = "static/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.post("/modules/{module_id}/materials", response_model=schemas.MaterialResponse, status_code=status.HTTP_201_CREATED)
def upload_material(module_id: int, file: UploadFile = File(...), title: Optional[str] = Form(None), db: Session = Depends(get_db), current_user: models.User = Depends(require_teacher)):
    module = db.query(models.Module).filter(models.Module.module_id == module_id).first()
    if not module:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Module not found")
        
    if module.course.teacher_id != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not own this course")
        
    # Generate unique file name and save to local static folder
    file_extension = os.path.splitext(file.filename)[1]
    safe_filename = f"material_{module_id}_{int(os.times()[4])}{file_extension}"
    file_path = os.path.join(UPLOAD_DIR, safe_filename)
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    # Infer file type
    file_type = "pdf" if file_extension.lower() == ".pdf" else "video" if file_extension.lower() in [".mp4", ".mkv", ".mov"] else "notes"
    
    new_material = models.Material(
        module_id=module_id,
        title=title or file.filename,
        file_path=f"/static/uploads/{safe_filename}",
        file_type=file_type
    )
    
    db.add(new_material)
    db.commit()
    db.refresh(new_material)
    return new_material

@router.delete("/materials/{material_id}", status_code=status.HTTP_200_OK)
def delete_material(material_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(require_teacher)):
    material = db.query(models.Material).filter(models.Material.material_id == material_id).first()
    if not material:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Material not found")
        
    if material.module.course.teacher_id != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not own this course")
        
    # Delete file from local disk if it exists
    relative_path = material.file_path.lstrip("/")
    if os.path.exists(relative_path):
        os.remove(relative_path)
        
    db.delete(material)
    db.commit()
    return {"message": "deleted"}

@router.post("/courses/{course_id}/archive")
def archive_course(course_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    course = db.query(models.Course).filter(models.Course.course_id == course_id).first()
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    course.is_archived = True
    
    # Log action
    log = models.ActivityLog(user_id=current_user.user_id, action=f"Archived course: {course.title}")
    db.add(log)
    db.commit()
    return {"message": "Course successfully archived"}

@router.post("/courses/{course_id}/restore")
def restore_course(course_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    course = db.query(models.Course).filter(models.Course.course_id == course_id).first()
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    course.is_archived = False
    
    # Log action
    log = models.ActivityLog(user_id=current_user.user_id, action=f"Restored course: {course.title}")
    db.add(log)
    db.commit()
    return {"message": "Course successfully restored"}
