from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from jose import jwt, JWTError
from datetime import timedelta, datetime
from typing import List
import os
import uuid
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from ..database import get_db
from .. import models, schemas, security

router = APIRouter(prefix="/auth", tags=["Authentication"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")

# Dependency to get current authenticated user
def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> models.User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token, 
            security.SECRET_KEY, 
            algorithms=[security.ALGORITHM]
        )
        user_id: str = payload.get("sub")
        role: str = payload.get("role")
        if user_id is None or role is None:
            raise credentials_exception
        token_data = schemas.TokenData(user_id=user_id, role=role)
    except JWTError:
        raise credentials_exception
        
    user = db.query(models.User).filter(models.User.user_id == int(token_data.user_id)).first()
    if user is None:
        raise credentials_exception
    return user

# Role enforcement dependencies
def require_role(allowed_roles: List[str]):
    def role_dependency(current_user: models.User = Depends(get_current_user)):
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required roles: {allowed_roles}"
            )
        return current_user
    return role_dependency

require_teacher = require_role(["teacher"])
require_admin = require_role(["admin"])
require_student = require_role(["student"])

# ----------------- ENDPOINTS -----------------

@router.post("/register", response_model=schemas.Token, status_code=status.HTTP_201_CREATED)
def register(payload: schemas.UserRegister, db: Session = Depends(get_db)):
    # Check if email is already registered
    db_user = db.query(models.User).filter(models.User.email == payload.email).first()
    if db_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is already registered"
        )
        
    # Verify branch exists
    branch = db.query(models.Branch).filter(models.Branch.branch_id == payload.branch_id).first()
    if not branch:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid branch_id specified"
        )

    # Validate role
    role = payload.role or "student"
    if role not in ["student", "teacher"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Self-registration is only allowed for student and teacher roles"
        )

    # Validate semester for student
    semester_id = None
    if role == "student":
        if not payload.semester_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="semester_id is required for student registration"
            )
        semester = db.query(models.Semester).filter(models.Semester.semester_id == payload.semester_id).first()
        if not semester:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid semester_id specified"
            )
        semester_id = payload.semester_id

    # Hash the password
    hashed_password = security.get_password_hash(payload.password)
    
    # Determine verification status
    is_verified = True if role != "student" else False
    verification_token = uuid.uuid4().hex if role == "student" else None
    
    # Create new user
    new_user = models.User(
        full_name=payload.full_name,
        email=payload.email,
        password_hash=hashed_password,
        role=role,
        branch_id=payload.branch_id,
        semester_id=semester_id,
        is_verified=is_verified,
        verification_token=verification_token
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    # ----------------- STUDENT ONLY: TEACHER ALLOCATION & BATCHING LOGIC -----------------
    if role == "student":
        # 1. Fetch teacher capacity from settings (default 7)
        capacity_setting = db.query(models.Setting).filter(models.Setting.setting_key == "teacher_capacity").first()
        capacity = int(capacity_setting.setting_value) if capacity_setting else 7

        # 2. Get all teachers registered in this branch
        teachers = db.query(models.User).filter(
            models.User.branch_id == new_user.branch_id,
            models.User.role == "teacher"
        ).all()
        
        if not teachers:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No teachers are registered in this branch to allocate a batch"
            )

        assigned_batch = None
        
        # 3. Find an existing batch in the branch/semester with space (< capacity)
        for teacher in teachers:
            batch = db.query(models.Batch).filter(
                models.Batch.branch_id == new_user.branch_id,
                models.Batch.semester_id == new_user.semester_id,
                models.Batch.teacher_id == teacher.user_id
            ).first()
            
            if batch:
                # Count unique students in this batch
                student_count = db.query(models.Enrollment.student_id).filter(
                    models.Enrollment.batch_id == batch.batch_id
                ).distinct().count()
                
                if student_count < capacity:
                    assigned_batch = batch
                    break

        # 4. If no batch has space, allocate the teacher with the least load and create a new batch
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
                        
            # Create the new batch
            assigned_batch = models.Batch(
                branch_id=new_user.branch_id,
                semester_id=new_user.semester_id,
                teacher_id=selected_teacher.user_id
            )
            db.add(assigned_batch)
            db.commit()
            db.refresh(assigned_batch)

        # 5. Auto-enroll student into branch/semester courses and link to their batch
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
        
        # Dispatch student email verification
        verify_link = f"http://localhost:5173/verify-email?token={verification_token}"
        logging.info("\n" + "="*80)
        logging.info(" EMAIL VERIFICATION LINK GENERATED")
        logging.info(f" Student: {new_user.full_name} ({new_user.email})")
        logging.info(f" Verification Link: {verify_link}")
        logging.info("="*80 + "\n")
        
        # Send real SMTP mail if configured
        smtp_server = os.getenv("SMTP_SERVER")
        smtp_port = os.getenv("SMTP_PORT")
        smtp_username = os.getenv("SMTP_USERNAME")
        smtp_password = os.getenv("SMTP_PASSWORD")
        smtp_from = os.getenv("SMTP_FROM", "noreply@lms.com")
        smtp_display_name = os.getenv("SMTP_DISPLAY_NAME", "LearnSphear")
        
        if smtp_server and smtp_port and smtp_username and smtp_password:
            try:
                msg = MIMEMultipart()
                msg['From'] = f'"{smtp_display_name}" <{smtp_from}>' if smtp_display_name else smtp_from
                msg['To'] = new_user.email
                msg['Subject'] = f"{smtp_display_name} - Verify Your Account"
                
                html_content = f"""
                <html>
                    <body style="font-family: 'Segoe UI', Arial, sans-serif; background-color: #f8fafc; padding: 30px; margin: 0; color: #1e293b;">
                        <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 12px; border: 1px solid #e2e8f0; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);">
                            <div style="background: linear-gradient(135deg, #0ea5e9 0%, #0284c7 100%); padding: 30px; text-align: center; color: white;">
                                <h1 style="margin: 0; font-size: 24px; font-weight: 700; letter-spacing: -0.025em;">Welcome to LearnSphear!</h1>
                                <p style="margin: 5px 0 0 0; opacity: 0.9; font-size: 14px;">Account Activation</p>
                            </div>
                            <div style="padding: 35px 30px; line-height: 1.6; font-size: 16px;">
                                <p style="margin-top: 0; font-weight: 600;">Hi {new_user.full_name},</p>
                                <p>Thank you for registering at LearnSphear LMS. To activate your student account and access your dashboard, please verify your email address by clicking the button below:</p>
                                
                                <div style="text-align: center; margin: 30px 0;">
                                    <a href="{verify_link}" style="background-color: #0284c7; color: white; padding: 12px 30px; text-decoration: none; border-radius: 6px; font-weight: 600; display: inline-block; box-shadow: 0 4px 6px -1px rgba(2, 132, 199, 0.2);">Verify Email Address</a>
                                </div>
                                
                                <p style="font-size: 14px; color: #64748b; margin-bottom: 0;">
                                    If the button above doesn't work, copy and paste the link below into your web browser:<br>
                                    <a href="{verify_link}" style="color: #0284c7; word-break: break-all;">{verify_link}</a>
                                </p>
                            </div>
                            <div style="background-color: #f8fafc; padding: 20px 30px; text-align: center; font-size: 12px; color: #94a3b8; border-top: 1px solid #e2e8f0;">
                                If you did not sign up for this account, you can safely ignore this email.
                            </div>
                        </div>
                    </body>
                </html>
                """
                msg.attach(MIMEText(html_content, 'html'))
                
                server = smtplib.SMTP(smtp_server, int(smtp_port))
                server.starttls()
                server.login(smtp_username, smtp_password)
                server.sendmail(smtp_from, new_user.email, msg.as_string())
                server.close()
                logging.info(f"Verification email sent to {new_user.email}")
            except Exception as e:
                logging.error(f"Failed to send SMTP verification email: {e}")
        
        # For student, we return empty token so they are prompted to verify first
        return {"token": "", "user_id": new_user.user_id, "role": new_user.role}
    
    # Create access token for teachers/admins who are auto-verified
    access_token = security.create_access_token(
        data={"sub": str(new_user.user_id), "role": new_user.role}
    )
    
    return {"token": access_token, "user_id": new_user.user_id, "role": new_user.role}

@router.post("/login", response_model=schemas.Token)
def login(credentials: schemas.UserLogin, request: Request, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == credentials.email).first()
    if not user or not security.verify_password(credentials.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    # Enforce email verification
    if not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please verify your email before logging in. Check your registered inbox for the activation link."
        )
        
    # Create access token
    access_token = security.create_access_token(
        data={"sub": str(user.user_id), "role": user.role}
    )
    
    # Log successful login session
    try:
        ip_address = request.client.host if request.client else "127.0.0.1"
        user_agent = request.headers.get("user-agent", "Unknown Browser")
        
        login_log = models.LoginHistory(
            user_id=user.user_id,
            ip_address=ip_address,
            user_agent=user_agent
        )
        db.add(login_log)
        
        # General activity logging
        act_log = models.ActivityLog(
            user_id=user.user_id,
            action=f"Logged in from IP: {ip_address}"
        )
        db.add(act_log)
        db.commit()
    except Exception as e:
        db.rollback()
        logging.error(f"Failed to record login history: {e}")
    
    return {"token": access_token, "user_id": user.user_id, "role": user.role}

from pydantic import BaseModel

class ForgotPasswordRequest(BaseModel):
    email: str

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

@router.post("/forgot-password")
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    import os
    user = db.query(models.User).filter(models.User.email == payload.email).first()
    if not user:
        # Factual, uniform response to prevent user enumeration
        return {"message": "If the email is registered, you will receive a reset link shortly."}
        
    expires_delta = timedelta(minutes=15)
    token = security.create_access_token(
        data={"sub": str(user.user_id), "purpose": "password_reset"},
        expires_delta=expires_delta
    )
    
    reset_link = f"http://localhost:5173/reset-password/{token}"
    
    # 1. Print the link to the console for easy local development testing
    import logging
    logging.info("\n" + "="*80)
    logging.info(" PASSWORD RESET REQUESTED")
    logging.info(f" User: {user.full_name} ({user.email})")
    logging.info(f" Reset Link: {reset_link}")
    logging.info("="*80 + "\n")
    
    # 2. Try to send a real email using SMTP if configured in environment
    smtp_server = os.getenv("SMTP_SERVER")
    smtp_port = os.getenv("SMTP_PORT")
    smtp_username = os.getenv("SMTP_USERNAME")
    smtp_password = os.getenv("SMTP_PASSWORD")
    smtp_from = os.getenv("SMTP_FROM", "noreply@lms.com")
    smtp_display_name = os.getenv("SMTP_DISPLAY_NAME", "LearnSphear")
    
    if smtp_server and smtp_port and smtp_username and smtp_password:
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            
            msg = MIMEMultipart()
            msg['From'] = f'"{smtp_display_name}" <{smtp_from}>' if smtp_display_name else smtp_from
            msg['To'] = user.email
            msg['Subject'] = f"{smtp_display_name} Password Reset Request"
            
            body = f"""Hi {user.full_name},
            
We received a request to reset the password for your {smtp_display_name} account.
You can reset your password by clicking the link below:

{reset_link}

This link is secure and will expire in 15 minutes.
If you did not request a password reset, please ignore this email.

Regards,
{smtp_display_name} Administration
"""
            msg.attach(MIMEText(body, 'plain'))
            
            server = smtplib.SMTP(smtp_server, int(smtp_port))
            server.starttls()
            server.login(smtp_username, smtp_password)
            server.sendmail(smtp_from, user.email, msg.as_string())
            server.close()
            logging.info(f"Real reset email sent successfully to {user.email}")
        except Exception as e:
            logging.error(f"Failed to send SMTP email (logged to console instead): {e}")
            
    return {"message": "If the email is registered, you will receive a reset link shortly."}

@router.post("/reset-password")
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="The password reset link is invalid or has expired.",
    )
    try:
        token_data = jwt.decode(
            payload.token, 
            security.SECRET_KEY, 
            algorithms=[security.ALGORITHM]
        )
        user_id: str = token_data.get("sub")
        purpose: str = token_data.get("purpose")
        
        if user_id is None or purpose != "password_reset":
            raise credentials_exception
            
    except JWTError:
        raise credentials_exception
        
    user = db.query(models.User).filter(models.User.user_id == int(user_id)).first()
    if not user:
        raise credentials_exception
        
    user.password_hash = security.get_password_hash(payload.new_password)
    db.commit()
    
    return {"message": "Your password has been successfully reset. You can now log in."}

@router.get("/verify-email")
def verify_email(token: str, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.verification_token == token).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification token."
        )
        
    user.is_verified = True
    user.verification_token = None
    
    # Log activity
    log = models.ActivityLog(user_id=user.user_id, action=f"User account verified: {user.email}")
    db.add(log)
    db.commit()
    
    return {"message": "Account successfully verified! You can now log in."}

@router.get("/device-history")
def get_device_history(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    history = db.query(models.LoginHistory).filter(
        models.LoginHistory.user_id == current_user.user_id
    ).order_by(models.LoginHistory.logged_in_at.desc()).limit(10).all()
    
    return [
        {
            "history_id": h.history_id,
            "ip_address": h.ip_address,
            "user_agent": h.user_agent,
            "logged_in_at": h.logged_in_at
        } for h in history
    ]
