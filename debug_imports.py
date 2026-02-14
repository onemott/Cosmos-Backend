import sys
import os
sys.path.append(os.getcwd())

print("Importing sqlalchemy...")
import sqlalchemy
print("Importing asyncpg...")
import asyncpg
print("Importing src.core.config...")
import src.core.config
print("Importing src.db.session...")
import src.db.session
print("Done.")
