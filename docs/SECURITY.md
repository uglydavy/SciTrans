# Security Policy

## Reporting a Vulnerability

If you discover a security issue in SciTrans (e.g., API keys accidentally logged, path traversal, arbitrary file write, command injection), please report it privately.

**Do NOT open a public issue with exploit details.**

### How to Report

1. Email: aknk.v@pm.me
2. Subject: [SECURITY] Brief description
3. Include:
   - Affected versions
   - Steps to reproduce
   - Impact assessment
   - Suggested fix (if any)

We will respond within 48 hours and work with you to address the issue.

## Sensitive Data

**Never commit:**
- API keys (`*_API_KEY`, `sk-*`, etc.)
- `.env` files
- Generated outputs in `outputs/`, `previews/`
- Personal or proprietary PDFs
- Cache files or logs containing sensitive data

## Security Best Practices

### For Users

1. **Environment variables:**
   - Store API keys in environment variables, not in code
   - Use `.env` (gitignored) or system environment
   - Never commit `.env` to version control

2. **API key rotation:**
   - Rotate keys regularly (monthly recommended)
   - Revoke keys immediately if exposed
   - Use separate keys for dev/prod

3. **Pre-commit hooks:**
   ```bash
   pip install pre-commit
   pre-commit install
   ```
   This will detect private keys before commits.

4. **Input validation:**
   - Don't process untrusted PDFs without sandboxing
   - Be aware of PDF malware risks
   - Validate all user inputs

### For Developers

1. **Code security:**
   - Never log API keys or secrets
   - Sanitize file paths to prevent traversal
   - Use subprocess safely (no shell=True with user input)
   - Validate all external inputs

2. **Dependencies:**
   - Keep dependencies up-to-date
   - Monitor security advisories
   - Use `pip-audit` to check for vulnerabilities

3. **Testing:**
   - Test with invalid/malicious inputs
   - Verify error messages don't leak sensitive info
   - Check that secrets are never printed

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Security Checklist

Before deployment:
- [ ] All API keys loaded from environment
- [ ] No hardcoded secrets in code
- [ ] Pre-commit hooks detect private keys
- [ ] Error messages sanitized
- [ ] Input validation in place
- [ ] Dependencies audited (`pip-audit`)
- [ ] Logs don't contain sensitive data
- [ ] `.gitignore` blocks `.env` and secrets

## Known Security Considerations

1. **PDF Processing:** PyMuPDF processes potentially untrusted PDFs. Use in sandboxed environments for production.
2. **API Keys:** Backend API keys have access to your accounts. Protect them carefully.
3. **File System:** The system writes to `outputs/`. Ensure proper permissions.

## Updates

Security updates will be released as patch versions (e.g., 1.0.1) and announced in release notes.

