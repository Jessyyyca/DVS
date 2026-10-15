
from decimal import Decimal
from bson.decimal128 import Decimal128
from pymongo import MongoClient
import duckdb

# -----------------------------------
# 1. EXTRACT: MongoDB
# -----------------------------------

mongo = MongoClient("mongodb://localhost:27017/")
sales_collection = mongo["sample_supplies"]["sales"]

sales_rows = []
item_rows = []

def to_decimal(value):
    if isinstance(value, Decimal128):
        return value.to_decimal()
    return Decimal(str(value))

for sale in sales_collection.find():
    sale_id = str(sale["_id"])
    customer = sale.get("customer") or {}

    sales_rows.append((
        sale_id,
        sale.get("saleDate"),
        sale.get("storeLocation"),
        sale.get("purchaseMethod"),
        customer.get("age"),
        customer.get("satisfaction"),
        sale.get("couponUsed")
    ))

    # 2. TRANSFORM: Produkte auflösen
    for item_no, item in enumerate(sale.get("items", []), 1):
        quantity = int(item["quantity"])
        price = to_decimal(item["price"])

        item_rows.append((
            sale_id,
            item_no,
            item["name"],
            quantity,
            price,
            price * quantity
        ))

mongo.close()

# -----------------------------------
# 3. LOAD: DuckDB
# -----------------------------------

con = duckdb.connect("warehouse.duckdb")

con.execute("BEGIN TRANSACTION")

try:
    con.execute("""
        CREATE OR REPLACE TABLE fact_sales (
            sale_id VARCHAR PRIMARY KEY,
            sale_date TIMESTAMP,
            store_location VARCHAR,
            purchase_method VARCHAR,
            customer_age INTEGER,
            customer_satisfaction INTEGER,
            coupon_used BOOLEAN
        )
    """)

    con.execute("""
        CREATE OR REPLACE TABLE fact_sales_items (
            sale_id VARCHAR,
            item_no INTEGER,
            product_name VARCHAR,
            quantity INTEGER,
            unit_price DECIMAL(18,2),
            total_price DECIMAL(18,2),
            PRIMARY KEY (sale_id, item_no),
            FOREIGN KEY (sale_id)
                REFERENCES fact_sales(sale_id)
        )
    """)

    if sales_rows:
        con.executemany("""
            INSERT INTO fact_sales
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, sales_rows)

    if item_rows:
        con.executemany("""
            INSERT INTO fact_sales_items
            VALUES (?, ?, ?, ?, ?, ?)
        """, item_rows)

    con.execute("COMMIT")

except Exception:
    con.execute("ROLLBACK")
    raise

print(f"Imported sales: {len(sales_rows)}")
print(f"Imported items: {len(item_rows)}")

con.close()
