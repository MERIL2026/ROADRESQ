-- Initialize PostGIS extension on database initialization
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Verify PostGIS version in container log on startup
SELECT PostGIS_Full_Version();
