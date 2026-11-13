# Security

Please report vulnerabilities privately via GitHub's *Report a vulnerability* (Security tab of this
repository), not in public issues.

## Design notes

- Passwords are stored as scrypt hashes; sessions are signed cookies (`SECRET_KEY`).
- All state-changing requests need a CSRF token; login and kiosk PIN attempts are rate limited.
- Kiosk PINs are short codes for operating a device, stored readable so staff can look them up.
  They protect the kiosk screen, not the results; results always need a login.
- A kiosk device is never logged in: starting a kiosk ends the login on that browser.
- Uploaded SVG logos are served with a restrictive Content-Security-Policy.
- Run servers behind HTTPS and set `COOKIE_SECURE=1`. The desktop app serves plain HTTP in the
  local network; use it in trusted networks.
