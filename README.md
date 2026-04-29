# StockFlow Backend Case Study

A three-part backend engineering case study for StockFlow — a B2B SaaS inventory management system. This repository demonstrates production-quality backend skills across code review, relational database design, and REST API implementation, using Python, Flask, SQLAlchemy, and PostgreSQL.

---

## Tech Stack

- **Python 3.9+**
- **Flask** — web framework
- **Flask-SQLAlchemy** — ORM and database session management
- **PostgreSQL** — relational database
- **psycopg2-binary** — PostgreSQL adapter for Python
- **python-dotenv** — environment variable management

---

## What This Demonstrates

| Part | Topic | Skills |
|------|-------|--------|
| [Part 1](PART1_Debugging.md) | Code Review & Debugging | Bug identification, defensive programming, atomic transactions, REST semantics |
| [Part 2](PART2_Database_Design.md) | Database Design | Multi-tenant SaaS schema, normalisation, audit logging, soft deletes |
| [Part 3](PART3_API_Implementation.md) | API Implementation | Production-quality REST endpoint, N+1 prevention, edge case handling |

---

## Assumptions

- SKU namespaces are isolated per company — two companies may use the same SKU string without conflict.
- "Recent sales" means stock-out events in `inventory_history` within the last 30 calendar days.
- An inventory-level `low_stock_threshold` overrides the product-level default when set.
- Soft deletes are used on `companies`, `warehouses`, `products`, and `suppliers`. All queries filter `deleted_at IS NULL`.
- The `require_auth` decorator is a stub for local development. In production it would validate a JWT or session token.
- Bundle stock deduction logic (from bundle vs. components) is flagged as an open question — see [Part 2](PART2_Database_Design.md#open-questions).

---

## How to Run

Requires **Python 3.9 or higher**.

```bash
# 1. Clone the repository
git clone https://github.com/your-username/stockflow-backend-case-study.git
cd stockflow-backend-case-study

# 2. Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate        # macOS / Linux
# venv\Scripts\activate         # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. (Optional) Create a .env file with your database URL
echo "DATABASE_URL=postgresql://localhost/stockflow" > .env

# 5. Run the Flask development server
export FLASK_APP=app/main.py
flask run
```

> The application will import and start cleanly without a live PostgreSQL instance. A running database is only required to execute actual queries.

---

## Repository Structure

```
stockflow-backend-case-study/
│
├── README.md                    ← You are here
├── PART1_Debugging.md           ← Code review: 6 bugs identified and fixed
├── PART2_Database_Design.md     ← Full SQL DDL schema + design rationale
├── PART3_API_Implementation.md  ← Low-stock alerts endpoint
│
├── app/
│   ├── __init__.py
│   ├── main.py                  ← Flask app factory, SQLAlchemy init
│   ├── models.py                ← SQLAlchemy ORM models (8 tables)
│   ├── routes.py                ← API endpoints (create_product, low_stock_alerts)
│   └── auth.py                  ← Stub require_auth decorator
│
├── requirements.txt             ← Pinned Python dependencies
└── .gitignore                   ← Standard Python gitignore
```

---

## Case Study Parts

- **[Part 1 — Code Review & Debugging](PART1_Debugging.md)**: Reviews a `create_product` Flask endpoint, identifies six production bugs (missing auth, no input validation, non-atomic commits, wrong HTTP status, and more), and presents a corrected implementation with design rationale.

- **[Part 2 — Database Design](PART2_Database_Design.md)**: Designs a full multi-tenant relational schema for StockFlow covering companies, warehouses, products, bundles, inventory, audit history, and suppliers. Includes DDL, design decisions, and open questions for the product team.

- **[Part 3 — API Implementation](PART3_API_Implementation.md)**: Implements a `GET /api/companies/<company_id>/alerts/low-stock` endpoint that returns low-stock alerts sorted by urgency, with days-until-stockout estimates, preferred supplier data, and thorough edge case handling.
