# RoadResQ — Local Development Guide

Welcome to the **RoadResQ** roadside assistance platform development team!

This guide walks a developer through taking a clean computer from `git clone` to a fully running, containerized local environment.

---

## 1. Prerequisites

Before starting, ensure your local development machine has:
1. **Git** (`git --version` >= 2.40)
2. **Docker Desktop** (`docker --version` >= 24.0, with Docker Compose v2)
3. **Python** (`python --version` >= 3.12, optional for host IDE autocomplete)
4. **Node.js** (`node --version` >= 20.0, optional for host IDE autocomplete)

---

## 2. Quick Start (5-Minute Onboarding)

### Step 1: Clone Repository
```bash
git clone https://github.com/MERIL2026/ROADRESQ.git
cd ROADRESQ
```

### Step 2: Create Local Environment Configuration
Copy the template `.env.example` to `.env`:
```bash
# On Linux / macOS / Git Bash / PowerShell:
cp .env.example .env
```

> ⚠️ **IMPORTANT**: Never edit or commit secret keys to `.env.example`. Modifying `.env` stays strictly local to your machine.

### Step 3: Boot Environment via Docker Compose
```bash
docker compose up --build
```

This single command starts:
- **PostgreSQL 16 + PostGIS 3.4** on port `5432`
- **Redis 7** on port `6379`
- **FastAPI Backend Service** on port `8000`
- **Customer Next.js Web App** on port `3000`

---

## 3. Verifying Local Application Services

Once `docker compose up` completes and reports healthy containers:

| Service | Local URL / Endpoint | Expected Response |
| :--- | :--- | :--- |
| **FastAPI Root** | `http://localhost:8000/` | Welcome JSON |
| **Swagger API Docs** | `http://localhost:8000/docs` | Interactive OpenAPI UI |
| **Liveness Probe** | `http://localhost:8000/health` | `{"status": "ok", ...}` |
| **Readiness Probe** | `http://localhost:8000/health/ready` | `{"status": "ready", "database": {...}, "redis": {...}}` |
| **Customer Web** | `http://localhost:3000` | RoadResQ Landing UI |
| **PostgreSQL** | `localhost:5432` | DB: `roadresq_db`, User: `roadresq_user` |
| **Redis Store** | `localhost:6379` | PING -> PONG |

---

## 4. Helper Automation Scripts

We provide convenient scripts under `scripts/`:

### PowerShell (Windows):
```powershell
# Setup environment:
.\scripts\dev-setup.ps1

# Check system health:
.\scripts\test-health.ps1

# Destructive database reset (wipes local development DB volume):
.\scripts\reset-db.ps1
```

### Bash (Linux / macOS):
```bash
chmod +x scripts/*.sh
./scripts/dev-setup.sh
./scripts/test-health.sh
./scripts/reset-db.sh
```
