.PHONY: run run-qt install-qt clean

VENV := venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

run: $(VENV)/bin/activate
	$(PYTHON) -m sqlbench --tk

run-qt: $(VENV)/bin/activate
	@if ! $(PIP) show PyQt6 > /dev/null 2>&1; then \
		echo "Installing PyQt6..."; \
		$(PIP) install PyQt6; \
	fi
	$(PYTHON) -m sqlbench --qt

install-qt: $(VENV)/bin/activate
	$(PIP) install PyQt6

$(VENV)/bin/activate: requirements.txt
	python3 -m venv $(VENV) && \
	$(PIP) install --upgrade pip && \
	$(PIP) install -r requirements.txt

clean:
	rm -rf $(VENV)
	rm -f sqlbench.db
	find . -type d -name __pycache__ -exec rm -rf {} +
