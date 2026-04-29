<div align="center">

# 📦 StockFlow — Backend Engineering Case Study

**A production-quality backend case study for a B2B SaaS Inventory Management System**

![Python](https://img.shields.io/badge/Python-3.9%2B-blue?logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.0-black?logo=flask&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-336791?logo=postgresql&logoColor=white)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-ORM-red)
![License](https://img.shields.io/badge/License-MIT-green)

</div>

---

## Overview

StockFlow is a multi-tenant B2B SaaS platform for inventory management. This repository contains my solution to a three-part backend engineering case study, demonstrating skills in **code review**, **relational database design**, and **REST API implementation**.

Each part is documented in detail with working code, design rationale, and open questions for the product team — structured the way a real engineering submission would be.

---

## Case Study Parts

| # | Document | What It Covers |
|---|----------|----------------|
| 1 | [Code Review & Debugging →](PART1_Debugging.md) | Identified and fixed **6 production bugs** in a Flask endpoint — missing auth, no input validation, non-atomic DB commits, wrong HTTP status, and more |
| 2 | [Database Design →](PART2_Database_Design.md) | Designed a **full multi-tenant schema** (8 tables) with audit logging, soft deletes, bundle support, and supplier relationships |
| 3 | [API Implementation →](PART3_API_Implementation.md) | Built a **low-stock alerts endpoint** with N+1 prevention, stockout estimation, preferred supplier lookup, and thorough edge case handling |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.9+ |
| Web Framework | Flask 3.0 |
| ORM | Flask-SQLAlchemy |
| Database | PostgreSQL |
| DB Adapter | psycopg2-binary |
| Config | python-dotenv |

---

## Key Engineering Highlights

**Part 1 — Debugging**
- Identified 6 distinct bugs across security, correctness, and reliability
- Fixed non-atomic commits using `db.session.flush()` + `db.session.commit()` in a single transaction
- Added company-scoped SKU uniqueness check with a clean `409 Conflict` response
- Enforced authentication at the route level with `@require_auth`

**Part 2 — Database Design**
- Multi-tenant schema with `company_id` on all tenant-scoped tables
- Separate `inventory` (current state) and `inventory_history` (append-only delta log) tables for O(1) reads with full audit trail
- `NUMERIC(12, 2)` for prices — avoids floating-point rounding errors in financial data
- Soft deletes via `deleted_at` to preserve referential integrity and audit history
- Self-referential `product_bundle_items` junction table for bundle composition

**Part 3 — API Implementation**
- Single bulk query for preferred suppliers — no N+1 database round-trips
- `COALESCE` in SQL filter for inventory-level threshold override
- Division-by-zero guard on `days_until_stockout` calculation
- Urgency-sorted response: items closest to stockout appear first
- Returns `200` with empty list (not `404`) when no alerts exist — correct REST semantics

---

## Project Structure

```
stockflow-backend-case-study/
│
├── README.md                    ← You are here
├── PART1_Debugging.md           ← Bug analysis + corrected implementation
├── PART2_Database_Design.md     ← Full SQL DDL schema + design decisions
├── PART3_API_Implementation.md  ← Low-stock alerts endpoint
│
├── app/
│   ├── __init__.py
│   ├── main.py                  ← Flask app factory + SQLAlchemy init
│   ├── models.py                ← ORM models for all 8 database tables
│   ├── routes.py                ← API endpoints (create_product, low_stock_alerts)
│   └── auth.py                  ← Stub require_auth decorator
│
├── requirements.txt             ← Pinned Python dependencies
└── .gitignore
```

---

## Getting Started

**Requirements:** Python 3.9 or higher

```bash
# 1. Clone the repository
git clone https://github.com/your-username/stockflow-backend-case-study.git
cd stockflow-backend-case-study

# 2. Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate        # macOS / Linux
venv\Scripts\activate           # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. (Optional) Set your database URL
echo "DATABASE_URL=postgresql://localhost/stockflow" > .env

# 5. Run the Flask development server
export FLASK_APP=app/main.py    # macOS / Linux
set FLASK_APP=app/main.py       # Windows
flask run
```

> **Note:** The app imports and starts cleanly without a live PostgreSQL instance. A running database is only needed to execute actual queries.

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/companies/<id>/products` | Create a new product with input validation and atomic DB insert |
| `GET` | `/api/companies/<id>/alerts/low-stock` | List low-stock alerts sorted by days until stockout |

### Example Response — Low-Stock Alert

```json
{
  "total": 1,
  "alerts": [
    {
      "product_id": 42,
      "product_name": "Widget Pro",
      "sku": "WGT-001",
      "warehouse_id": 3,
      "warehouse_name": "East Warehouse",
      "current_quantity": 4,
      "low_stock_threshold": 10,
      "daily_sales_rate": 1.5,
      "days_until_stockout": 2.7,
      "preferred_supplier": {
        "id": 7,
        "name": "Acme Supplies",
        "email": "orders@acme.com"
      }
    }
  ]
}
```

---

## Design Assumptions

- SKU namespaces are isolated per company — two companies may share the same SKU string without conflict
- "Recent sales" = stock-out events (`delta < 0`) in `inventory_history` within the last 30 days
- An inventory-level `low_stock_threshold` overrides the product-level default when set
- Soft deletes are used on `companies`, `warehouses`, `products`, and `suppliers`
- `require_auth` is a stub for local development — production would validate a JWT
- Bundle stock deduction logic is flagged as an open question (see [Part 2](PART2_Database_Design.md#open-questions))

---

## Dependencies

```
Flask==3.0.3
Flask-SQLAlchemy==3.1.1
psycopg2-binary==2.9.9
python-dotenv==1.0.1
```

---

<div align="center">

Built as part of a Backend Engineering Intern application · StockFlow Case Study

</div>
