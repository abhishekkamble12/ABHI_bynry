# Part 3: API Implementation — Low-Stock Alerts

## Endpoint Overview

```
GET /api/companies/<company_id>/alerts/low-stock
```

Returns a JSON list of low-stock alerts for a given company. An alert is raised for each product-warehouse pair where the current stock quantity is at or below the configured threshold. Alerts are sorted by urgency — items closest to running out of stock appear first.

This endpoint is designed for production use: it avoids N+1 queries, handles soft-deleted entities, guards against division-by-zero, and returns a well-structured response for both empty and non-empty result sets.

---

## Assumptions

- **Recent sales activity** — "Recent" means stock-out events (`delta < 0`) recorded in `inventory_history` within the last 30 calendar days.
- **Daily sales rate** — Calculated as `abs(sum of negative deltas in last 30 days) / 30`. This gives the average units sold per day over the look-back window.
- **Days until stockout** — Estimated as `current_quantity / daily_sales_rate`, rounded to one decimal place. Returns `null` if `daily_sales_rate` is zero (no recent sales recorded), since a stockout date cannot be predicted.
- **Low stock** — A product-warehouse pair is considered low-stock when `current_quantity <= low_stock_threshold`. The inventory-level threshold overrides the product-level threshold when set.
- **Preferred supplier** — The supplier linked via `product_suppliers` with `is_preferred = TRUE`. If no preferred supplier is set, `preferred_supplier` is `null` in the response.

---

## Implementation

```python
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
```

---

## Edge Cases Handled

- **N+1 query prevention** — Preferred suppliers for all alerted products are fetched in a single bulk query using `.in_(product_ids)`, then stored in a `supplier_map` dictionary keyed by `product_id`. Supplier data is looked up in O(1) during response construction — no per-alert database round-trips.

- **Division-by-zero protection** — If `daily_rate` is 0 (no stock-out events in the last 30 days), `days_until_stockout` is set to `None` rather than attempting a division. This prevents a `ZeroDivisionError` and correctly signals to the client that a stockout date cannot be estimated.

- **Soft-delete filtering** — The query filters `Product.deleted_at.is_(None)` and `Warehouse.deleted_at.is_(None)`, ensuring that decommissioned products and closed warehouses are invisible to the endpoint without requiring hard deletes.

- **Empty result handling** — When no low-stock rows are found, the endpoint returns `{"alerts": [], "total": 0}` with HTTP `200 OK`. This is intentional — the absence of alerts is a valid, non-error state and should not return `404`.

- **Authorisation** — The `@require_auth` decorator is applied at the route level, enforcing authentication before any database work is performed. In production, this decorator would validate a JWT and reject unauthenticated requests with `401 Unauthorized`.

- **Threshold override** — `func.coalesce(Inventory.low_stock_threshold, Product.low_stock_threshold)` in the filter ensures that an inventory-level threshold (when set) takes precedence over the product-level default, without requiring application-level branching in the query.

---

## Additional Questions for the Product Team

1. **Pagination** — For large companies with many warehouses, this endpoint could return hundreds of alerts in a single response. Should we add `limit`/`offset` query parameters or cursor-based pagination?

2. **Alert suppression** — Should there be a mechanism to acknowledge or snooze an alert so it does not reappear on the next poll? If so, we would need an `alert_suppressions` table or a similar state-tracking mechanism.

3. **Bundle stock** — How should low-stock be calculated for bundle products — based on the bundle's own inventory row, derived from the availability of its components, or both? The current implementation treats bundles the same as standard products.

4. **Look-back window configurability** — Is 30 days the right window for all product types? Fast-moving items (e.g., consumables) may need a shorter window for accurate burn-rate estimates; slow-moving items may need a longer one. Should this be configurable per product or product type?

5. **Caching** — Low-stock checks can be expensive for large catalogues. Should results be cached (e.g., in Redis) with an invalidation strategy triggered on inventory writes?
