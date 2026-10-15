from pymongo import MongoClient
from dotenv import load_dotenv
import os




def get_dsn() -> str:
    # Loads .env from the current working directory by default
    load_dotenv()
    return os.getenv("DSN")
