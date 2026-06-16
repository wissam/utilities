PREFIX ?= $(HOME)/.local
BINDIR ?= $(PREFIX)/bin
DATADIR ?= $(PREFIX)/share/velastra-sonar

.PHONY: install
install:
	install -d "$(BINDIR)"
	install -d "$(DATADIR)"
	install -m 0644 config/velastra-sonar-projects.tsv "$(DATADIR)/projects.tsv"
	install -m 0755 scripts/codex-git-push.sh "$(BINDIR)/codex-git-push"
	install -m 0755 scripts/linear-rank-issues.py "$(BINDIR)/linear-rank-issues"
	install -m 0755 scripts/sonarqube-mcp.py "$(BINDIR)/sonarqube-mcp"
	install -m 0755 scripts/velastra-sonar-summary.py "$(BINDIR)/velastra-sonar-summary"
	install -m 0755 scripts/velastra-sonar-scan.sh "$(BINDIR)/velastra-sonar-scan"
