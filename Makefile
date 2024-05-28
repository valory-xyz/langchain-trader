.PHONY: clean
clean: clean-test clean-build clean-pyc clean-docs

.PHONY: clean-build
clean-build:
	rm -fr build/
	rm -fr dist/
	rm -fr .eggs/
	rm -fr pip-wheel-metadata
	find . -name '*.egg-info' -exec rm -fr {} +
	find . -name '*.egg' -exec rm -fr {} +
	find . -type d -name __pycache__ -exec rm -rv {} +
	rm -fr Pipfile.lock
	rm -rf plugins/*/build
	rm -rf plugins/*/dist

.PHONY: clean-docs
clean-docs:
	rm -fr site/

.PHONY: clean-pyc
clean-pyc:
	find . -name '*.pyc' -exec rm -f {} +
	find . -name '*.pyo' -exec rm -f {} +
	find . -name '*~' -exec rm -f {} +
	find . -name '__pycache__' -exec rm -fr {} +
	find . -name '.DS_Store' -exec rm -fr {} +

.PHONY: clean-test
clean-test:
	rm -fr .tox/
	rm -f .coverage
	find . -name ".coverage*" -not -name ".coveragerc" -exec rm -fr "{}" \;
	rm -fr coverage.xml
	rm -fr htmlcov/
	rm -fr .hypothesis
	rm -fr .pytest_cache
	rm -fr .mypy_cache/
	rm -fr .hypothesis/
	find . -name 'log.txt' -exec rm -fr {} +
	find . -name 'log.*.txt' -exec rm -fr {} +

# isort: fix import orders
# black: format files according to the pep standards
.PHONY: formatters
formatters:
	tomte format-code

# black-check: check code style
# isort-check: check for import order
# flake8: wrapper around various code checks, https://flake8.pycqa.org/en/latest/user/error-codes.html
# mypy: static type checker
# pylint: code analysis for code smells and refactoring suggestions
# darglint: docstring linter
.PHONY: code-checks
code-checks:
	tomte check-code

# safety: checks dependencies for known security vulnerabilities
# bandit: security linter
.PHONY: security
security:
	tomte check-security
	gitleaks detect --report-format json --report-path leak_report

# generate latest hashes for updated packages
# generate docs for updated packages
# update copyright headers
.PHONY: generators
generators:
	tox -e abci-docstrings
	tomte format-copyright --author valory --exclude-part abci  --exclude-part http_client  --exclude-part ipfs  --exclude-part ledger  --exclude-part p2p_libp2p_client  --exclude-part gnosis_safe  --exclude-part gnosis_safe_proxy_factory  --exclude-part multisend  --exclude-part service_registry  --exclude-part acn  --exclude-part contract_api  --exclude-part http  --exclude-part ipfs  --exclude-part ledger_api --exclude-part tendermint --exclude-part abstract_abci --exclude-part abstract_round_abci --exclude-part registration_abci --exclude-part reset_pause_abci --exclude-part termination_abci --exclude-part transaction_settlement_abci --exclude-part http_server  --exclude-part mech --exclude-part mech_interact_abci
	autonomy packages lock

.PHONY: common-checks-1
common-checks-1:
	tomte check-copyright --author valory
	tomte check-doc-links
	tox -p -e check-hash -e check-packages -e check-doc-hashes

.PHONY: fix-abci-app-specs
fix-abci-app-specs:
	export PYTHONPATH=${PYTHONPATH}:${PWD}
	autonomy analyse fsm-specs --update --app-class LangchainTraderAbciApp --package packages/valory/skills/langchain_trader_abci/ || (echo "Failed to check langchain_trader_abci consistency" && exit 1)
	autonomy analyse fsm-specs --update --app-class LangchainTraderChainedSkillAbciApp --package packages/valory/skills/langchain_trader_chained_abci/ || (echo "Failed to check langchain_trader_chained_abci consistency" && exit 1)

.PHONY: tm
tm:
	rm -r ~/.tendermint
	tendermint init
	tendermint node --proxy_app=tcp://127.0.0.1:26658 --rpc.laddr=tcp://127.0.0.1:26657 --p2p.laddr=tcp://0.0.0.0:26656 --p2p.seeds= --consensus.create_empty_blocks=true

.PHONY: all-linters
all-linters:
	gitleaks detect --report-format json --report-path leak_report
	tox -e spell-check
	tox -e liccheck
	tox -e check-doc-hashes
	tox -e bandit
	tox -e safety
	tox -e check-packages
	tox -e check-abciapp-specs
	tox -e check-hash
	tox -e black-check
	tox -e isort-check
	tox -e flake8
	tox -e darglint
	tox -e pylint
	tox -e mypy

.PHONY: transfer_request
transfer_request:
	curl -X POST http://localhost:8000/request -H "Content-Type: application/json" -d '{"prompt":"Transfer 1 wei to 0x8D7102ce2d35a409535285252599c149FBeABB73"}' | jq

v := $(shell pip -V | grep virtualenvs)
