.PHONY: run install clean

VENV := venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

run: $(VENV)
	$(PYTHON) -m sqlbench

install: $(VENV)

$(VENV): requirements.txt
	python3 -m venv $(VENV)
	$(PIP) install -r requirements.txt
	touch $(VENV)

clean:
	rm -rf $(VENV)
	rm -f sqlbench.db
	find . -type d -name __pycache__ -exec rm -rf {} +
