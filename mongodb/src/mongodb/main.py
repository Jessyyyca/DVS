from pymongo import MongoClient
from . import get_dsn
from pprint import pprint



client = MongoClient(get_dsn())

db = client["sample_supplies"]
sales = db["sales"]

print("Connected to MongoDB!")
print("Documents:", sales.count_documents({}))

### CREATE
new_sale = {
    "_id": "tutorial_demo_sale",
    "storeLocation": "Berlin",
    "purchaseMethod": "Online",
    "items": [
        {
            "name": "notebook",
            "quantity": 2,
            "price": 12.99
        }
    ],
    "customer": {
        "age": 25,
        "satisfaction": 5
    },
    "couponUsed": False
}

pprint(f"inserting {new_sale}")
sales.insert_one(new_sale)
print("Sale inserted!")

### READ
### read specific id
sale = sales.find_one({"_id": "tutorial_demo_sale"})

print(sale)

### read all online sales
for sale in sales.find(
    {"purchaseMethod": "Online"}
).limit(2):
    print(sale)

### UPDATE
sales.update_one(
    {"_id": "tutorial_demo_sale"},
    {"$set": {"customer.satisfaction": 4}}
)

print(sales.find_one({"_id": "tutorial_demo_sale"}))

### DELETE
sales.delete_one({"_id": "tutorial_demo_sale"})

print("Sale deleted!")
