from django.conf import settings
from pymongo import MongoClient

client = MongoClient(settings.MONGO_URI)
db = client[settings.MONGO_DB_NAME]

# ---------- Collections ----------
# expenses_collection : one document per logged expense, references user_id
# profiles_collection : profile photo + monthly budget, keyed by user_id
# users_collection    : mirror of Django's SQLite User table, for visibility
#                        in Compass. SQLite remains the source of truth for
#                        authentication — this collection is read-only from
#                        the app's perspective except during register/edit.
expenses_collection = db["expenses"]
profiles_collection = db["profiles"]
users_collection = db["users"]
monthly_summaries_collection = db["monthly_summaries"]
split_requests_collection = db["split_requests"]