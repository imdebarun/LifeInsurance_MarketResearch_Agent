import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent))

from db.manager import create_user, init_db
from db.models import User
from db.manager import SessionLocal

print("Initializing DB...")
init_db()

print("Attempting to create test user...")
res = create_user("testuser", "test@example.com", "password123")

if res:
    print("User created successfully!")
else:
    print("User creation returned False.")
    
# Manual check
session = SessionLocal()
u = session.query(User).filter(User.username == "testuser").first()
if u:
    print(f"Verified: Found user {u.username} in DB.")
else:
    print("Verified: User NOT found in DB.")
session.close()
