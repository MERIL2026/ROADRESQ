# RoadResQ — Digital Roadside Assistance Platform

> **Phase 0 Foundation Setup Complete** — Reproducible, collaborative, containerized development infrastructure for two-person team development.

---

## 🚗 Project Overview

**RoadResQ** is a modern, production-grade roadside assistance platform designed for location-aware emergency vehicle assistance, provider dispatching, real-time tracking, transparent estimates, and automated payments.

---

## 🛠️ Technology Stack

| Layer | Technology | Purpose |
| :--- | :--- | :--- |
| **Backend** | Python 3.12 + FastAPI | Modular monolith API, domain logic, geospatial matching |
| **Web UIs** | Next.js 14 + React + TypeScript | Web UIs for Customers, Providers, and Admin |
| **Database** | PostgreSQL 16 + PostGIS 3.4 | Transactional datastore & spatial geospatial indexing |
| **Cache & Presence**| Redis 7 | Live location presence, rate limiting, state caching |
| **Containers** | Docker & Docker Compose | Containerized local environment |
| **CI / CD** | GitHub Actions | Automated linting, type checks, testing, and secret scanning |

---

## 📁 Repository Structure

```text
RoadResQ/
│
├── apps/
│   ├── customer-web/               # Next.js Customer Web Application
│   ├── provider-web/               # Next.js Provider Web Application
│   ├── admin-web/                  # Next.js Admin Web Application
│   └── mobile/                     # React Native / Expo Mobile App Blueprint
│
├── backend/                        # FastAPI Modular Monolith API Backend
│   ├── app/                        # Main FastAPI application source code
│   │   ├── api/                    # Routers (Health, Liveness, Readiness)
│   │   ├── core/                   # Config, DB connection, Redis setup
│   │   └── main.py                 # Application Entrypoint
│   ├── alembic/                    # Database migration environment
│   ├── tests/                      # Pytest test suite
│   └── Dockerfile                  # Backend container specification
│
├── infra/                          # Infrastructure & Docker configuration
│   └── docker/postgres/            # PostGIS initialization script
│
├── scripts/                        # Development helper scripts (.ps1 and .sh)
│
├── docs/                           # Comprehensive Engineering Documentation
│   ├── GIT_WORKFLOW.md
│   ├── LOCAL_DEVELOPMENT.md
│   ├── DOCKER_GUIDE.md
│   ├── ENVIRONMENT_GUIDE.md
│   ├── ARCHITECTURE.md
│   └── CONTRIBUTING.md
│
├── documents/                      # Preserved Original Specification Documents (25 PDFs)
│
├── .github/                        # GitHub Actions CI Workflows & Issue/PR Templates
├── .env.example                    # Environment Configuration Template
├── README.md                       # Master Project Documentation
└── docker-compose.yml              # Multi-container local orchestration
```

---

## 🚀 Quick Start — Local Development

### 1. Prerequisites
- [Git](https://git-scm.com/)
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (with Docker Compose v2)

### 2. Boot Environment
```bash
# Clone the repository
git clone https://github.com/MERIL2026/ROADRESQ.git
cd ROADRESQ

# Copy environment settings template
cp .env.example .env

# Build and start all services via Docker Compose
docker compose up --build
```

---

## 🧪 Verification & Health Check Endpoints

Once Docker Compose starts:

- **Customer Web Application**: [http://localhost:3000](http://localhost:3000)
- **FastAPI Root**: [http://localhost:8000](http://localhost:8000)
- **Interactive OpenAPI Documentation**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Liveness Health Check**: [http://localhost:8000/health](http://localhost:8000/health)
- **Readiness Health Check (DB + PostGIS + Redis)**: [http://localhost:8000/health/ready](http://localhost:8000/health/ready)

---

## 🌿 Git Branching Strategy

RoadResQ uses a structured feature-branch workflow for clean team collaboration:

```text
main   ◄── Production Branch (Protected, PR only)
  ▲
develop ◄── Integration Branch
  ▲
feature/*, fix/*, chore/* ◄── Feature Development
```

For complete details, see [`docs/GIT_WORKFLOW.md`](docs/GIT_WORKFLOW.md).

---

## 🔒 Security Baseline
- Secrets and `.env` files are strictly ignored via `.gitignore`.
- Automated GitHub Actions secret scanning blocks accidental credential pushes.
- Production and development configurations are decoupled.

---

## 📜 Documentation Index
- 📖 [Local Development Guide](docs/LOCAL_DEVELOPMENT.md)
- 🐳 [Docker Operations Guide](docs/DOCKER_GUIDE.md)
- 🌿 [Git Workflow & Branch Protection Policy](docs/GIT_WORKFLOW.md)
- 🔐 [Environment & Secrets Guide](docs/ENVIRONMENT_GUIDE.md)
- 🏗️ [Phase 0 Architecture Overview](docs/ARCHITECTURE.md)
- 🤝 [Contributing Guidelines](docs/CONTRIBUTING.md)

---

## 📄 License
Privately owned software for **RoadResQ**. All rights reserved.
