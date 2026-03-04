.PHONY: install dev test lint format clean

install:
	pip install -e ".[dev,serving,example]"

dev:
	uvicorn modelforge.main:app --reload --host 0.0.0.0 --port 8000

test:
	pytest tests/ -v

lint:
	ruff check src/ tests/

format:
	ruff format src/ tests/

clean:
	rm -rf build/ dist/ *.egg-info .pytest_cache .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} +
	rm -f *.db
