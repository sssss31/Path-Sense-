import uuid
from fastapi import APIRouter,Depends,HTTPException,status
from fastapi.security import HTTPAuthorizationCredentials,HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.security import create_token,decode_token,hash_password,verify_password
from app.database.session import get_session
from app.models import User
from app.schemas.auth import Credentials,TokenResponse,UserResponse
router=APIRouter(prefix="/auth",tags=["auth"]);bearer=HTTPBearer(auto_error=False)
async def current_user(credentials:HTTPAuthorizationCredentials|None=Depends(bearer),session:AsyncSession=Depends(get_session)):
    if not credentials:raise HTTPException(status_code=401,detail="Authentication required")
    try:user_id=uuid.UUID(decode_token(credentials.credentials))
    except Exception:raise HTTPException(status_code=401,detail="Invalid or expired token")
    user=await session.get(User,user_id)
    if not user or not user.is_active:raise HTTPException(status_code=401,detail="User unavailable")
    return user
async def optional_user(credentials:HTTPAuthorizationCredentials|None=Depends(bearer),session:AsyncSession=Depends(get_session)):
    if not credentials:return None
    try:return await current_user(credentials,session)
    except HTTPException:return None
@router.post("/register",response_model=TokenResponse,status_code=201)
async def register(data:Credentials,session:AsyncSession=Depends(get_session)):
    if await session.scalar(select(User).where(User.email==data.email.lower())):raise HTTPException(status_code=409,detail="Email already registered")
    user=User(email=data.email.lower(),password_hash=hash_password(data.password));session.add(user);await session.commit();await session.refresh(user);return TokenResponse(access_token=create_token(str(user.id)))
@router.post("/login",response_model=TokenResponse)
async def login(data:Credentials,session:AsyncSession=Depends(get_session)):
    user=await session.scalar(select(User).where(User.email==data.email.lower()))
    if not user or not verify_password(data.password,user.password_hash):raise HTTPException(status_code=401,detail="Invalid email or password")
    return TokenResponse(access_token=create_token(str(user.id)))
@router.get("/me",response_model=UserResponse)
async def me(user:User=Depends(current_user)):return UserResponse(id=str(user.id),email=user.email,role=user.role)
@router.post("/logout",status_code=204)
async def logout():return None
