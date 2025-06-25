from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey, Boolean, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base

class User(Base):
    __tablename__ = "Users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    password = Column(String(255), nullable=False)
    createdAt = Column(DateTime(timezone=True), server_default=func.now())
    updatedAt = Column(DateTime(timezone=True), onupdate=func.now())

class Brand(Base):
    __tablename__ = "Brands"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    createdAt = Column(DateTime(timezone=True), server_default=func.now())
    updatedAt = Column(DateTime(timezone=True), onupdate=func.now())
    
    products = relationship("Product", back_populates="brand")

class Product(Base):
    __tablename__ = "Products"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    price = Column(Float, nullable=False)
    brandId = Column(Integer, ForeignKey("Brands.id"))
    createdAt = Column(DateTime(timezone=True), server_default=func.now())
    updatedAt = Column(DateTime(timezone=True), onupdate=func.now())
    
    brand = relationship("Brand", back_populates="products")
    stocks = relationship("Stock", back_populates="product")

class Stock(Base):
    __tablename__ = "Stocks"
    
    id = Column(Integer, primary_key=True, index=True)
    quantity = Column(Integer, nullable=False)
    productId = Column(Integer, ForeignKey("Products.id"))
    createdAt = Column(DateTime(timezone=True), server_default=func.now())
    updatedAt = Column(DateTime(timezone=True), onupdate=func.now())
    
    product = relationship("Product", back_populates="stocks")

class Customer(Base):
    __tablename__ = "Customers"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255))
    phone = Column(String(255))
    address = Column(Text)
    createdAt = Column(DateTime(timezone=True), server_default=func.now())
    updatedAt = Column(DateTime(timezone=True), onupdate=func.now())
    
    sales = relationship("Sale", back_populates="customer")

class Provider(Base):
    __tablename__ = "Providers"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255))
    phone = Column(String(255))
    address = Column(Text)
    createdAt = Column(DateTime(timezone=True), server_default=func.now())
    updatedAt = Column(DateTime(timezone=True), onupdate=func.now())

class Sale(Base):
    __tablename__ = "Sales"
    
    id = Column(Integer, primary_key=True, index=True)
    total = Column(Float, nullable=False)
    customerId = Column(Integer, ForeignKey("Customers.id"))
    userId = Column(Integer, ForeignKey("Users.id"))
    createdAt = Column(DateTime(timezone=True), server_default=func.now())
    updatedAt = Column(DateTime(timezone=True), onupdate=func.now())
    
    customer = relationship("Customer", back_populates="sales")

class Budget(Base):
    __tablename__ = "Budgets"
    
    id = Column(Integer, primary_key=True, index=True)
    total = Column(Float, nullable=False)
    customerId = Column(Integer, ForeignKey("Customers.id"))
    userId = Column(Integer, ForeignKey("Users.id"))
    limitDate = Column(DateTime(timezone=True))
    isPaid = Column(Boolean, default=False)
    createdAt = Column(DateTime(timezone=True), server_default=func.now())
    updatedAt = Column(DateTime(timezone=True), onupdate=func.now())

class Cashier(Base):
    __tablename__ = "Cashiers"
    
    id = Column(Integer, primary_key=True, index=True)
    initialMoney = Column(Float, nullable=False)
    finalMoney = Column(Float)
    isOpen = Column(Boolean, default=True)
    userId = Column(Integer, ForeignKey("Users.id"))
    createdAt = Column(DateTime(timezone=True), server_default=func.now())
    updatedAt = Column(DateTime(timezone=True), onupdate=func.now()) 