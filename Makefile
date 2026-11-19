.PHONY: install run test compose-up compose-down
install:
	pip install -r requirements.txt
run:
	uvicorn app.main:app --reload --host 127.0.0.1 --port 8888
test:
	pytest -q
compose-up:
	docker compose up --build -d
compose-down:
	docker compose down
