IMAGE := evaluate

.PHONY: all build run test clean setup

all: setup run

build:
	docker build -t $(IMAGE) .

run: build
	docker run --env-file .env -v "$(PWD)":/app $(IMAGE)

test: build
	docker run --env-file .env -v "$(PWD)":/app $(IMAGE) pytest tests/ -v

setup:
	@if [ ! -f .env ]; then \
		echo "OPENAI_API_KEY=" > .env; \
		echo "Created .env — add your OpenAI API key and re-run make"; \
		false; \
	elif ! grep -q 'OPENAI_API_KEY=.\+' .env; then \
		echo "OPENAI_API_KEY is empty in .env — add your key and re-run make"; \
		false; \
	fi

clean:
	rm -rf output/ __pycache__ .pytest_cache
