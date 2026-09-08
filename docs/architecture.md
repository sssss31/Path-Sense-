# Architecture

PathSense is a modular monorepo. Next.js owns presentation and client state; FastAPI owns logistics decisions. `RouteAnalysisService` orchestrates independent providers concurrently, then passes normalized data through risk, accessibility, vehicle and decision engines. Gemini is an optional explanation layer and never the source of truth.

Provider interfaces isolate geocoding, routing, weather and terrain. Development mode uses clearly labelled deterministic providers. Production adapters can replace them without changing engines or API schemas. PostgreSQL/PostGIS stores route geometry, incidents and risk zones; Redis is an optional cache, never a startup dependency.

