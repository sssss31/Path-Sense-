"""One-command local runner for PathSense (Windows, macOS, Linux).

    python scripts/bootstrap.py            # set up + start backend and frontend
    python scripts/bootstrap.py --setup    # set up only (no servers)
    python scripts/bootstrap.py --check    # print what would be used, change nothing

What it does, in order:
  1. verifies Python/Node, creates backend/.venv and installs requirements, runs npm install
  2. picks a database: DATABASE_URL from .env if reachable -> Docker PostGIS (docker-compose.test.yml)
     if Docker works -> otherwise SQLite demo mode (no PostGIS, simulated providers, everything else works)
  3. for PostgreSQL: alembic upgrade head + demo hazard fixtures; for SQLite: tables are created on app startup
  4. writes frontend/.env.local with the backend URL, picks free ports
  5. starts uvicorn and next dev, opens the browser
Nothing here needs admin rights. Stop with Ctrl+C.
"""
import argparse
import os
import platform
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
ENV = ROOT / ".env"
WIN = platform.system() == "Windows"
VENV_PY = BACKEND / ".venv" / ("Scripts/python.exe" if WIN else "bin/python")
SQLITE_URL = "sqlite+aiosqlite:///./pathsense.db"
DOCKER_URL = "postgresql+asyncpg://pathsense_test:pathsense_test@localhost:55432/pathsense_test"

def log(msg: str):
    print(f"[pathsense] {msg}", flush=True)

def run(cmd, cwd=None, check=True, env=None, quiet=False):
    return subprocess.run(cmd, cwd=cwd, check=check, env=env, stdout=subprocess.DEVNULL if quiet else None, stderr=subprocess.STDOUT if quiet else None)

def read_env() -> dict:
    values = {}
    if ENV.exists():
        for line in ENV.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1); values[k.strip()] = v.strip()
    return values

def write_env(values: dict):
    template = (ROOT / ".env.example").read_text(encoding="utf-8") if (ROOT / ".env.example").exists() else ""
    lines, seen = [], set()
    for line in template.splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k = line.split("=", 1)[0].strip(); seen.add(k)
            lines.append(f"{k}={values.get(k, line.split('=', 1)[1].strip())}")
        else:
            lines.append(line)
    for k, v in values.items():
        if k not in seen: lines.append(f"{k}={v}")
    ENV.write_text("\n".join(lines) + "\n", encoding="utf-8")

def free_port(preferred: int) -> int:
    for port in [preferred] + list(range(preferred + 1, preferred + 20)):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return preferred

def tcp_open(host: str, port: int, timeout=1.5) -> bool:
    with socket.socket() as s:
        s.settimeout(timeout)
        return s.connect_ex((host, port)) == 0

def parse_pg(url: str):
    try:
        rest = url.split("@", 1)[1]; hostport = rest.split("/", 1)[0]
        host, _, port = hostport.partition(":")
        return host or "localhost", int(port or 5432)
    except Exception:
        return None

def ensure_python_env():
    if sys.version_info < (3, 11):
        sys.exit("Python 3.11+ is required (3.12 recommended). Install from python.org and tick 'Add to PATH'.")
    if not VENV_PY.exists():
        log("creating backend/.venv"); run([sys.executable, "-m", "venv", str(BACKEND / ".venv")])
    marker = BACKEND / ".venv" / ".requirements.sha"
    req = BACKEND / "requirements.txt"
    digest = str(req.stat().st_mtime_ns)
    if not marker.exists() or marker.read_text() != digest:
        log("installing backend requirements (first run takes a few minutes)")
        run([str(VENV_PY), "-m", "pip", "install", "-q", "-r", str(req)])
        marker.write_text(digest)

def ensure_node_env():
    npm = shutil.which("npm.cmd" if WIN else "npm") or shutil.which("npm")
    if not npm:
        sys.exit("Node.js/npm not found. Install Node 20 LTS from nodejs.org and reopen the terminal.")
    if not (FRONTEND / "node_modules").exists():
        log("installing frontend packages (first run takes a few minutes)")
        run([npm, "install", "--no-audit", "--no-fund"], cwd=FRONTEND)
    return npm

def docker_postgis() -> str | None:
    docker = shutil.which("docker")
    if not docker:
        return None
    try:
        run([docker, "info"], check=True, quiet=True)
    except Exception:
        return None
    log("Docker found: starting PostGIS container (docker-compose.test.yml)")
    try:
        run([docker, "compose", "-f", str(ROOT / "docker-compose.test.yml"), "up", "-d"], cwd=ROOT, quiet=True)
    except Exception:
        return None
    for _ in range(40):
        if tcp_open("127.0.0.1", 55432): return DOCKER_URL
        time.sleep(1.5)
    return None

def choose_database(env: dict, check_only: bool) -> tuple[str, str]:
    """Return (database_url, kind) where kind is postgres | sqlite."""
    url = env.get("DATABASE_URL", "")
    if url.startswith("postgresql"):
        hp = parse_pg(url)
        if hp and tcp_open(*hp):
            log(f"using PostgreSQL from .env at {hp[0]}:{hp[1]}"); return url, "postgres"
        log(f"PostgreSQL in .env is not reachable ({hp}); trying Docker, then SQLite")
    if not check_only:
        docker_url = docker_postgis()
        if docker_url:
            return docker_url, "postgres"
    elif shutil.which("docker"):
        log("Docker is installed; the real run would start PostGIS with it")
    log("no PostGIS available: using SQLite demo mode (simulated providers, hazard intelligence unavailable, everything else works)")
    return SQLITE_URL, "sqlite"

def backend_env(env: dict, db_url: str, kind: str) -> dict:
    merged = dict(env)
    merged["DATABASE_URL"] = db_url
    if kind == "sqlite":
        merged["USE_MOCK_DATA"] = "true"; merged.setdefault("APP_ENV", "development")
    merged.setdefault("JWT_SECRET", "local-dev-secret-change-me")
    merged.setdefault("DEMO_USER_EMAIL", "demo@smartlogistics.local"); merged.setdefault("DEMO_USER_PASSWORD", "Demo123!")
    merged.setdefault("GEMINI_MODEL", "gemini-3.6-flash")
    return merged

def prepare_postgres(env_vars: dict):
    e = {**os.environ, **env_vars}
    log("applying migrations (alembic upgrade head)")
    run([str(VENV_PY), "-m", "alembic", "upgrade", "head"], cwd=BACKEND, env=e)
    fixtures = [("gsi_landslide_inventory", "gsi_inventory_sample.csv"), ("gsi_landslide_susceptibility", "gsi_susceptibility_sample.geojson"), ("nrsc_flood_hazard", "nrsc_flood_sample.geojson")]
    log("seeding synthetic hazard fixtures (replace with real GSI data via scripts/import_gsi.py)")
    for cfg, f in fixtures:
        run([str(VENV_PY), "-m", "app.ingestion.importer", "--config", f"tests/fixtures/{cfg}.fixture.yaml", "--file", f"tests/fixtures/{f}"], cwd=BACKEND, env={**e, "USE_MOCK_DATA": "true"}, quiet=True, check=False)

def main(argv=None):
    parser = argparse.ArgumentParser(); parser.add_argument("--setup", action="store_true"); parser.add_argument("--check", action="store_true"); parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)
    log(f"{platform.system()} {platform.release()} · Python {platform.python_version()} · repo {ROOT}")
    env = read_env()
    if args.check:
        db_url, kind = choose_database(env, True)
        log(f"database: {kind} ({db_url.split('@')[-1] if '@' in db_url else db_url})"); log(f"backend port: {free_port(8000)} · frontend port: {free_port(3000)}"); return
    ensure_python_env(); npm = ensure_node_env()
    db_url, kind = choose_database(env, False)
    env_vars = backend_env(env, db_url, kind)
    write_env(env_vars); log(f".env written (DATABASE_URL -> {kind}, USE_MOCK_DATA={env_vars.get('USE_MOCK_DATA','false')})")
    if kind == "postgres":
        prepare_postgres(env_vars)
    else:
        log("SQLite: tables and the demo user are created automatically when the backend starts")
    api_port, web_port = free_port(8000), free_port(3000)
    (FRONTEND / ".env.local").write_text(f"NEXT_PUBLIC_API_BASE_URL=http://localhost:{api_port}/api/v1\n", encoding="utf-8")
    origins = env_vars.get("ALLOWED_ORIGINS") or f'["http://localhost:{web_port}","http://127.0.0.1:{web_port}"]'
    if args.setup:
        log(f"setup complete. Start with:\n  backend : cd backend && {'.venv\\Scripts\\activate' if WIN else 'source .venv/bin/activate'} && uvicorn app.main:app --reload --port {api_port}\n  frontend: cd frontend && npm run dev -- --port {web_port}"); return
    e = {**os.environ, **env_vars, "ALLOWED_ORIGINS": origins}
    log(f"starting backend on http://localhost:{api_port} and frontend on http://localhost:{web_port}")
    backend = subprocess.Popen([str(VENV_PY), "-m", "uvicorn", "app.main:app", "--port", str(api_port)], cwd=BACKEND, env=e)
    frontend = subprocess.Popen([npm, "run", "dev", "--", "--port", str(web_port)], cwd=FRONTEND, env={**os.environ, "NEXT_PUBLIC_API_BASE_URL": f"http://localhost:{api_port}/api/v1"})
    ready = False
    for _ in range(60):
        try:
            with urllib.request.urlopen(f"http://localhost:{api_port}/api/v1/system/readiness", timeout=2) as r:
                if r.status == 200: ready = True; break
        except Exception:
            time.sleep(1)
    log("backend ready" if ready else "backend did not answer readiness yet (check its log above)")
    log(f"open http://localhost:{web_port}  ·  login {env_vars.get('DEMO_USER_EMAIL')} / {env_vars.get('DEMO_USER_PASSWORD')}  ·  API docs http://localhost:{api_port}/docs")
    if kind == "sqlite":
        log("mode: SQLite demo. For live providers + hazard intelligence install Docker Desktop or PostGIS and rerun (see docs/windows-setup.md).")
    if not args.no_browser:
        time.sleep(4); webbrowser.open(f"http://localhost:{web_port}")
    try:
        while True:
            time.sleep(1)
            if backend.poll() is not None: log("backend exited"); break
            if frontend.poll() is not None: log("frontend exited"); break
    except KeyboardInterrupt:
        pass
    finally:
        for p in (backend, frontend):
            if p.poll() is None: p.terminate()
        log("stopped")

if __name__ == "__main__":
    main()
