# BatchZero — common tasks
#
# The raw commands are documented in README.md.

.PHONY: help falkordb install seed replay benchmark replay-live test api ui ui-build stack down

help:
	@echo "BatchZero targets:"
	@echo "  falkordb      start FalkorDB only"
	@echo "  install       install backend dev deps (editable)"
	@echo "  seed          reseed the Port Meridian fixture"
	@echo "  replay        watch the full 4-role investigation"
	@echo "  replay-live   same, but drive the loop with the live LLM"
	@echo "  benchmark     correctness + latency over 3 clean runs"
	@echo "  test          run the pytest suite"
	@echo "  api           serve the API + built UI on :8000"
	@echo "  ui / ui-build run the dev server / build the UI"
	@echo "  stack / down  start / stop FalkorDB"

falkordb:
	docker compose up -d falkordb

install:
	cd backend && pip install -e ".[dev]"

seed:
	cd backend && python -m batchzero.seed --reset

replay:
	cd backend && python -m batchzero.demo.replay

replay-live:
	cd backend && python -m batchzero.demo.replay --live

benchmark:
	cd backend && python -m batchzero.demo.replay --benchmark 3

test:
	cd backend && pytest -q

api:
	cd backend && python -m batchzero.api.app

ui:
	cd frontend && npm install && npm run dev

ui-build:
	cd frontend && npm install && npm run build

stack:
	docker compose -f docker-compose.yml up -d falkordb
	cd backend && python -m batchzero.seed --reset

down:
	docker compose down
