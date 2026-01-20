# main.py
from database import Base, engine
from fastapi.security import OAuth2PasswordRequestForm
from datetime import datetime
from fastapi import FastAPI, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import Boolean, Column, Integer, String, ForeignKey, DateTime, Text, Float
from models import User, ScheduleEvent
from schemas import UserCreate, UserOut, EventCreate, EventOut, EventUpdate, VerifyCode, Token
#                                                         ↑ добавлено EventUpdate
from auth import (
    get_password_hash,
    create_access_token,
    get_current_user,
    get_db,
    verify_password
)
from verification import generate_code, store_code, verify_code          # ← новые импорты
from email_utils import send_verification_email                         # ← новые импорты
import json
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="LyfeStyler API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Registration & Verification ---
@app.post("/register", status_code=201)
def register(user: UserCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == user.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_pw = get_password_hash(user.password)
    new_user = User(email=user.email, hashed_password=hashed_pw, is_verified=False)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # Генерация и отправка кода
    code = generate_code()
    store_code(user.email, code)
    background_tasks.add_task(send_verification_email, user.email, code)

    return {"msg": "Verification code sent to your email"}

@app.post("/verify")
def verify_email(data: VerifyCode, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.is_verified:
        raise HTTPException(status_code=400, detail="Email already verified")

    if verify_code(data.email, data.code):
        user.is_verified = True
        db.commit()
        return {"msg": "Email verified successfully"}
    else:
        raise HTTPException(status_code=400, detail="Invalid or expired code")


# --- Auth (login) ---


@app.post("/token")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    # form_data.username содержит email
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.is_verified:
        raise HTTPException(status_code=403, detail="Email not verified")
    
    access_token = create_access_token(data={"sub": form_data.username})
    return {"access_token": access_token, "token_type": "bearer"}


# --- User Profile ---
@app.get("/me", response_model=UserOut)
def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user


# --- Events ---
@app.post("/events", response_model=EventOut)
def create_event(
    event: EventCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    db_event = ScheduleEvent(
        user_id=current_user.id,
        title=event.title,
        start_time=event.startTime,
        end_time=event.endTime,
        date=event.date,
        is_range=event.isRange,
        is_recurring=event.isRecurring,
        recurrence_days=event.recurrenceDays,
        reminder=event.reminder,
        reminder_minutes=event.reminderMinutes,
        color=event.color,
        description=event.description,
        tags=json.dumps(event.tags)
    )
    db.add(db_event)
    db.commit()
    db.refresh(db_event)
    return db_event

@app.put("/events/{event_id}", response_model=EventOut)
def update_event(
    event_id: int,
    update_data: EventUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    event = db.query(ScheduleEvent).filter(
        ScheduleEvent.id == event_id,
        ScheduleEvent.user_id == current_user.id
    ).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    # Обновляем поля
    if update_data.actual_start_time:
        event.actual_start_time = update_data.actual_start_time
    if update_data.actual_end_time:
        event.actual_end_time = update_data.actual_end_time
    event.completed = update_data.completed
    if update_data.notes:
        event.notes = update_data.notes

    db.commit()
    db.refresh(event)

    # Вычисляем длительность
    duration = None
    if event.actual_start_time and event.actual_end_time:
        delta = event.actual_end_time - event.actual_start_time
        duration = int(delta.total_seconds())

    return {
        "id": event.id,
        "title": event.title,
        # ... все поля из EventOut ...
        "completed": event.completed,
        "notes": event.notes,
        "duration_seconds": duration
    }

@app.get("/events/stats")
def get_event_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Возвращает статистику по событиям: мин/макс/среднее время выполнения"""
    events = db.query(ScheduleEvent).filter(
        ScheduleEvent.user_id == current_user.id,
        ScheduleEvent.completed == True
    ).all()
    
    stats = {}
    for event in events:
        if event.actual_start_time and event.actual_end_time:
            duration = (event.actual_end_time - event.actual_start_time).total_seconds()
            key = event.title  # или event.tags
            
            if key not in stats:
                stats[key] = []
            stats[key].append(duration)
    
    # Формируем результат
    result = {}
    for key, durations in stats.items():
        result[key] = {
            "min": min(durations),
            "max": max(durations),
            "avg": sum(durations) / len(durations),
            "count": len(durations)
        }
    
    return result

@app.get("/events", response_model=list[EventOut])
def get_events(
    date: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    events = db.query(ScheduleEvent).filter(
        ScheduleEvent.user_id == current_user.id,
        ScheduleEvent.date == date
    ).all()

    result = []
    for ev in events:
        duration = None
        if ev.actual_start_time and ev.actual_end_time:
            delta = ev.actual_end_time - ev.actual_start_time
            duration = int(delta.total_seconds())

        tags_list = json.loads(ev.tags) if ev.tags else []

        result.append({
            "id": ev.id,
            "title": ev.title,
            "startTime": ev.start_time,
            "endTime": ev.end_time,
            "date": ev.date,
            "isRange": ev.is_range,
            "isRecurring": ev.is_recurring,
            "recurrenceDays": ev.recurrence_days,
            "reminder": ev.reminder,
            "reminderMinutes": ev.reminder_minutes,
            "color": ev.color,
            "description": ev.description,
            "tags": tags_list,
            "completed": ev.completed,
            "notes": ev.notes,
            "duration_seconds": duration
        })
    return result

@app.post("/events/{event_id}/start")
def start_event_timer(
    event_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    event = db.query(ScheduleEvent).filter(
        ScheduleEvent.id == event_id,
        ScheduleEvent.user_id == current_user.id
    ).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    event.actual_start_time = datetime.utcnow()
    db.commit()
    return {"status": "started", "time": event.actual_start_time.isoformat()}

@app.post("/events/{event_id}/stop")
def stop_event_timer(
    event_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    event = db.query(ScheduleEvent).filter(
        ScheduleEvent.id == event_id,
        ScheduleEvent.user_id == current_user.id
    ).first()
    if not event or not event.actual_start_time:
        raise HTTPException(status_code=400, detail="Timer not started")
    
    event.actual_end_time = datetime.utcnow()
    event.completed = True
    db.commit()
    
    duration = (event.actual_end_time - event.actual_start_time).total_seconds()
    return {
        "status": "completed",
        "duration_seconds": duration,
        "world_record": False  # ← потом добавим логику рекордов
    }


@app.on_event("startup")
def startup_event():
    # Создаем все таблицы при запуске приложения
    Base.metadata.create_all(bind=engine)
    print("✅ Все таблицы созданы в базе данных")