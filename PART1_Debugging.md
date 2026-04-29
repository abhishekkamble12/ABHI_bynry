# Part 1: Code Review & Debugging

## Overview

This section documents a code review of a Flask endpoint responsible for creating products in the StockFlow inventory system. The original `create_product` endpoint contained six distinct bugs spanning correctness, security, and reliability. Each bug is identified below with its production impact and the fix applied in the corrected implementation.

---

## Identified Bugs

| # | Issue | Production Impact | Fix |
|---|-------|-------------------|-----|
| 1 | Missing `@require_auth` decorator | Any unauthenticated caller can create products in any company's catalogue | Add `@require_auth` above the route so authentication is enforced before any business logic runs |
| 2 | No input validation on required fields | Missing `name`, `sku`, or `price` raises an unhandled `KeyError` (500); empty strings silently create corrupt records | Validate all required fields are present and non-empty before touching the database; return `400` with a clear message |
| 3 | SKU uniqueness not scoped to company | Two products with the same SKU can be created within the same company, corrupting inventory lookups | Query `Product` filtered by both `sku` and `company_id`; return `409 Conflict` if a match exists |
| 4 | Missing `db.session.flush()` before commit | `product.id` is `None` when passed to downstream logic; foreign key violations are possible | Call `db.session.flush()` after `db.session.add(product)` to get the DB-assigned `id` within the current transaction, before committing |
| 5 | No `db.session.rollback()` on error | A failed transaction leaves the session in a dirty state, causing all subsequent requests in the same session to fail | Wrap all DB work in `try/except`; call `db.session.rollback()` in the `except` block to restore a clean session state |
| 6 | Returns `200 OK` instead of `201 Created` on success | Clients cannot distinguish "resource created" from "request processed", breaking REST semantics | Return `jsonify(product_data), 201` on successful creation |

---

## Corrected Implementation

```python
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
```

---

## Key Design Decisions

### Atomic Transactions

SQLAlchemy's session lifecycle has three distinct steps used here:

- `db.session.add(product)` — stages the new `Product` object in the session (no SQL sent yet).
- `db.session.flush()` — sends the `INSERT` to the database within the current transaction, making the auto-generated `product.id` available for use, without committing. This is critical when downstream logic (e.g., creating a related `Inventory` row) needs the new primary key.
- `db.session.commit()` — finalises the transaction. If this succeeds, the row is permanently written.
- `db.session.rollback()` in the `except` block — if any step raises an exception, rollback returns the session to a clean state so subsequent requests are not affected.

### `@require_auth` Decorator

The decorator is applied at the route level, above the function body, so authentication is enforced before any business logic or database access occurs. In this repository, `require_auth` is a stub that passes all requests through — in production it would validate a JWT or session token and reject unauthenticated requests with `401 Unauthorized`.

### Company-Scoped SKU Uniqueness

SKUs are unique per company, not globally. This means two different companies can legitimately use the same SKU string (e.g., both use `"WIDGET-001"` for different products). The uniqueness check queries `Product` filtered by both `sku` and `company_id`, and returns `409 Conflict` with a descriptive message if a duplicate is found — rather than relying on a database constraint violation, which would surface as an opaque `IntegrityError`.
