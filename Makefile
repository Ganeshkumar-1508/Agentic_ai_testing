# TestAI — Developer Makefile
# Local development (default) and Docker commands.

.PHONY: help dev dev-frontend dev-backend dev-db setup health test test-quick \
        up down build backend frontend logs db-shell db-reset clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ── Local Development ──────────────────────────────────────────────

dev: ## Start local dev: db (Docker) + backend + frontend (host)
	@$(MAKE) setup 2>/dev/null || true
	docker compose up -d db
	@echo "Waiting for database..."
	@sleep 3
	@echo "Starting backend on http://localhost:8000 ..."
	@echo "Starting frontend on http://localhost:3000 ..."
	@echo "Run in separate terminals:"
	@echo "  make dev-backend"
	@echo "  make dev-frontend"

dev-backend: ## Run backend on host (uvicorn, hot-reload)
	cd backend && uvicorn api.main:app --reload --host 127.0.0.1 --port 8000

dev-frontend: ## Run frontend on host (next dev)
	npm run dev

dev-db: ## Start only the database in Docker
	docker compose up -d db
	@echo "PostgreSQL running on localhost:5432"

# ── Setup ──────────────────────────────────────────────────────────

setup: ## First-time setup: copy .env.example files
	@if [ ! -f .env ]; then cp .env.example .env 2>/dev/null && echo "Created .env from .env.example" || echo ".env.example not found"; fi
	@if [ ! -f backend/.env ]; then cp backend/.env.example backend/.env 2>/dev/null && echo "Created backend/.env from backend/.env.example" || true; fi
	@echo "Run 'make dev' for local development or 'make up' for Docker"

# ── Health & Testing ──────────────────────────────────────────────

health: ## Check all services are healthy
	@echo "=== Backend Health ==="
	@curl -s -o /dev/null -w "HTTP %{http_code}\n" http://localhost:8000/health || echo "Backend not reachable"
	@echo "=== Frontend ==="
	@curl -s -o /dev/null -w "HTTP %{http_code}\n" http://localhost:3000/ || echo "Frontend not reachable"
	@echo "=== Database ==="
	@docker compose exec db pg_isready -U testai 2>/dev/null || echo "DB not reachable"
	@echo "=== OpenAPI Docs ==="
	@curl -s -o /dev/null -w "HTTP %{http_code}\n" http://localhost:8000/openapi.json || echo "Docs not reachable"

test: ## Run integration tests
	python -m pytest backend/tests/ -v --timeout=30

test-quick: ## Run integration tests (quick subset)
	python -m pytest backend/tests/test_integration.py::test_endpoint_returns_200 -k "health or runs or sessions or export" -v --timeout=10

# ── Docker (production / full stack) ──────────────────────────────

up: ## Start all services in Docker (db, backend, frontend)
	docker compose up -d

down: ## Stop all Docker services
	docker compose down

build: ## Build all Docker images
	docker compose build

backend: ## Restart Docker backend (hot-reloads Python changes)
	docker compose cp backend/api/routers/ testai-backend:/app/api/routers/
	docker compose cp backend/harness/ testai-backend:/app/harness/
	docker restart testai-backend

frontend: ## Build and start Docker frontend
	docker compose build frontend
	docker compose up -d frontend

logs: ## Tail Docker logs from all services
	docker compose logs -f

db-shell: ## Open a psql shell
	docker compose exec db psql -U testai -d testai

db-reset: ## Reset the database (drops all data)
	docker compose down db
	docker compose up -d db
	@sleep 3
	@echo "Database reset — tables will be recreated on next backend startup"

clean: ## Remove all stopped containers and unused images
	docker compose down -v 2>/dev/null || true
	docker system prune -f
