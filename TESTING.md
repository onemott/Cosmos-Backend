# Backend Testing Guide

## ✅ Backend Server is Running!

The FastAPI backend is now running at: **http://localhost:8000**

### Quick Links

- **Health Check**: http://localhost:8000/health
- **API Documentation (Swagger UI)**: http://localhost:8000/api/docs
- **Alternative Docs (ReDoc)**: http://localhost:8000/api/redoc
- **OpenAPI Schema**: http://localhost:8000/api/openapi.json

### Available API Endpoints

#### Authentication
- `POST /api/v1/auth/login` - User login
- `POST /api/v1/auth/refresh` - Refresh access token
- `POST /api/v1/auth/logout` - User logout

#### Tenants (Super Admin)
- `GET /api/v1/tenants` - List all tenants
- `POST /api/v1/tenants` - Create new tenant
- `GET /api/v1/tenants/{id}` - Get tenant details
- `PATCH /api/v1/tenants/{id}` - Update tenant
- `DELETE /api/v1/tenants/{id}` - Delete tenant

#### Users
- `GET /api/v1/users/me` - Get current user
- `GET /api/v1/users` - List users
- `POST /api/v1/users` - Create user
- `GET /api/v1/users/{id}` - Get user details
- `PATCH /api/v1/users/{id}` - Update user
- `DELETE /api/v1/users/{id}` - Delete user

#### Clients
- `GET /api/v1/clients` - List clients
- `POST /api/v1/clients` - Create client
- `GET /api/v1/clients/{id}` - Get client details
- `PATCH /api/v1/clients/{id}` - Update client
- `DELETE /api/v1/clients/{id}` - Delete client
- `GET /api/v1/clients/{id}/accounts` - Get client accounts
- `GET /api/v1/clients/{id}/documents` - Get client documents

#### Accounts
- `GET /api/v1/accounts` - List accounts
- `GET /api/v1/accounts/{id}` - Get account details
- `GET /api/v1/accounts/{id}/holdings` - Get account holdings
- `GET /api/v1/accounts/{id}/transactions` - Get account transactions
- `GET /api/v1/accounts/{id}/performance` - Get account performance

#### Holdings
- `GET /api/v1/holdings` - List holdings
- `GET /api/v1/holdings/summary` - Get holdings summary
- `GET /api/v1/holdings/allocation` - Get allocation breakdown

#### Transactions
- `GET /api/v1/transactions` - List transactions
- `GET /api/v1/transactions/{id}` - Get transaction details

#### Documents
- `GET /api/v1/documents` - List documents
- `POST /api/v1/documents/upload` - Upload document
- `GET /api/v1/documents/{id}` - Get document metadata
- `GET /api/v1/documents/{id}/download` - Download document
- `DELETE /api/v1/documents/{id}` - Delete document

#### Tasks & Workflows
- `GET /api/v1/tasks` - List tasks
- `POST /api/v1/tasks` - Create task
- `GET /api/v1/tasks/{id}` - Get task details
- `PATCH /api/v1/tasks/{id}` - Update task
- `POST /api/v1/tasks/{id}/complete` - Complete task

#### Modules
- `GET /api/v1/modules` - List modules
- `GET /api/v1/modules/all` - List all modules (super admin)
- `POST /api/v1/modules/{id}/enable` - Enable module
- `POST /api/v1/modules/{id}/disable` - Disable module

#### Reports
- `GET /api/v1/reports` - List reports
- `POST /api/v1/reports/generate` - Generate report
- `GET /api/v1/reports/{id}` - Get report details
- `GET /api/v1/reports/{id}/download` - Download report

## Testing with cURL

### 1. Check Health

```bash
curl http://localhost:8000/health
```

Expected response:
```json
{"status":"healthy","version":"0.1.0"}
```

### 2. Explore API Documentation

Open in your browser:
```
http://localhost:8000/api/docs
```

This provides an interactive interface to test all endpoints.

### 3. Test Endpoints (Currently Placeholder)

Most endpoints return 501 (Not Implemented) or empty arrays since we haven't implemented the business logic yet. The structure is in place!

## Current Status

✅ **Working:**
- Server startup
- Health check endpoint
- API documentation (Swagger UI & ReDoc)
- All route definitions
- Database models
- Pydantic schemas
- Security framework
- Multi-tenancy structure

⏳ **To Implement:**
- Database migrations
- Authentication logic
- Business logic in services
- Bank integrations
- Background workers
- Actual data CRUD operations

## Next Steps

### 1. Set up Database

```bash
# Run migrations
cd backend
source venv/bin/activate
alembic upgrade head
```

### 2. Create Test Data

You can use the Swagger UI to create test data once the endpoints are implemented.

### 3. Test with Admin Portal

Start the admin portal (Next.js) to test the full stack:

```bash
cd admin
npm install
npm run dev
```

Access at: http://localhost:3001

## Server Management

### Start Server

```bash
cd backend
source venv/bin/activate
uvicorn src.main:app --reload --port 8000
```

### Stop Server

```bash
# Find process
lsof -ti:8000

# Kill process
kill -9 <PID>

# Or kill all on port 8000
lsof -ti:8000 | xargs kill -9
```

### Check Logs

```bash
cd backend
tail -f server.log
```

### Restart Server

```bash
cd backend
lsof -ti:8000 | xargs kill -9
source venv/bin/activate
uvicorn src.main:app --reload --port 8000
```

## Troubleshooting

### Port Already in Use

```bash
lsof -ti:8000 | xargs kill -9
```

### Import Errors

Make sure virtual environment is activated:
```bash
source venv/bin/activate
```

### Database Connection Error

Local testing uses PostgreSQL. Verify the service is running and the connection string in `.env` is correct, then run migrations:

```bash
alembic upgrade head
```

### Check Server is Running

```bash
curl http://localhost:8000/health
```

## API Testing Tools

1. **Swagger UI (Built-in)**
   - http://localhost:8000/api/docs
   - Interactive, no setup needed

2. **cURL (Command Line)**
   ```bash
   curl http://localhost:8000/api/v1/tenants
   ```

3. **Postman**
   - Import OpenAPI schema from: http://localhost:8000/api/openapi.json

4. **HTTPie**
   ```bash
   pip install httpie
   http http://localhost:8000/api/v1/tenants
   ```

## Database Schema

Use psql to inspect the local PostgreSQL database:

```bash
psql "postgresql://postgres:postgres@localhost:5432/eam_platform"
\dt
\d+ tasks
```

