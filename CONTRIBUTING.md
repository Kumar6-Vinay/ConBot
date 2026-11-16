# Contributing to ConBot

Thanks for your interest in improving ConBot. Contributions that improve correctness, reliability, accessibility, security, or developer experience are welcome.

## Development setup

Use Python 3.12, matching the CI workflow and Docker image:

```bash
git clone https://github.com/Kumar6-Vinay/ConBot.git
cd ConBot
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env
```

Set credentials only for the provider/model configuration you plan to exercise. Tests should not require real upstream API credentials; mock external calls in new tests. See the README for local API and frontend instructions.

## Before opening a pull request

1. Keep changes focused and explain the user or engineering problem they address.
2. Add or update tests for behavior changes and bug fixes.
3. Run `pytest -q` and report the result.
4. Update documentation and `.env.example` when configuration or API behavior changes.
5. Never include API keys, personal data, or production request contents in commits, fixtures, logs, or screenshots.
6. For frontend changes, include a screenshot or short recording when it helps reviewers assess the result.

## Pull request description

Please include:

- the problem and proposed solution;
- notable tradeoffs or compatibility changes;
- how the change was tested;
- any new environment variables or deployment steps.

For security-sensitive issues, follow [SECURITY.md](SECURITY.md) rather than filing a public issue with exploit details.
