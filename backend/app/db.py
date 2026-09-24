"""MongoDB connection shared by the whole app."""

import certifi
from motor.motor_asyncio import AsyncIOMotorClient

from app.config import DB_NAME, MONGO_URL

# ---------- Mongo ----------
# Explicitly point at certifi's CA bundle — on some fresh Python installs
# (especially newer/pre-release versions on Windows), the system's default
# certificate store isn't picked up automatically, causing
# "CERTIFICATE_VERIFY_FAILED: unable to get local issuer certificate".

client = AsyncIOMotorClient(MONGO_URL, tlsCAFile=certifi.where())
db = client[DB_NAME]
