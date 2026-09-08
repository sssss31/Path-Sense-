import re
from pydantic import BaseModel,Field,field_validator
EMAIL=re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
class Credentials(BaseModel):
    email:str=Field(max_length=255);password:str=Field(min_length=8,max_length=128)
    @field_validator("email")
    @classmethod
    def email_shape(cls,value:str)->str:
        # Basic shape check instead of EmailStr: special-use domains such as demo@smartlogistics.local must stay usable.
        value=value.strip().lower()
        if not EMAIL.match(value):raise ValueError("value is not a valid email address")
        return value
class TokenResponse(BaseModel):access_token:str;token_type:str="bearer"
class UserResponse(BaseModel):id:str;email:str;role:str
