from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime


# ---------- User Schemas ----------

class UserCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=50)
    email: str
    password: str = Field(..., min_length=8)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    created_at: datetime


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ---------- Expense Schemas ----------

class ExpenseCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=100)
    amount: float = Field(..., gt=0)  # gt=0 means must be greater than 0
    category: str = Field(..., min_length=1, max_length=50)
    notes: Optional[str] = None


class ExpenseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    amount: float
    category: str
    notes: Optional[str]
    date: datetime
    user_id: int


class ExpenseUpdate(BaseModel):
    title: str = Field(..., min_length=1, max_length=100)
    amount: float = Field(..., gt=0)
    category: str = Field(..., min_length=1, max_length=50)
    notes: Optional[str] = None


# ---------- Summary Schema ----------

class CategorySummary(BaseModel):
    category: str
    total: float