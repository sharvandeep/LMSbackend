from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from ..database import get_db
from .. import models, schemas
from .auth import require_admin, get_current_user

router = APIRouter(prefix="/semesters", tags=["Semester Management"])

@router.get("/", response_model=List[schemas.SemesterResponse])
def list_semesters(db: Session = Depends(get_db)):
    return db.query(models.Semester).order_by(models.Semester.number).all()

@router.post("/", response_model=schemas.SemesterResponse, status_code=status.HTTP_201_CREATED)
def create_semester(payload: schemas.SemesterCreate, db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    # Check if number already exists
    existing = db.query(models.Semester).filter(models.Semester.number == payload.number).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Semester number {payload.number} already exists"
        )
        
    new_semester = models.Semester(
        number=payload.number,
        name=payload.name,
        status=payload.status or "Active"
    )
    db.add(new_semester)
    db.commit()
    db.refresh(new_semester)
    return new_semester

@router.put("/{semester_id}", response_model=schemas.SemesterResponse)
def update_semester(semester_id: int, payload: schemas.SemesterCreate, db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    semester = db.query(models.Semester).filter(models.Semester.semester_id == semester_id).first()
    if not semester:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Semester not found"
        )
        
    # Check if number is taken by another semester
    existing = db.query(models.Semester).filter(
        models.Semester.number == payload.number, 
        models.Semester.semester_id != semester_id
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Semester number {payload.number} already exists"
        )
        
    semester.number = payload.number
    semester.name = payload.name
    semester.status = payload.status
    db.commit()
    db.refresh(semester)
    return semester

@router.delete("/{semester_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_semester(semester_id: int, db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    semester = db.query(models.Semester).filter(models.Semester.semester_id == semester_id).first()
    if not semester:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Semester not found"
        )
        
    # Check if any users are linked to this semester
    users_count = db.query(models.User).filter(models.User.semester_id == semester_id).count()
    if users_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete semester. It is linked to {users_count} users."
        )
        
    # Check if any courses are linked to this semester
    courses_count = db.query(models.Course).filter(models.Course.semester_id == semester_id).count()
    if courses_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete semester. It is linked to {courses_count} courses."
        )

    db.delete(semester)
    db.commit()
    return None
