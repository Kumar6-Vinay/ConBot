# Contributing to ConBot

Thanks for your interest in contributing to ConBot.

This project is intended to be a practical, self-hosted AI assistant with a clean backend/frontend separation and a low-friction developer experience. We welcome issue reports, feature suggestions, documentation improvements, and code contributions.

## How to contribute

1. Fork the repository.
2. Create a feature branch from `main`.
3. Make your change.
4. Run the relevant tests before opening a pull request.
5. Open a pull request with a clear description of the change and why it matters.

## Development setup

```bash
git clone https://github.com/Kumar6-Vinay/ConBot.git
cd ConBot
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env
```

Then start the backend and frontend as described in the main README.

## Code expectations

- keep changes focused and easy to review
- prefer clear, small commits over broad refactors
- document new behavior where relevant
- add or update tests for bug fixes and new functionality
- avoid breaking existing configuration conventions unless the change is intentional and documented

## Testing

Run the test suite before submitting a pull request:

```bash
pytest -q
```

## Pull request guidelines

- keep PR titles concise and informative
- explain the problem and solution clearly
- include screenshots or examples when UI behavior changes
- mention configuration changes or environment impact
- link related issues when applicable

## Community expectations

Please be respectful, constructive, and helpful in discussions. We aim to keep this project collaborative, welcoming, and technically thoughtful.

## Reporting issues

Before opening a bug report or feature request, check whether it already exists.

Use clear issue titles and include:

- what happened
- what you expected to happen
- steps to reproduce
- relevant environment details
- any logs, screenshots, or API responses that help explain the issue

Thank you for helping improve ConBot.
