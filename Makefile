VISUAL_DIRS ?= $(wildcard sti_reports/*)

.PHONY: visual-check
visual-check:
	@echo "Running visual QA for $(VISUAL_DIRS)"
	@python3 visual_qc.py $(VISUAL_DIRS)
	@python3 visual_template_audit.py $(VISUAL_DIRS)

.PHONY: source-check
source-check:
	@echo "Running source QA for $(VISUAL_DIRS)"
	@python3 source_qc.py $(VISUAL_DIRS)

.PHONY: report-check
report-check: visual-check source-check
