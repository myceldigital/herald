# Security Policy

## Reporting a Vulnerability

If you believe you have found a security issue in Herald, please use GitHub's private vulnerability reporting flow instead of opening a public issue.

Steps:

1. Open the repository's `Security` tab.
2. Click `Report a vulnerability`.
3. Include a clear description, impact, and reproduction steps if possible.

Please avoid public disclosure until the issue has been reviewed and a fix path is clear.

## Scope

Herald is clinical guideline infrastructure, so security issues may include:

- command injection or unsafe file handling
- maliciously crafted input files causing unsafe behavior
- unsafe dependency or workflow configuration
- accidental exposure of secrets or sensitive repository settings

Clinical correctness problems are important, but they should usually be reported as standard issues unless they create a true security impact.
