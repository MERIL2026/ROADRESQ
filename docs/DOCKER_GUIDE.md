# RoadResQ — Docker Operations & Troubleshooting Guide

RoadResQ relies on **Docker Compose** to ensure deterministic environments for all developers.

---

## 1. Primary Operational Commands

### Start All Services
```bash
docker compose up
```

### Start in Detached Mode (Background)
```bash
docker compose up -d
```

### Rebuild Containers After Adding Dependencies
```bash
docker compose up --build
```

### Stop All Services (Preserving Database Data)
```bash
docker compose down
```

### Stop All Services & WIPE Local Database Volumes (Destructive Reset)
```bash
docker compose down -v
```

---

## 2. Inspecting Logs

### View Logs for All Services
```bash
docker compose logs -f
```

### View Logs for Backend Only
```bash
docker compose logs -f backend
```

### View Logs for PostgreSQL Only
```bash
docker compose logs -f postgres
```

---

## 3. Interactive Shell & CLI Access

### PostgreSQL Shell (`psql`) Access
```bash
docker compose exec postgres psql -U roadresq_user -d roadresq_db
```
Inside `psql`, verify PostGIS extension:
```sql
SELECT PostGIS_Full_Version();
```

### Redis CLI Access
```bash
docker compose exec redis redis-cli
```
Inside `redis-cli`:
```text
PING
KEYS *
```

### Backend Container Bash Shell
```bash
docker compose exec backend bash
```

---

## 4. Container Architecture & Ports

```text
Host System (Your Machine)
 ├── Port 3000  ──►  Customer Web Container (Next.js)
 ├── Port 8000  ──►  Backend Container (FastAPI + Uvicorn)
 ├── Port 5432  ──►  PostgreSQL + PostGIS Container
 └── Port 6379  ──►  Redis Container
```
