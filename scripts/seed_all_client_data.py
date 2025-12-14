#!/usr/bin/env python3
"""
Master seed script for client-facing application test data.

This script runs all client-related seed scripts in the correct order:
1. Portfolio data (clients, accounts, holdings, transactions)
2. Documents
3. Tasks

Usage:
    cd backend
    source venv/bin/activate
    python scripts/seed_all_client_data.py
    
    # With reset (clears existing test data first):
    python scripts/seed_all_client_data.py --reset
"""

import subprocess
import sys
import argparse


def run_script(script_name: str, reset: bool = False) -> bool:
    """Run a seed script and return success status."""
    cmd = [sys.executable, f"scripts/{script_name}"]
    if reset:
        cmd.append("--reset")
    
    result = subprocess.run(cmd, cwd=".")
    return result.returncode == 0


def main():
    parser = argparse.ArgumentParser(description="Seed all client test data")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Reset existing test data before seeding (only applies to portfolio script)",
    )
    args = parser.parse_args()
    
    print("=" * 70)
    print("           CLIENT APP - MASTER SEED SCRIPT")
    print("=" * 70)
    print()
    
    # Step 1: Portfolio data
    print("STEP 1/3: Seeding Portfolio Data")
    print("-" * 70)
    if not run_script("seed_client_portfolio.py", reset=args.reset):
        print("ERROR: Portfolio seeding failed!")
        sys.exit(1)
    print()
    
    # Step 2: Documents
    print("STEP 2/3: Seeding Documents")
    print("-" * 70)
    if not run_script("seed_client_documents.py"):
        print("ERROR: Document seeding failed!")
        sys.exit(1)
    print()
    
    # Step 3: Tasks
    print("STEP 3/3: Seeding Tasks")
    print("-" * 70)
    if not run_script("seed_client_tasks.py"):
        print("ERROR: Task seeding failed!")
        sys.exit(1)
    
    print()
    print("=" * 70)
    print("                   ALL SEEDS COMPLETE!")
    print("=" * 70)
    print()
    print("Test Credentials:")
    print("-" * 70)
    print("  Client 1:")
    print("    Email:    client1@test.com")
    print("    Password: Test1234!")
    print()
    print("  Client 2:")
    print("    Email:    client2@test.com")
    print("    Password: Test1234!")
    print()
    print("Quick Test Commands:")
    print("-" * 70)
    print("  # 1. Start the server (in a separate terminal)")
    print("  uvicorn src.main:app --reload")
    print()
    print("  # 2. Login and get token")
    print('  curl -X POST http://localhost:8000/api/v1/client/auth/login \\')
    print('    -H "Content-Type: application/json" \\')
    print('    -d \'{"email":"client1@test.com","password":"Test1234!"}\'')
    print()
    print("  # 3. Use the token to call APIs")
    print('  curl http://localhost:8000/api/v1/client/portfolio/summary \\')
    print('    -H "Authorization: Bearer <YOUR_TOKEN>"')
    print()
    print("Swagger UI: http://localhost:8000/api/docs")
    print("=" * 70)


if __name__ == "__main__":
    main()

