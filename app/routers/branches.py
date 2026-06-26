from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from ..database import get_db
from .. import models, schemas
from .auth import require_admin, get_current_user

router = APIRouter(prefix="/branches", tags=["Branch Management"])

@router.get("/", response_model=List[schemas.BranchResponse])
def list_branches(db: Session = Depends(get_db)):
    return db.query(models.Branch).order_by(models.Branch.branch_id).all()

@router.post("/", response_model=schemas.BranchResponse, status_code=status.HTTP_201_CREATED)
def create_branch(payload: schemas.BranchCreate, db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    # Check if branch name already exists
    existing = db.query(models.Branch).filter(models.Branch.name == payload.name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Branch name already exists"
        )
    
    new_branch = models.Branch(name=payload.name)
    db.add(new_branch)
    db.commit()
    db.refresh(new_branch)
    return new_branch

@router.put("/{branch_id}", response_model=schemas.BranchResponse)
def update_branch(branch_id: int, payload: schemas.BranchCreate, db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    branch = db.query(models.Branch).filter(models.Branch.branch_id == branch_id).first()
    if not branch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Branch not found"
        )
    
    # Check if name is taken by another branch
    existing = db.query(models.Branch).filter(
        models.Branch.name == payload.name, 
        models.Branch.branch_id != branch_id
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Branch name already exists"
        )
        
    branch.name = payload.name
    db.commit()
    db.refresh(branch)
    return branch

@router.delete("/{branch_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_branch(branch_id: int, db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    branch = db.query(models.Branch).filter(models.Branch.branch_id == branch_id).first()
    if not branch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Branch not found"
        )
        
    # Check if any users are linked to this branch
    users_count = db.query(models.User).filter(models.User.branch_id == branch_id).count()
    if users_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete branch. It is linked to {users_count} users."
        )
        
    # Check if any courses are linked to this branch
    courses_count = db.query(models.Course).filter(models.Course.branch_id == branch_id).count()
    if courses_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete branch. It is linked to {courses_count} courses."
        )

    db.delete(branch)
    db.commit()
    return None
