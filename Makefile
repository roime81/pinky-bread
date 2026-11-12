.PHONY: install run test compose-up compose-down
install:
	pip install -r requirements.txt
run:
	uvicorn app.main:app --reload --host 127.0.0.1 --port 8080
test:
	pytest -q
compose-up:
	docker compose up --build
compose-down:
	docker compose down
