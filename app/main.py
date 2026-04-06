from datetime import datetime
from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, extract
from typing import Optional
from app.database import get_db
from app.models import User, Expense
from app.schemas import (
    UserCreate, UserResponse, LoginRequest, TokenResponse,
    ExpenseCreate, ExpenseResponse, ExpenseUpdate, CategorySummary
)
from app.security import hash_password, verify_password, create_access_token, decode_access_token

app = FastAPI(title="SpendSmart API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


# ---------- Auth Dependency ----------

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> User:
    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception

    user_id = payload.get("sub")
    if user_id is None:
        raise credentials_exception

    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()
    if user is None:
        raise credentials_exception

    return user


# ---------- Root ----------

@app.get("/")
async def home():
    return {"message": "SpendSmart API is alive!"}


# ---------- Auth Routes ----------

@app.post("/auth/register", response_model=UserResponse, status_code=201)
async def register(user: UserCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == user.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")
    
    # Block disposable email domains
    blocked_domains = [
        "mailinator.com", "tempmail.com", "guerrillamail.com",
        "10minutemail.com", "throwaway.email", "fakeinbox.com",
        "yopmail.com", "trashmail.com", "maildrop.cc"
    ]
    email_domain = user.email.split("@")[1].lower()
    if email_domain in blocked_domains:
        raise HTTPException(status_code=400, detail="Please use a real email address")

    new_user = User(
        name=user.name,
        email=user.email,
        hashed_password=hash_password(user.password)
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return new_user


@app.post("/auth/login", response_model=TokenResponse)
async def login(credentials: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == credentials.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token(data={"sub": str(user.id)})
    return TokenResponse(access_token=token)


# ---------- User Routes ----------

@app.get("/users/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user


# ---------- Expense Routes ----------

@app.post("/expenses", response_model=ExpenseResponse, status_code=201)
async def create_expense(
    expense: ExpenseCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    new_expense = Expense(
        title=expense.title,
        amount=expense.amount,
        category=expense.category,
        notes=expense.notes,
        date=expense.date or datetime.utcnow(),
        user_id=current_user.id
    )
    db.add(new_expense)
    await db.commit()
    await db.refresh(new_expense)
    return new_expense


@app.get("/expenses", response_model=list[ExpenseResponse])
async def get_expenses(
    # Optional filters — all default to None meaning "no filter"
    category: Optional[str] = Query(None, description="Filter by category"),
    month: Optional[int] = Query(None, ge=1, le=12, description="Filter by month (1-12)"),
    year: Optional[int] = Query(None, ge=2000, le=2100, description="Filter by year"),
    # Pagination
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(10, ge=1, le=100, description="Results per page"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Start with base query — always filter by current user
    query = select(Expense).where(Expense.user_id == current_user.id)

    # Add filters only if provided
    if category:
        query = query.where(Expense.category == category)

    if month:
        query = query.where(extract('month', Expense.date) == month)

    if year:
        query = query.where(extract('year', Expense.date) == year)

    # Order by newest first
    query = query.order_by(Expense.date.desc())

    # Pagination — skip (page-1)*limit rows, take limit rows
    query = query.offset((page - 1) * limit).limit(limit)

    result = await db.execute(query)
    return result.scalars().all()


@app.get("/expenses/{expense_id}", response_model=ExpenseResponse)
async def get_expense(
    expense_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(Expense).where(
            Expense.id == expense_id,
            Expense.user_id == current_user.id
        )
    )
    expense = result.scalar_one_or_none()
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")
    return expense


@app.put("/expenses/{expense_id}", response_model=ExpenseResponse)
async def update_expense(
    expense_id: int,
    expense_update: ExpenseUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(Expense).where(
            Expense.id == expense_id,
            Expense.user_id == current_user.id
        )
    )
    expense = result.scalar_one_or_none()
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")

    expense.title = expense_update.title
    expense.amount = expense_update.amount
    expense.category = expense_update.category
    expense.notes = expense_update.notes
    await db.commit()
    await db.refresh(expense)
    return expense


@app.delete("/expenses/{expense_id}")
async def delete_expense(
    expense_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(Expense).where(
            Expense.id == expense_id,
            Expense.user_id == current_user.id
        )
    )
    expense = result.scalar_one_or_none()
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")

    await db.delete(expense)
    await db.commit()
    return {"message": f"Expense {expense_id} deleted"}


# ---------- Summary Routes ----------

@app.get("/expenses/summary/by-category", response_model=list[CategorySummary])
async def summary_by_category(
    month: Optional[int] = Query(None, ge=1, le=12),
    year: Optional[int] = Query(None, ge=2000, le=2100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = (
        select(Expense.category, func.sum(Expense.amount).label("total"))
        .where(Expense.user_id == current_user.id)
    )

    if month:
        query = query.where(extract('month', Expense.date) == month)
    if year:
        query = query.where(extract('year', Expense.date) == year)

    query = query.group_by(Expense.category)
    result = await db.execute(query)
    rows = result.all()
    return [CategorySummary(category=row[0], total=row[1]) for row in rows]


@app.get("/expenses/summary/total")
async def total_spending(
    month: Optional[int] = Query(None, ge=1, le=12),
    year: Optional[int] = Query(None, ge=2000, le=2100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = select(func.sum(Expense.amount)).where(
        Expense.user_id == current_user.id
    )

    if month:
        query = query.where(extract('month', Expense.date) == month)
    if year:
        query = query.where(extract('year', Expense.date) == year)

    result = await db.execute(query)
    total = result.scalar() or 0
    return {"total": total}


@app.get("/expenses/summary/monthly")
async def monthly_summary(
    year: Optional[int] = Query(None, ge=2000, le=2100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Group expenses by month and sum amounts
    query = (
        select(
            extract('month', Expense.date).label('month'),
            extract('year', Expense.date).label('year'),
            func.sum(Expense.amount).label('total')
        )
        .where(Expense.user_id == current_user.id)
    )

    if year:
        query = query.where(extract('year', Expense.date) == year)

    query = query.group_by(
        extract('year', Expense.date),
        extract('month', Expense.date)
    ).order_by(
        extract('year', Expense.date),
        extract('month', Expense.date)
    )

    result = await db.execute(query)
    rows = result.all()
    return [
        {"month": int(row[0]), "year": int(row[1]), "total": row[2]}
        for row in rows
    ]