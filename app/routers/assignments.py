from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session, joinedload
from typing import List
import os
import shutil

from ..database import get_db
from .. import models, schemas
from .auth import get_current_user, require_teacher, require_student
from .courses import check_course_access

router = APIRouter(tags=["Assignments & Submissions"])

SUBMISSIONS_DIR = "static/uploads/submissions"
os.makedirs(SUBMISSIONS_DIR, exist_ok=True)

# ----------------- ASSIGNMENT ENDPOINTS -----------------

@router.get("/assignments", response_model=List[schemas.AssignmentResponse])
def get_all_assignments(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    # 1. Admin sees all assignments
    if current_user.role == "admin":
        assignments = db.query(models.Assignment).options(joinedload(models.Assignment.course)).all()
    # 2. Teacher sees assignments for courses they teach
    elif current_user.role == "teacher":
        assignments = db.query(models.Assignment).join(models.Course).filter(
            models.Course.teacher_id == current_user.user_id
        ).options(joinedload(models.Assignment.course)).all()
    # 3. Student sees assignments for courses they are enrolled in
    elif current_user.role == "student":
        assignments = db.query(models.Assignment).join(models.Enrollment, models.Enrollment.course_id == models.Assignment.course_id).filter(
            models.Enrollment.student_id == current_user.user_id
        ).options(joinedload(models.Assignment.course)).all()
    else:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    response_data = []
    # Cache student submissions to avoid N+1 queries if student is requesting
    submissions_dict = {}
    if current_user.role == "student":
        submissions = db.query(models.Submission).filter(
            models.Submission.student_id == current_user.user_id
        ).all()
        submissions_dict = {sub.assignment_id: sub for sub in submissions}

    for asg in assignments:
        submission = submissions_dict.get(asg.assignment_id) if current_user.role == "student" else None
        
        response_data.append(schemas.AssignmentResponse(
            assignment_id=asg.assignment_id,
            course_id=asg.course_id,
            title=asg.title,
            description=asg.description,
            due_date=asg.due_date,
            total_marks=asg.total_marks,
            created_at=asg.created_at,
            student_status=submission.status if submission else "Not Submitted",
            submitted_at=submission.submitted_at if submission else None,
            grade=submission.marks if submission else None,
            feedback=submission.feedback if submission else None,
            course_title=asg.course.title if asg.course else None
        ))
    return response_data

@router.get("/courses/{course_id}/assignments", response_model=List[schemas.AssignmentResponse])
def get_course_assignments(course_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    check_course_access(course_id, current_user, db)
    assignments = db.query(models.Assignment).filter(models.Assignment.course_id == course_id).all()
    
    response_data = []
    for asg in assignments:
        submission = db.query(models.Submission).filter(
            models.Submission.assignment_id == asg.assignment_id,
            models.Submission.student_id == current_user.user_id
        ).first()
        
        response_data.append(schemas.AssignmentResponse(
            assignment_id=asg.assignment_id,
            course_id=asg.course_id,
            title=asg.title,
            description=asg.description,
            due_date=asg.due_date,
            total_marks=asg.total_marks,
            created_at=asg.created_at,
            student_status=submission.status if submission else "Not Submitted",
            submitted_at=submission.submitted_at if submission else None,
            grade=submission.marks if submission else None,
            feedback=submission.feedback if submission else None
        ))
    return response_data

@router.get("/assignments/{assignment_id}", response_model=schemas.AssignmentResponse)
def get_assignment_by_id(assignment_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    assignment = db.query(models.Assignment).filter(models.Assignment.assignment_id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")
    check_course_access(assignment.course_id, current_user, db)
    
    submission = db.query(models.Submission).filter(
        models.Submission.assignment_id == assignment_id,
        models.Submission.student_id == current_user.user_id
    ).first()
    
    return schemas.AssignmentResponse(
        assignment_id=assignment.assignment_id,
        course_id=assignment.course_id,
        title=assignment.title,
        description=assignment.description,
        due_date=assignment.due_date,
        total_marks=assignment.total_marks,
        created_at=assignment.created_at,
        student_status=submission.status if submission else "Not Submitted",
        submitted_at=submission.submitted_at if submission else None,
        grade=submission.marks if submission else None,
        feedback=submission.feedback if submission else None
    )

@router.post("/courses/{course_id}/assignments", response_model=schemas.AssignmentResponse, status_code=status.HTTP_201_CREATED)
def create_assignment(course_id: int, payload: schemas.AssignmentCreate, db: Session = Depends(get_db), current_user: models.User = Depends(require_teacher)):
    # Verify course belongs to teacher
    course = db.query(models.Course).filter(
        models.Course.course_id == course_id,
        models.Course.teacher_id == current_user.user_id
    ).first()
    if not course:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not own this course")
        
    new_assignment = models.Assignment(
        course_id=course_id,
        title=payload.title,
        description=payload.description,
        due_date=payload.due_date,
        total_marks=payload.total_marks
    )
    db.add(new_assignment)
    db.commit()
    db.refresh(new_assignment)

    # Send notifications
    from .notifications import send_notification_helper, notify_admins
    # 1. Notify all enrolled students
    enrollments = db.query(models.Enrollment).filter(models.Enrollment.course_id == course_id).all()
    for enrollment in enrollments:
        send_notification_helper(
            db, 
            enrollment.student_id, 
            "New Assignment Uploaded", 
            f"Your teacher {current_user.full_name} has published a new assignment: '{new_assignment.title}' in course '{course.title}'."
        )
    # 2. Notify all admins
    notify_admins(
        db,
        "New Assignment Created",
        f"Teacher {current_user.full_name} created assignment '{new_assignment.title}' in course '{course.title}'."
    )

    return new_assignment

@router.put("/assignments/{assignment_id}", response_model=schemas.AssignmentResponse)
def update_assignment(assignment_id: int, payload: schemas.AssignmentCreate, db: Session = Depends(get_db), current_user: models.User = Depends(require_teacher)):
    assignment = db.query(models.Assignment).filter(models.Assignment.assignment_id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")
        
    if assignment.course.teacher_id != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not own this course")
        
    assignment.title = payload.title
    assignment.description = payload.description
    assignment.due_date = payload.due_date
    assignment.total_marks = payload.total_marks
    
    db.commit()
    db.refresh(assignment)
    return assignment

@router.delete("/assignments/{assignment_id}", status_code=status.HTTP_200_OK)
def delete_assignment(assignment_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(require_teacher)):
    assignment = db.query(models.Assignment).filter(models.Assignment.assignment_id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")
        
    if assignment.course.teacher_id != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not own this course")
        
    db.delete(assignment)
    db.commit()
    return {"message": "deleted"}

# ----------------- SUBMISSIONS & GRADING ENDPOINTS -----------------

@router.get("/assignments/{assignment_id}/submissions")
def get_assignment_submissions(assignment_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(require_teacher)):
    assignment = db.query(models.Assignment).filter(models.Assignment.assignment_id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")
        
    if assignment.course.teacher_id != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not own this course")
        
    submissions = db.query(models.Submission).filter(models.Submission.assignment_id == assignment_id).all()
    
    # Return formatted list including student names
    return [
        {
            "submission_id": sub.submission_id,
            "assignment_id": sub.assignment_id,
            "student_id": sub.student_id,
            "student_name": sub.student.full_name,
            "file_path": sub.file_path,
            "submitted_at": sub.submitted_at,
            "marks": sub.marks,
            "feedback": sub.feedback,
            "status": sub.status
        } for sub in submissions
    ]

@router.post("/assignments/{assignment_id}/submit", response_model=schemas.SubmissionResponse, status_code=status.HTTP_201_CREATED)
def submit_assignment(assignment_id: int, file: UploadFile = File(...), db: Session = Depends(get_db), current_user: models.User = Depends(require_student)):
    assignment = db.query(models.Assignment).filter(models.Assignment.assignment_id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")
        
    check_course_access(assignment.course_id, current_user, db)
    
    # Check if already submitted
    existing_submission = db.query(models.Submission).filter(
        models.Submission.assignment_id == assignment_id,
        models.Submission.student_id == current_user.user_id
    ).first()
    
    # Generate file name
    file_extension = os.path.splitext(file.filename)[1]
    safe_filename = f"submission_{assignment_id}_{current_user.user_id}{file_extension}"
    file_path = os.path.join(SUBMISSIONS_DIR, safe_filename)
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    from .notifications import send_notification_helper, notify_admins
    if existing_submission:
        # Update existing submission
        existing_submission.file_path = f"/static/uploads/submissions/{safe_filename}"
        existing_submission.submitted_at = models.func.now()
        existing_submission.status = "Pending"
        db.commit()
        db.refresh(existing_submission)

        # Notify Teacher
        if assignment.course.teacher_id:
            send_notification_helper(
                db,
                assignment.course.teacher_id,
                "Assignment Submission Updated",
                f"Student {current_user.full_name} has updated their submission for '{assignment.title}'."
            )
        # Notify Admins
        notify_admins(
            db,
            "Assignment Submission Updated",
            f"Student {current_user.full_name} updated submission for '{assignment.title}' in '{assignment.course.title}'."
        )

        return existing_submission
    else:
        # Create new submission
        new_submission = models.Submission(
            assignment_id=assignment_id,
            student_id=current_user.user_id,
            file_path=f"/static/uploads/submissions/{safe_filename}",
            status="Pending"
        )
        db.add(new_submission)
        db.commit()
        db.refresh(new_submission)

        # Notify Teacher
        if assignment.course.teacher_id:
            send_notification_helper(
                db,
                assignment.course.teacher_id,
                "New Assignment Submission",
                f"Student {current_user.full_name} has submitted '{assignment.title}'."
            )
        # Notify Admins
        notify_admins(
            db,
            "New Assignment Submission",
            f"Student {current_user.full_name} submitted '{assignment.title}' in '{assignment.course.title}'."
        )

        return new_submission

@router.put("/submissions/{submission_id}", response_model=schemas.SubmissionResponse)
def grade_submission(submission_id: int, payload: schemas.GradeSubmission, db: Session = Depends(get_db), current_user: models.User = Depends(require_teacher)):
    submission = db.query(models.Submission).filter(models.Submission.submission_id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found")
        
    if submission.assignment.course.teacher_id != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not own this course")
        
    submission.marks = payload.marks
    submission.feedback = payload.feedback
    submission.status = "Graded"
    
    db.commit()
    db.refresh(submission)

    # Send notifications
    from .notifications import send_notification_helper, notify_admins
    # Notify Student
    send_notification_helper(
        db,
        submission.student_id,
        "Assignment Graded",
        f"Your submission for '{submission.assignment.title}' has been graded: {payload.marks}/{submission.assignment.total_marks} marks."
    )
    # Notify Admins
    notify_admins(
        db,
        "Submission Graded",
        f"Teacher {current_user.full_name} graded student {submission.student.full_name}'s submission for '{submission.assignment.title}': {payload.marks}/{submission.assignment.total_marks} marks."
    )

    return submission
