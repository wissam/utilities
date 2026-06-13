PREFIX ?= $(HOME)/.local
BINDIR ?= $(PREFIX)/bin

.PHONY: install
install:
	install -d "$(BINDIR)"
	install -m 0755 scripts/linear-rank-issues.py "$(BINDIR)/linear-rank-issues"
	install -m 0755 scripts/velastra-sonar-scan.sh "$(BINDIR)/velastra-sonar-scan"
