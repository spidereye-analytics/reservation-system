# auth.py
from asyncio import iscoroutinefunction
from datetime import datetime, timedelta
from functools import wraps

from jose import JWTError, jwt, ExpiredSignatureError
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from .models import User
from .dependencies import get_db, UserRole
import os
import logging

# Get JWT secret key from environment variable
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


def authenticate_user(db: Session, email: str, password: str):
    user = db.query(User).filter(User.email == email).first()
    if not user:
        logging.error(f"User not found: {email}")
        return False
    if not verify_password(password, user.hashed_password):
        logging.error(f"Password verification failed for user: {email}")
        logging.error(f"Stored hash: {user.hashed_password}")
        logging.error(f"Provided password: {password}")
        return False
    return user


def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError as e:
        logging.error(f"JWTError: {str(e)}")
        raise credentials_exception
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise credentials_exception
    return user


def role_required(required_roles):
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, current_user: User = Depends(get_current_user), **kwargs):
            if current_user.role not in required_roles and current_user.role != UserRole.ADMIN.value:
                raise HTTPException(status_code=403, detail="User does not have the required role")
            return await func(*args, current_user=current_user, **kwargs)

        def sync_wrapper(*args, current_user: User = Depends(get_current_user), **kwargs):
            if current_user.role not in required_roles and current_user.role != UserRole.ADMIN.value:
                raise HTTPException(status_code=403, detail="User does not have the required role")
            return func(*args, current_user=current_user, **kwargs)

        if iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator