# TestAI — Developer Makefile
# Common commands for local development.

.PHONY: help up down build backend frontend logs health test clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

up: ## Start all services (db, backend, frontend)
	docker compose up -d

down: ## Stop all services
	docker compose down

build: ## Build all Docker images
	docker compose build

backend: ## Restart just the backend (hot-reloads Python changes)
	docker compose cp backend/api/routers/ testai-backend:/app/api/routers/
	docker compose cp backend/harness/ testai-backend:/app/harness/
	docker restart testai-backend

frontend: ## Build just the frontend
	docker compose build frontend
	docker compose up -d frontend

logs: ## Tail logs from all services
	docker compose logs -f

health: ## Check all services are healthy
	@echo "=== Backend Health ==="
	@curl -s -o /dev/null -w "HTTP %{http_code}\n" http://localhost:8001/health || echo "Backend not reachable"
	@echo "=== Frontend ==="
	@curl -s -o /dev/null -w "HTTP %{http_code}\n" http://localhost:3001/chat || echo "Frontend not reachable"
	@echo "=== Database ==="
	@docker compose exec db pg_isready -U postgres 2>/dev/null || echo "DB not reachable"
	@echo "=== OpenAPI Docs ==="
	@curl -s -o /dev/null -w "HTTP %{http_code}\n" http://localhost:8001/openapi.json || echo "Docs not reachable"

test: ## Run integration tests
	python -m pytest backend/tests/ -v --timeout=30

test-quick: ## Run integration tests (quick subset)
	python -m pytest backend/tests/test_integration.py::test_endpoint_returns_200 -k "health or runs or sessions or export" -v --timeout=10

db-shell: ## Open a psql shell
	docker compose exec db psql -U postgres -d testai

db-reset: ## Reset the database (drops all data)
	docker compose down db
	docker compose up -d db
	@sleep 3
	@echo "Database reset — tables will be recreated on next backend startup"

clean: ## Remove all stopped containers and unused images
	docker compose down -v 2>/dev/null || true
	docker system prune -f

setup: ## First-time setup: copy .env.example files
	@if [ ! -f .env ]; then cp .env.example .env 2>/dev/null && echo "Created .env from .env.example" || echo ".env.example not found"; fi
	@if [ ! -f backend/.env ]; then cp backend/.env.example backend/.env 2>/dev/null && echo "Created backend/.env from backend/.env.example" || true; fi
	@echo "Run 'make up' to start all services"
