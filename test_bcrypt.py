
from passlib.context import CryptContext
import sys

print(f"Python version: {sys.version}")
try:
    import bcrypt
    print(f"bcrypt version: {bcrypt.__version__}")
except Exception as e:
    print(f"bcrypt error: {e}")

try:
    import passlib
    print(f"passlib version: {passlib.__version__}")
except Exception as e:
    print(f"passlib error: {e}")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

try:
    hash = pwd_context.hash("admin123")
    print(f"Hash generated: {hash}")
    
    verify = pwd_context.verify("admin123", hash)
    print(f"Verification result: {verify}")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
