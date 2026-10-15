from pymongo import MongoClient
from dotenv import load_dotenv
import os

# Loads .env from the current working directory by default
load_dotenv()

# Read variables
dsn = os.getenv("DSN")


client = MongoClient(dsn)

db = client["sample_supplies"]
sales=db["sales"]