"""
SQLAlchemy ORM models for StockFlow.

All eight models mirror the DDL schema defined in PART2_Database_Design.md.
`db` is imported from app.main (where SQLAlchemy() is instantiated) to avoid
circular imports — models.py must never create its own SQLAlchemy instance.
"""

from datetime import datetime

from sqlalchemy import Numeric, UniqueConstraint

from app.main import db


class Company(db.Model):
    """Multi-tenant anchor table. Every warehouse and product belongs to a company."""

    __tablename__ = "companies"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    deleted_at = db.Column(db.DateTime, nullable=True)  # soft-delete timestamp


class Warehouse(db.Model):
    """Physical storage locations, scoped to a company."""

    __tablename__ = "warehouses"

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(
        db.Integer, db.ForeignKey("companies.id"), nullable=False
    )
    name = db.Column(db.String(255), nullable=False)
    location = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    deleted_at = db.Column(db.DateTime, nullable=True)  # soft-delete timestamp


class Product(db.Model):
    """Product catalogue, scoped to a company. SKU is unique per company."""

    __tablename__ = "products"
    __table_args__ = (
        # Enforce company-scoped SKU uniqueness — two companies may share a SKU string
        UniqueConstraint("company_id", "sku", name="uq_products_company_sku"),
    )

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(
        db.Integer, db.ForeignKey("companies.id"), nullable=False
    )
    name = db.Column(db.String(255), nullable=False)
    sku = db.Column(db.String(100), nullable=False)
    # NUMERIC(12,2) avoids floating-point rounding errors in financial calculations
    price = db.Column(Numeric(12, 2), nullable=False)
    low_stock_threshold = db.Column(db.Integer, nullable=False, default=10)
    is_bundle = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    deleted_at = db.Column(db.DateTime, nullable=True)  # soft-delete timestamp


class ProductBundleItem(db.Model):
    """
    Junction table for bundle composition (many-to-many self-referential on products).
    A bundle product contains one or more component products with a given quantity.
    """

    __tablename__ = "product_bundle_items"
    __table_args__ = (
        UniqueConstraint(
            "bundle_product_id",
            "component_product_id",
            name="uq_bundle_items_bundle_component",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    bundle_product_id = db.Column(
        db.Integer, db.ForeignKey("products.id"), nullable=False
    )
    component_product_id = db.Column(
        db.Integer, db.ForeignKey("products.id"), nullable=False
    )
    quantity = db.Column(db.Integer, nullable=False, default=1)


class Inventory(db.Model):
    """
    Current stock levels — one row per product-warehouse pair.
    Designed for fast point-in-time reads; historical movements live in InventoryHistory.
    """

    __tablename__ = "inventory"
    __table_args__ = (
        UniqueConstraint(
            "product_id", "warehouse_id", name="uq_inventory_product_warehouse"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(
        db.Integer, db.ForeignKey("products.id"), nullable=False
    )
    warehouse_id = db.Column(
        db.Integer, db.ForeignKey("warehouses.id"), nullable=False
    )
    quantity = db.Column(db.Integer, nullable=False, default=0)
    # When set, this threshold overrides the product-level low_stock_threshold
    low_stock_threshold = db.Column(db.Integer, nullable=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class InventoryHistory(db.Model):
    """
    Append-only audit log of stock movements.
    delta > 0 means stock received; delta < 0 means stock consumed/removed.
    Storing deltas (not absolute values) avoids update anomalies and allows
    reconstruction of any historical stock level by summing deltas.
    """

    __tablename__ = "inventory_history"

    id = db.Column(db.Integer, primary_key=True)
    inventory_id = db.Column(
        db.Integer, db.ForeignKey("inventory.id"), nullable=False
    )
    # positive = stock in, negative = stock out
    delta = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class Supplier(db.Model):
    """Supplier master data. Not scoped to a company — suppliers are global."""

    __tablename__ = "suppliers"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(255), nullable=True)
    phone = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    deleted_at = db.Column(db.DateTime, nullable=True)  # soft-delete timestamp


class ProductSupplier(db.Model):
    """
    Junction table linking products to their suppliers.
    is_preferred flags the primary supplier for a product (used in low-stock alerts).
    """

    __tablename__ = "product_suppliers"
    __table_args__ = (
        UniqueConstraint(
            "product_id", "supplier_id", name="uq_product_suppliers_product_supplier"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(
        db.Integer, db.ForeignKey("products.id"), nullable=False
    )
    supplier_id = db.Column(
        db.Integer, db.ForeignKey("suppliers.id"), nullable=False
    )
    is_preferred = db.Column(db.Boolean, nullable=False, default=False)
    lead_time_days = db.Column(db.Integer, nullable=True)
