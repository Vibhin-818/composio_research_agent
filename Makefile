.PHONY: install run analyze report all

install:
	py -m pip install -r requirements.txt

run:
	py run.py

analyze:
	py analysis.py

report:
	py report/build.py

all: run analyze report
