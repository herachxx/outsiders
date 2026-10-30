PYTHON ?= python
RULES ?= $(GRAND_RULES_PATH)
MODEL ?= $(GRAND_MODEL_PATH)

.PHONY: predict test serve
predict:
	$(PYTHON) -m app.batch --input "$(IN)" --output "$(OUT)" --rules "$(RULES)" $(if $(MODEL),--model "$(MODEL)",)

test:
	$(PYTHON) -m pytest -q

serve:
	$(PYTHON) -m uvicorn app.api:app --host 127.0.0.1 --port 8000
