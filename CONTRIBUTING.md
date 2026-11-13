# Contributing

Issues and pull requests are welcome – bug reports, translations, ideas.

## Development

```bash
pip install -e ".[dev]"
python -m pytest
tapinion demo && tapinion serve      # http://127.0.0.1:8000, kiosk PIN of the demo events: 1234
```

- New code, comments and file names in English; user-facing texts go into
  `tapinion/locales/en.json` and `de.json` (both, same keys).
- Every change to behaviour comes with a test in `tests/`.
- UI changes: check the kiosk on a tablet in landscape and portrait.

## Licence of contributions

Tapinion is licensed under the AGPL-3.0-or-later. By submitting a contribution you agree that it
is licensed under the same terms, and you confirm that you have the right to submit it
([Developer Certificate of Origin](https://developercertificate.org/)). Please sign off your
commits: `git commit -s`.
