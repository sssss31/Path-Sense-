# PathSense on Windows — complete local setup

Yeh document Windows 10/11 par PathSense (backend + frontend + PostGIS) chalane ke liye hai.
Sab commands **cmd.exe** ke liye hain (PowerShell nahi). Har command alag line par, ek-ek karke chalayen.

Repo path is guide me `E:\sih project\Rishab` maana gaya hai; apna path lagayen.

---

## ⚡ Sabse aasan: one-click run (kisi bhi system par)

Sirf **Python 3.12** aur **Node.js** install hone chahiye. Repo folder me `run.bat` double-click karein (ya cmd me `run.bat`). Mac/Linux par `./run.sh`.

Script khud:
1. `backend\.venv` banata hai, `pip install`, `npm install` karta hai (pehli baar 3–5 min)
2. Database chunta hai: `.env` ka PostgreSQL reachable hai → wahi; nahi to Docker chalu hai → Docker se PostGIS; nahi to **SQLite demo mode** (PostGIS ke bina — login, route analysis, deliveries, reports, dashboard sab chalta hai; hazard layers "unavailable" dikhte hain, providers simulated)
3. PostgreSQL par migrations + sample data; SQLite par tables aur demo user khud ban jate hain
4. `frontend\.env.local` likhta hai, free ports chunta hai, backend + frontend start karke browser khol deta hai

Login: `demo@smartlogistics.local` / `Demo123!`. Band karne ke liye Ctrl+C.

Sirf check karna ho (kuch badle bina): `python scripts\bootstrap.py --check`. Setup ke baad servers khud chalane ho: `python scripts\bootstrap.py --setup`.

Live providers + asli hazard intelligence chahiye to neeche ke steps se PostGIS lagayen; `run.bat` use apne aap pakad lega.

---

## 0. Kya chahiye

| Cheez | Kahan se | Note |
|---|---|---|
| Python 3.12 | https://www.python.org/downloads/windows/ | Install me **"Add python.exe to PATH"** tick karein |
| Node.js 20 LTS (ya 24) | https://nodejs.org | `node -v` se check |
| PostgreSQL 16/17/18 + PostGIS | https://www.enterprisedb.com/downloads/postgres-postgresql-downloads | Install ke end me **Stack Builder** se PostGIS bundle install karein |
| (Optional) Docker Desktop | https://www.docker.com/products/docker-desktop/ | Hai to PostGIS ka step 2 ek command me ho jata hai |

PostGIS sirf **live hazard intelligence** (risk map layers, spatial summary, asli GSI/NRSC data) ke liye chahiye. Bina PostGIS ke `run.bat` SQLite demo mode chala deta hai jisme baaki sab kaam karta hai.

---

## 1. Repo folder check

```bat
cd /d "E:\sih project\Rishab"
dir
```

`backend`, `frontend`, `docs`, `.env.example` dikhne chahiye.

---

## 2. Database (PostGIS)

### Option A — Docker Desktop hai

```bat
cd /d "E:\sih project\Rishab"
docker compose -f docker-compose.test.yml up -d
```

Yeh `localhost:55432` par PostGIS deta hai (user/password/db sab `pathsense_test`). Step 3 me `.env` ka port `55432` rakhein. Option B skip karein.

### Option B — PostgreSQL installer (Docker nahi)

**B1. Server chal raha hai?** (18 ki jagah apna version number lagayen)

```bat
sc query postgresql-x64-18
```

- `STATE : RUNNING` → theek hai, B2 par jayen.
- `STATE : STOPPED` → Admin cmd me: `net start postgresql-x64-18`
- `service does not exist` → data folder khud banayen aur server start karein:

```bat
"C:\Program Files\PostgreSQL\18\bin\initdb.exe" -D "E:\sih project\pgdata" -U postgres --auth=trust -E UTF8
"C:\Program Files\PostgreSQL\18\bin\pg_ctl.exe" -D "E:\sih project\pgdata" -l "E:\sih project\pgdata.log" start
```

Is case me har reboot ke baad sirf dusri (`pg_ctl ... start`) command dobara chalani hai.

Confirm:

```bat
"C:\Program Files\PostgreSQL\18\bin\pg_isready.exe"
```

`accepting connections` aana chahiye.

**B2. User, database, PostGIS** (SQL hamesha `psql -c "..."` ke through; seedha cmd me SQL nahi chalta)

```bat
"C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -c "CREATE USER pathsense_test WITH PASSWORD 'pathsense_test';"
"C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -c "CREATE DATABASE pathsense_test OWNER pathsense_test;"
"C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -d pathsense_test -c "CREATE EXTENSION postgis;"
```

Installer wale server par `postgres` user ka password poochhega (install ke waqt jo set kiya tha).

Agar aakhri command `could not open extension control file ... postgis.control` de → PostGIS install nahi hua:
1. `"C:\Program Files\PostgreSQL\18\bin\stackbuilder.exe"` chalayen → apna PostgreSQL server chunein → **Spatial Extensions** → **PostGIS bundle** → install.
2. Ya https://download.osgeo.org/postgis/windows/ se apne PG version ka zip download karke `C:\Program Files\PostgreSQL\18` me extract karein.
3. Phir `CREATE EXTENSION postgis;` wali command dobara.

Check:

```bat
"C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -d pathsense_test -c "SELECT postgis_full_version();"
```

---

## 3. `.env` file (repo root me)

`E:\sih project\Rishab\.env` Notepad me kholein (nahi hai to `.env.example` copy karke banayen). Yeh values rakhein:

```
APP_ENV=development
USE_MOCK_DATA=false
DATABASE_URL=postgresql+asyncpg://pathsense_test:pathsense_test@localhost:5432/pathsense_test
JWT_SECRET=koi-lamba-random-secret
DEMO_USER_EMAIL=demo@smartlogistics.local
DEMO_USER_PASSWORD=Demo123!
GEMINI_API_KEY=apni-key-ya-khali
GEMINI_MODEL=gemini-3.6-flash
OPENWEATHER_API_KEY=apni-key-ya-khali
OSRM_BASE_URL=https://router.project-osrm.org
NOMINATIM_BASE_URL=https://nominatim.openstreetmap.org
REDIS_URL=
NEXT_PUBLIC_GOOGLE_MAPS_API_KEY=
```

- Docker (Option A) use kiya hai to `DATABASE_URL` me port `55432` likhein.
- `USE_MOCK_DATA=true` karne par internet ke bina demo mode chalta hai (routing/weather simulated).
- Keys optional hain: OpenWeather na ho to weather unavailable dikhega; Gemini na ho to deterministic explanation.

---

## 4. Backend

**Hamesha `backend` folder ke andar, venv active karke.** (Bahar se chalane par `No module named 'app'` aata hai.)

Pehli baar:

```bat
cd /d "E:\sih project\Rishab\backend"
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Baad me har baar sirf:

```bat
cd /d "E:\sih project\Rishab\backend"
.venv\Scripts\activate
```

Migrations (tables banana):

```bat
alembic upgrade head
```

Demo user banana:

```bat
python -c "import asyncio;from sqlalchemy import select;from app.core.config import get_settings;from app.database.session import SessionLocal;from app.models import User;from app.core.security import hash_password;s=get_settings();exec('async def m():\n    async with SessionLocal() as db:\n        if not await db.scalar(select(User).where(User.email==s.demo_user_email)): db.add(User(email=s.demo_user_email,password_hash=hash_password(\'Demo123!\'),role=\'operator\')); await db.commit(); print(\'demo user created\')');asyncio.run(m())"
```

Sample hazard data (synthetic test fixtures; asli GSI data ke liye `docs/authoritative-data.md`):

```bat
python -m app.ingestion.importer --config tests/fixtures/gsi_landslide_inventory.fixture.yaml --file tests/fixtures/gsi_inventory_sample.csv
python -m app.ingestion.importer --config tests/fixtures/gsi_landslide_susceptibility.fixture.yaml --file tests/fixtures/gsi_susceptibility_sample.geojson
python -m app.ingestion.importer --config tests/fixtures/nrsc_flood_hazard.fixture.yaml --file tests/fixtures/nrsc_flood_sample.geojson
```

Backend start (window khula rakhein):

```bat
uvicorn app.main:app --reload --port 8010
```

Check: browser me http://localhost:8010/api/v1/system/readiness → `"ready": true`, `"database_reachable": true`.

---

## 5. Frontend (naya cmd window)

`E:\sih project\Rishab\frontend` me `.env.local` naam ki file banayen, content:

```
NEXT_PUBLIC_API_BASE_URL=http://localhost:8010/api/v1
```

Phir:

```bat
cd /d "E:\sih project\Rishab\frontend"
npm install
npm run dev
```

Browser: **http://localhost:3000** (`localhost` hi likhein, `127.0.0.1` nahi — CORS sirf localhost allow karta hai).
Login: `demo@smartlogistics.local` / `Demo123!`

---

## 6. Roz chalane ka short crama

1. Database up hai? Docker: Docker Desktop start. Installer: service running, ya `pg_ctl ... start`.
2. cmd 1: `cd /d "E:\sih project\Rishab\backend"` → `.venv\Scripts\activate` → `uvicorn app.main:app --reload --port 8010`
3. cmd 2: `cd /d "E:\sih project\Rishab\frontend"` → `npm run dev`
4. http://localhost:3000

---

## 7. Diagnostics

```bat
cd /d "E:\sih project\Rishab\backend"
.venv\Scripts\activate
python scripts\validate_demo_corridor.py
python scripts\live_smoke.py
python scripts\gemini_smoke.py
```

---

## 8. Common errors

| Error | Matlab | Fix |
|---|---|---|
| `'python' is not recognized` | Python PATH me nahi | Python installer dobara → "Add to PATH"; ya `py -3.12` use karein |
| `'alembic'/'uvicorn' is not recognized` | venv active nahi / galat folder | `cd backend` → `.venv\Scripts\activate` |
| `No module named 'app'` | `backend` folder ke bahar chal rahe ho | `cd /d "...\backend"` phir command |
| `Connect call failed ... 5432/55432` / `WinError 1225` | PostgreSQL server chal nahi raha ya galat port | Step 2 (B1) + `.env` ka port check |
| `could not open extension control file` | PostGIS install nahi | Step 2 (B2) Stack Builder |
| Login par **Failed to fetch** | Frontend backend tak nahi pahunch raha | Backend chal raha hai? `.env.local` me sahi port? URL `localhost` hai? |
| Login par **500** | Backend DB tak nahi pahunch raha | Backend terminal me error dekhein; step 2/3 |
| Login par **401** | User nahi hai / password galat | Step 4 ka demo-user command |
| `'CREATE' is not recognized` | SQL ko cmd me likha | `psql -c "..."` ke andar chalayen |
| `'docker' is not recognized` | Docker nahi hai | Option B use karein |
| `Location not found: '...'` (analysis) | Naam OpenStreetMap me nahi mila | Town/district ka naam, jaise `Tezpur, Assam` |
| `npm error enoent ... package.json` | Galat folder | `cd frontend` phir `npm run dev` |

---

## 9. Optional

- **Google base map**: `.env` me `NEXT_PUBLIC_GOOGLE_MAPS_API_KEY=<key>` daal kar frontend restart; bina key ke OpenStreetMap chalta hai.
- **Tests**: `pytest --ignore=tests/integration` (backend folder). Integration tests `TEST_DATABASE_URL` waali database ko **truncate** karte hain — demo database par mat chalayen.
- **Asli GSI data**: Bhukosh se download karke `backend\data\gsi\` me rakhein, phir `python scripts\import_gsi.py --check` aur `python scripts\import_gsi.py`.
