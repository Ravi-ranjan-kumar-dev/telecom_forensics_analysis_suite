#crud.py
from sqlalchemy.orm import Session
from . import models, schemas
from .auth import get_password_hash


def get_user_by_username(db: Session, username: str):
    return db.query(models.User).filter(models.User.username == username).first()


def create_user(db: Session, user: schemas.UserCreate):
    hashed_password = get_password_hash(user.password)
    db_user = models.User(
        username=user.username,
        password_hash=hashed_password,
        role="viewer"  # हमेशा viewer
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user
# नया: किसी user का role बदलने के लिए (सिर्फ admin के लिए)
def update_user_role(db: Session, username: str, new_role: str):
    user = get_user_by_username(db, username)
    if not user:
        return None
    setattr(user, "role", new_role)
    db.commit()
    db.refresh(user)
    return user
