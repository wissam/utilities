PREFIX ?= $(HOME)/.local
BINDIR ?= $(PREFIX)/bin

.PHONY: install
install:
	install -d "$(BINDIR)"
	install -m 0755 scripts/linear-rank-issues.py "$(BINDIR)/linear-rank-issues"
