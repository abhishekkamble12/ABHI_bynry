"""
StockFlow Flask routes blueprint.

Contains two endpoints:
  POST /api/companies/<company_id>/products       — create a new product
  GET  /api/companies/<company_id>/alerts/low-stock — list low-stock alerts
"""

from datetime import datetime, timedelta

from flask import Blueprint, jsonify, request
from sqlalchemy import func

from app.auth import require_auth
from app.main import db
from app.models import (
    Company,
    Inventory,
    InventoryHistory,
    Product,
    ProductSupplier,
    Supplier,
    Warehouse,
)

# All routes are prefixed with /api
bp = Blueprint("main", __name__, url_prefix="/api")

# Look-back window for "recent sales" used in low-stock calculations
RECENT_DAYS = 30


@bp.route("/companies/<int:company_id>/products", methods=["POST"])
@require_auth
def create_product(company_id):
    """
    Create a new product for a company.

    POST /api/companies/<company_id>/products
    Body (JSON): { name, sku, price, low_stock_threshold (optional) }
    Returns: 201 with the created product, or 400/409/500 on error.
    """
    data = request.get_json() or {}

    # --- Input validation: required fields must be present and non-empty ---
    required_fields = ["name", "sku", "price"]
    for field in required_fields:
        if not data.get(field):
            return jsonify({"error": f"Missing required field: {field}"}), 400

    name = str(data["name"]).strip()
    sku = str(data["sku"]).strip()

    # Validate price is a non-negative number
    try:
        price = float(data["price"])
        if price < 0:
            raise ValueError("price must be non-negative")
    except (ValueError, TypeError):
        return jsonify({"error": "price must be a non-negative number"}), 400

    # --- Company-scoped SKU uniqueness check ---
    # Two companies may share a SKU string, but within one company SKUs must be unique
    existing = Product.query.filter_by(
        sku=sku, company_id=company_id, deleted_at=None
    ).first()
    if existing:
        return jsonify({"error": f"SKU '{sku}' already exists for this company"}), 409

    # --- Atomic transaction: add product and flush to get the DB-assigned id ---
    try:
        product = Product(
            company_id=company_id,
            name=name,
            sku=sku,
            price=price,
            low_stock_threshold=data.get("low_stock_threshold", 10),
        )
        db.session.add(product)
        # flush() sends the INSERT to the DB within the current transaction,
        # making product.id available without committing yet
        db.session.flush()
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Database error", "detail": str(e)}), 500

    return jsonify({
        "id": product.id,
        "company_id": product.company_id,
        "name": product.name,
        "sku": product.sku,
        "price": str(product.price),
    }), 201


@bp.route("/companies/<int:company_id>/alerts/low-stock", methods=["GET"])
@require_auth
def low_stock_alerts(company_id):
    """
    Return low-stock alerts for a company, sorted by urgency.

    GET /api/companies/<company_id>/alerts/low-stock
    Returns: 200 with a list of alerts (may be empty).

    An alert is raised when a product's current quantity falls at or below its
    low_stock_threshold. Each alert includes an estimated days_until_stockout
    based on average daily sales over the last 30 days.
    """
    thirty_days_ago = datetime.utcnow() - timedelta(days=RECENT_DAYS)

    # Subquery: total units sold per inventory row in the last 30 days.
    # delta is negative for sales, so we sum and take abs() later.
    recent_sales_sq = (
        db.session.query(
            InventoryHistory.inventory_id,
            func.sum(InventoryHistory.delta).label("total_sold"),
        )
        .filter(
            InventoryHistory.delta < 0,  # only stock-out events
            InventoryHistory.created_at >= thirty_days_ago,
        )
        .group_by(InventoryHistory.inventory_id)
        .subquery()
    )

    # Main query: inventory rows at or below threshold, joined to product and warehouse.
    # outerjoin on recent_sales_sq so products with no recent sales are still included.
    rows = (
        db.session.query(Inventory, Product, Warehouse, recent_sales_sq.c.total_sold)
        .join(Product, Inventory.product_id == Product.id)
        .join(Warehouse, Inventory.warehouse_id == Warehouse.id)
        .outerjoin(recent_sales_sq, recent_sales_sq.c.inventory_id == Inventory.id)
        .filter(
            Product.company_id == company_id,
            Product.deleted_at.is_(None),       # exclude soft-deleted products
            Warehouse.deleted_at.is_(None),     # exclude soft-deleted warehouses
            # Use inventory-level threshold if set; fall back to product-level threshold
            Inventory.quantity <= func.coalesce(
                Inventory.low_stock_threshold, Product.low_stock_threshold
            ),
        )
        .all()
    )

    # Return early with an empty list — 200 is correct here (no alerts is a valid state)
    if not rows:
        return jsonify({"alerts": [], "total": 0}), 200

    # Bulk-fetch preferred suppliers to avoid N+1 queries.
    # One query for all product IDs, then build a dict for O(1) lookup.
    product_ids = [row.Product.id for row in rows]
    preferred_supplier_rows = (
        db.session.query(ProductSupplier, Supplier)
        .join(Supplier, ProductSupplier.supplier_id == Supplier.id)
        .filter(
            ProductSupplier.product_id.in_(product_ids),
            ProductSupplier.is_preferred.is_(True),
        )
        .all()
    )
    # Map product_id → Supplier object for fast lookup during response construction
    supplier_map = {ps.ProductSupplier.product_id: ps.Supplier for ps in preferred_supplier_rows}

    # Build the response payload
    alerts = []
    for row in rows:
        inv, product, warehouse, total_sold = row

        # Calculate average daily sales rate; total_sold is negative (stock-out deltas)
        total_sold_abs = abs(total_sold) if total_sold else 0
        daily_rate = total_sold_abs / RECENT_DAYS

        if daily_rate > 0:
            # Estimate how many days until stock runs out at the current burn rate
            days_until_stockout = round(inv.quantity / daily_rate, 1)
        else:
            # No recent sales — cannot predict stockout date
            days_until_stockout = None

        supplier = supplier_map.get(product.id)

        alerts.append({
            "product_id": product.id,
            "product_name": product.name,
            "sku": product.sku,
            "warehouse_id": warehouse.id,
            "warehouse_name": warehouse.name,
            "current_quantity": inv.quantity,
            "low_stock_threshold": (
                inv.low_stock_threshold
                if inv.low_stock_threshold is not None
                else product.low_stock_threshold
            ),
            "daily_sales_rate": round(daily_rate, 2),
            "days_until_stockout": days_until_stockout,
            "preferred_supplier": {
                "id": supplier.id,
                "name": supplier.name,
                "email": supplier.email,
            } if supplier else None,
        })

    # Sort by urgency: known stockout dates ascending first, then unknowns (None) at end
    alerts.sort(
        key=lambda a: (a["days_until_stockout"] is None, a["days_until_stockout"] or 0)
    )

    return jsonify({"alerts": alerts, "total": len(alerts)}), 200
