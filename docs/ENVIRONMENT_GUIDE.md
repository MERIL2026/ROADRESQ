# RoadResQ — Environment Variables & Secrets Management Guide

Security and secret isolation are mandatory principles for the **RoadResQ** platform.

---

## 1. Core Principles

1. **NEVER COMMIT REAL `.env` FILES TO GIT**.
2. **`.env` IS IN `.gitignore` BY DEFAULT**.
3. Always update `.env.example` when introducing new environment variables (using dummy/placeholder values only).

---

## 2. Environment Variables Specification

| Variable | Description | Example / Default |
| :--- | :--- | :--- |
| `APP_ENV` | Application environment (`development`, `staging`, `production`) | `development` |
| `APP_NAME` | Display name of service | `RoadResQ` |
| `DEBUG` | FastAPI debug mode | `true` |
| `BACKEND_PORT` | Host exposed port for backend API | `8000` |
| `POSTGRES_USER` | PostgreSQL database user | `roadresq_user` |
| `POSTGRES_PASSWORD` | PostgreSQL database password | `roadresq_password` |
| `POSTGRES_DB` | PostgreSQL database name | `roadresq_db` |
| `DATABASE_URL` | Async SQLAlchemy connection URI | `postgresql+asyncpg://...` |
| `REDIS_URL` | Redis cache connection URI | `redis://redis:6379/0` |
| `JWT_SECRET` | Secret key for signing auth tokens | `dev_jwt_secret_key...` |
| `MAPS_API_KEY` | Google Maps / Mapbox API key | `your_maps_api_key` |
| `PAYMENT_GATEWAY_KEY` | Payment Gateway key | `your_payment_key` |

---

## 3. Incident Response: What to do if a Secret is Accidental Committed

1. **DO NOT SIMPLY DELETE THE FILE IN A NEW COMMIT**. The secret remains permanently in Git history!
2. **IMMEDIATELY ROTATE / REVOKE THE COMPROMISED KEY** at the service provider (AWS, Google Cloud, Razorpay, etc.).
3. Notify the team immediately.
