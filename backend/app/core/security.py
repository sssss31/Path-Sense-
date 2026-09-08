from datetime import datetime,timedelta,timezone
import bcrypt
from jose import JWTError,jwt
from app.core.config import get_settings
# bcrypt is called directly: passlib 1.7.x is incompatible with bcrypt>=4.1 (missing __about__, 72-byte guard).
# Hashes remain standard "$2b$" strings, so existing passlib-generated hashes keep verifying.
def hash_password(value:str)->str:return bcrypt.hashpw(value.encode("utf-8")[:72],bcrypt.gensalt()).decode("utf-8")
def verify_password(value:str,hashed:str)->bool:
    try:return bcrypt.checkpw(value.encode("utf-8")[:72],hashed.encode("utf-8"))
    except (ValueError,TypeError):return False
def create_token(user_id:str)->str:
    s=get_settings();expires=datetime.now(timezone.utc)+timedelta(minutes=s.access_token_minutes)
    return jwt.encode({"sub":user_id,"exp":expires},s.jwt_secret,algorithm=s.jwt_algorithm)
def decode_token(token:str)->str:
    s=get_settings();payload=jwt.decode(token,s.jwt_secret,algorithms=[s.jwt_algorithm]);return payload["sub"]
