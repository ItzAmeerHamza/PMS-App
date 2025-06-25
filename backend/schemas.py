from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

# User schemas
class UserBase(BaseModel):
    username: str
    name: str

class UserCreate(UserBase):
    password: str

class UserUpdate(BaseModel):
    username: Optional[str] = None
    name: Optional[str] = None
    password: Optional[str] = None

class User(UserBase):
    id: int
    createdAt: datetime
    updatedAt: Optional[datetime] = None

    class Config:
        from_attributes = True

# Brand schemas
class BrandBase(BaseModel):
    name: str

class BrandCreate(BrandBase):
    pass

class BrandUpdate(BaseModel):
    name: Optional[str] = None

class Brand(BrandBase):
    id: int
    createdAt: datetime
    updatedAt: Optional[datetime] = None

    class Config:
        from_attributes = True

# Product schemas
class ProductBase(BaseModel):
    name: str
    price: float
    brandId: int

class ProductCreate(ProductBase):
    pass

class ProductUpdate(BaseModel):
    name: Optional[str] = None
    price: Optional[float] = None
    brandId: Optional[int] = None

class Product(ProductBase):
    id: int
    createdAt: datetime
    updatedAt: Optional[datetime] = None
    brand: Optional[Brand] = None

    class Config:
        from_attributes = True

# Stock schemas
class StockBase(BaseModel):
    quantity: int
    productId: int

class StockCreate(StockBase):
    pass

class StockUpdate(BaseModel):
    quantity: Optional[int] = None
    productId: Optional[int] = None

class Stock(StockBase):
    id: int
    createdAt: datetime
    updatedAt: Optional[datetime] = None
    product: Optional[Product] = None

    class Config:
        from_attributes = True

# Customer schemas
class CustomerBase(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None

class CustomerCreate(CustomerBase):
    pass

class CustomerUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None

class Customer(CustomerBase):
    id: int
    createdAt: datetime
    updatedAt: Optional[datetime] = None

    class Config:
        from_attributes = True

# Provider schemas
class ProviderBase(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None

class ProviderCreate(ProviderBase):
    pass

class ProviderUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None

class Provider(ProviderBase):
    id: int
    createdAt: datetime
    updatedAt: Optional[datetime] = None

    class Config:
        from_attributes = True

# Sale schemas
class SaleBase(BaseModel):
    total: float
    customerId: int
    userId: int

class SaleCreate(SaleBase):
    pass

class SaleUpdate(BaseModel):
    total: Optional[float] = None
    customerId: Optional[int] = None
    userId: Optional[int] = None

class Sale(SaleBase):
    id: int
    createdAt: datetime
    updatedAt: Optional[datetime] = None
    customer: Optional[Customer] = None

    class Config:
        from_attributes = True

# Budget schemas
class BudgetBase(BaseModel):
    total: float
    customerId: int
    userId: int
    limitDate: Optional[datetime] = None
    isPaid: bool = False

class BudgetCreate(BudgetBase):
    pass

class BudgetUpdate(BaseModel):
    total: Optional[float] = None
    customerId: Optional[int] = None
    userId: Optional[int] = None
    limitDate: Optional[datetime] = None
    isPaid: Optional[bool] = None

class Budget(BudgetBase):
    id: int
    createdAt: datetime
    updatedAt: Optional[datetime] = None
    customer: Optional[Customer] = None

    class Config:
        from_attributes = True

# Cashier schemas
class CashierBase(BaseModel):
    initialMoney: float
    userId: int

class CashierCreate(CashierBase):
    pass

class CashierUpdate(BaseModel):
    initialMoney: Optional[float] = None
    finalMoney: Optional[float] = None
    isOpen: Optional[bool] = None
    userId: Optional[int] = None

class Cashier(CashierBase):
    id: int
    finalMoney: Optional[float] = None
    isOpen: bool = True
    createdAt: datetime
    updatedAt: Optional[datetime] = None

    class Config:
        from_attributes = True

# Token schemas
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None 