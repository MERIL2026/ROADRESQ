# RoadResQ — Phase 0 Architecture Overview

This document outlines the Phase 0 containerized development architecture for the **RoadResQ** roadside assistance platform.

---

## System Architecture Diagram

```text
                               Docker Compose Environment
                                            │
        ┌───────────────────┬───────────────┴───────────────┬───────────────────┐
        │                   │                               │                   │
        ▼                   ▼                               ▼                   ▼
 Customer Web          Provider Web                    Admin Web             Mobile App
(Next.js: 3000)      (Next.js: 3001)                 (Next.js: 3002)     (React Native)
        │                   │                               │                   │
        └───────────────────┴───────────────┬───────────────┴───────────────────┘
                                            │ HTTP / JSON API
                                            ▼
                                  FastAPI Backend Core
                                    (Python: 8000)
                                            │
                    ┌───────────────────────┴───────────────────────┐
                    ▼                                               ▼
          PostgreSQL 16 + PostGIS 3.4                         Redis 7 Store
             (DB Port: 5432)                                (Cache Port: 6379)
```

---

## Subsystem Roles

1. **FastAPI Backend Core**: Serves as a **modular monolith** hosting domain logic (auth, bookings, matching, tracking).
2. **PostgreSQL + PostGIS**: Primary transactional datastore enabling spatial indexing (`GEOMETRY(Point, 4362)`) for location-aware provider dispatch.
3. **Redis**: In-memory data store for live provider presence, WebSocket session state, and caching.
4. **Next.js Web Applications**: Modular web UIs for Customers, Providers, and Administrators.
