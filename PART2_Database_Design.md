# Part 2: Database Design

## Overview

This section presents the relational database schema for StockFlow, a multi-tenant B2B SaaS inventory management system. The schema supports multiple companies (tenants), each with their own warehouses, product catalogues, and inventory records. It is designed for correctness, auditability, and query performance — with soft deletes to preserve historical data, an append-only audit log for stock movements, and company-scoped constraints to enforce tenant isolation.

---

## Schema DDL

```sql
-- Multi-tenant anchor table. Every warehouse and product belongs to a company.
CREATE TABLE companies (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(255) NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_at  TIMESTAMP
);

-- Physical storage locations, scoped to a company.
CREATE TABLE warehouses (
    id          SERIAL PRIMARY KEY,
    company_id  INTEGER NOT NULL REFERENCES companies(id),
    name        VARCHAR(255) NOT NULL,
    location    TEXT,
    created_at  TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_at  TIMESTAMP
);

-- Product catalogue, scoped to a company. SKU is unique per company.
CREATE TABLE products (
    id                  SERIAL PRIMARY KEY,
    company_id          INTEGER NOT NULL REFERENCES companies(id),
    name                VARCHAR(255) NOT NULL,
    sku                 VARCHAR(100) NOT NULL,
    price               NUMERIC(12, 2) NOT NULL,
    low_stock_threshold INTEGER NOT NULL DEFAULT 10,
    is_bundle           BOOLEAN NOT NULL DEFAULT FALSE,
    created_at          TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_at          TIMESTAMP,
    UNIQUE (company_id, sku)
);

-- Junction table for bundle composition (many-to-many self-referential on products).
-- A bundle product contains one or more component products with a given quantity.
CREATE TABLE product_bundle_items (
    id                   SERIAL PRIMARY KEY,
    bundle_product_id    INTEGER NOT NULL REFERENCES products(id),
    component_product_id INTEGER NOT NULL REFERENCES products(id),
    quantity             INTEGER NOT NULL DEFAULT 1,
    UNIQUE (bundle_product_id, component_product_id)
);

-- Current stock levels — one row per product-warehouse pair.
-- Designed for fast point-in-time reads; historical movements live in inventory_history.
CREATE TABLE inventory (
    id                  SERIAL PRIMARY KEY,
    product_id          INTEGER NOT NULL REFERENCES products(id),
    warehouse_id        INTEGER NOT NULL REFERENCES warehouses(id),
    quantity            INTEGER NOT NULL DEFAULT 0,
    low_stock_threshold INTEGER,  -- overrides product-level threshold when set
    updated_at          TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (product_id, warehouse_id)
);

-- Append-only audit log of all stock movements.
-- delta > 0 = stock received; delta < 0 = stock consumed or removed.
CREATE TABLE inventory_history (
    id           SERIAL PRIMARY KEY,
    inventory_id INTEGER NOT NULL REFERENCES inventory(id),
    delta        INTEGER NOT NULL,
    reason       VARCHAR(255),
    created_at   TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Supplier master data.
CREATE TABLE suppliers (
    id         SERIAL PRIMARY KEY,
    name       VARCHAR(255) NOT NULL,
    email      VARCHAR(255),
    phone      VARCHAR(50),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMP
);

-- Junction table linking products to their suppliers.
-- is_preferred flags the primary supplier used in low-stock alerts.
CREATE TABLE product_suppliers (
    id             SERIAL PRIMARY KEY,
    product_id     INTEGER NOT NULL REFERENCES products(id),
    supplier_id    INTEGER NOT NULL REFERENCES suppliers(id),
    is_preferred   BOOLEAN NOT NULL DEFAULT FALSE,
    lead_time_days INTEGER,
    UNIQUE (product_id, supplier_id)
);
```

---

## Design Decisions

1. **Separating `inventory` from `inventory_history`**
   `inventory` holds the current stock level for each product-warehouse pair — one row, fast point-in-time reads. `inventory_history` is an append-only audit log that records every stock movement as a `delta` (positive for stock in, negative for stock out). Storing deltas rather than absolute values avoids update anomalies in concurrent environments and makes it straightforward to reconstruct any historical stock level by summing deltas up to a given timestamp.

2. **`NUMERIC(12, 2)` for monetary values**
   Floating-point types (`FLOAT`, `DOUBLE PRECISION`) cannot represent all decimal fractions exactly, which leads to rounding errors in financial calculations. `NUMERIC(12, 2)` stores exact decimal values — up to 10 digits before the decimal point and exactly 2 after — making it the correct choice for prices in an inventory system.

3. **`company_id` on `products`**
   StockFlow is multi-tenant. Placing `company_id` directly on the `products` table (rather than deriving it through a join via `warehouses`) allows a single-column index to enforce tenant isolation and makes all product queries fast without additional joins. The `UNIQUE (company_id, sku)` constraint also doubles as the primary index anchor for SKU lookups within a tenant.

4. **`product_bundle_items` junction table**
   A bundle is a product that contains other products. A separate junction table with `bundle_product_id` and `component_product_id` columns cleanly models this many-to-many self-referential relationship and allows a `quantity` attribute on the relationship itself. This avoids nullable self-referential foreign keys on the `products` table and supports multi-level bundle nesting.

5. **Soft deletes via `deleted_at`**
   Setting `deleted_at = NOW()` instead of issuing a `DELETE` statement preserves referential integrity (foreign keys remain valid), maintains the full audit history in `inventory_history`, and allows accidental deletions to be reversed. All application queries filter `WHERE deleted_at IS NULL` to exclude soft-deleted rows from results.

---

## Open Questions

1. **Multi-currency support** — Is pricing always in a single base currency (e.g., USD), or does the system need to support multiple currencies? If multi-currency is required, a `currency_code` column and possibly an exchange rates table would be needed.

2. **Units of measure** — Are all inventory quantities in discrete units (each), or do some products use continuous measures such as kilograms or litres? This affects how `quantity` in `inventory` and `delta` in `inventory_history` are interpreted and displayed.

3. **Negative inventory** — Should the system allow `quantity` in `inventory` to go below zero (e.g., to support backorders)? The current schema permits this. A `CHECK (quantity >= 0)` constraint could be added if negative stock should be prevented at the database level.

4. **Bundle stock calculation** — When a bundle is sold, how should stock be deducted — from the bundle's own inventory row, from each component's row, or both? The current schema supports either approach but does not enforce one. This needs a product decision before the order fulfilment logic is implemented.

5. **User roles and permissions** — The schema has no `users` table. Should warehouse staff, company admins, and super-admins have different access levels? If so, a `users` table and a role/permission model would be required, and `inventory_history` should capture the `user_id` of whoever made each stock change.

6. **Supplier lead times** — `product_suppliers` has a `lead_time_days` column at the product-supplier level. Should this override a supplier-level default, or should both be stored and the more specific value take precedence?
