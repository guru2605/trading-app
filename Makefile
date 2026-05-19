.PHONY: build up down db migrate test fix

build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down

db:
	docker compose up -d db redis

migrate:
	poetry run alembic upgrade head

test:
	poetry run pytest tests/ -v

fix:
	./tasks.sh -x
