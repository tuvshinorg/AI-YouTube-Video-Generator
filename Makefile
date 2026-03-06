PYTHON := python3
PIPELINE := pipeline.py

.DEFAULT_GOAL := help

.PHONY: help setup cli run run-file feed image voice clip subtitle transition mix final upload clean cron-show cron-remove

help:
	@echo "AI YouTube Video Generator"
	@echo ""
	@echo "First time:"
	@echo "  make setup          — install deps, create dirs, init DB, install cron"
	@echo ""
	@echo "Management:"
	@echo "  make cli            — interactive CLI (add RSS, queue, run, stop…)"
	@echo ""
	@echo "Pipeline:"
	@echo "  make run            — run full pipeline + upload to YouTube"
	@echo "  make run-file       — run full pipeline, save .mp4 for manual upload"
	@echo "  make feed           — module 01: fetch RSS → generate scenes"
	@echo "  make image          — module 02: generate images with Flux"
	@echo "  make voice          — module 03: text-to-speech"
	@echo "  make clip           — module 04: image + audio → video clip"
	@echo "  make subtitle       — module 05: burn subtitles"
	@echo "  make transition     — module 06: add transitions between clips"
	@echo "  make mix            — module 07: mix narration + background music"
	@echo "  make final          — module 08: merge video + audio"
	@echo "  make upload         — module 09: upload to YouTube"
	@echo "  make clean          — module 10: delete temp files"
	@echo ""
	@echo "Cron:"
	@echo "  make cron-show      — print current crontab"
	@echo "  make cron-remove    — remove the pipeline cron entry"

setup:
	bash setup.sh

cli:
	$(PYTHON) cli.py

run:
	$(PYTHON) $(PIPELINE) --output api

run-file:
	$(PYTHON) $(PIPELINE) --output file

feed:
	$(PYTHON) $(PIPELINE) --module feed

image:
	$(PYTHON) $(PIPELINE) --module image

voice:
	$(PYTHON) $(PIPELINE) --module voice

clip:
	$(PYTHON) $(PIPELINE) --module clip

subtitle:
	$(PYTHON) $(PIPELINE) --module subtitle

transition:
	$(PYTHON) $(PIPELINE) --module transition

mix:
	$(PYTHON) $(PIPELINE) --module mix

final:
	$(PYTHON) $(PIPELINE) --module final

upload:
	$(PYTHON) $(PIPELINE) --module upload

clean:
	$(PYTHON) $(PIPELINE) --module clean

cron-show:
	crontab -l

cron-remove:
	crontab -l 2>/dev/null | grep -v "# ai-youtube-video-generator" | grep -v "pipeline.py" | crontab -
	@echo "Cron entry removed"
