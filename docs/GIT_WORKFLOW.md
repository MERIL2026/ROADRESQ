# RoadResQ — Git Branching Strategy & Workflow Guide

This document defines the team collaboration workflow and Git branching strategy for developers working on the **RoadResQ** roadside assistance platform.

---

## 1. High-Level Branch Structure

```text
main (Production Ready Only)
  │
  ├── develop (Integration Branch for Completed Features)
  │
  ├── feature/* (New Features / Phase Components)
  ├── fix/*     (Bug fixes)
  ├── refactor/* (Code structure & optimization)
  └── chore/*   (DevOps, Docker, CI, Dependencies)
```

---

## 2. Branch Responsibilities & Rules

### A. `main` Branch
- **Purpose**: Represents production-ready code.
- **Strict Rule**: **NO DIRECT PUSHES ALLOWED**.
- **Integration**: All changes must arrive via approved Pull Requests from `develop`.

### B. `develop` Branch
- **Purpose**: Primary integration branch where completed features are combined and tested together.
- **Strict Rule**: Direct pushes prohibited for feature work. All feature additions must arrive via Pull Requests from `feature/*`, `fix/*`, or `chore/*` branches.

### C. Feature & Task Branches
Always create a branch off `develop` before starting work:

```bash
# Branch naming conventions:
feature/customer-auth
feature/provider-onboarding
feature/booking-system
feature/payment-integration
fix/login-validation
fix/postgres-connection-timeout
chore/docker-setup
chore/ci-pipeline-tuning
refactor/db-session-handler
```

---

## 3. Step-by-Step Developer Workflow

### Step 1: Sync `develop`
```bash
git checkout develop
git pull origin develop
```

### Step 2: Create a Feature Branch
```bash
git checkout -b feature/booking-system
```

### Step 3: Develop & Test Locally
Run tests and type checks before committing:
```bash
# Backend checks (inside container or venv)
pytest
ruff check .
mypy app

# Frontend checks
npm run type-check
npm run lint
```

### Step 4: Commit Changes
Use clear, descriptive commit messages:
```bash
git add .
git commit -m "feat(booking): implement geospatial provider radius lookup endpoint"
```

### Step 5: Push Branch & Open Pull Request
```bash
git push -u origin feature/booking-system
```
Go to GitHub (`https://github.com/MERIL2026/ROADRESQ`) and open a Pull Request targeting **`develop`**.

### Step 6: Code Review & CI Pass
1. CI checks must pass automatically (`ci-backend`, `ci-frontend`, `security-scan`).
2. Require approval from your team co-developer.
3. Merge using **Squash and Merge** or **Rebase and Merge** to maintain a clean Git history.

---

## 4. GitHub Branch Protection Policy (Manual Setup Required)

Navigate to **GitHub Repository Settings → Branches → Add Branch Protection Rule**:

### Protection Rules for `main` and `develop`:
- **Branch Pattern Name**: `main` (repeat for `develop`)
- ✅ **Require a pull request before merging** (Require 1 approval)
- ✅ **Require status checks to pass before merging** (Select `test-and-lint`, `build-and-lint`, `secret-scan`)
- ✅ **Require branches to be up to date before merging**
- ✅ **Do not allow bypassing the above settings**
- ✅ **Block force pushes**
- ✅ **Block branch deletion**
