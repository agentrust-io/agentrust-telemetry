## Summary

## Contract impact

- [ ] No wire-contract change
- [ ] Backward-compatible contract change with fixtures
- [ ] Breaking contract change with migration notes

## Evidence

- [ ] `python tools/sync_schemas.py`
- [ ] `python tools/check_schemas.py`
- [ ] `python conformance/runner/validate.py`
- [ ] `python -m unittest discover -s tests -v`
- [ ] `python -m build`

## Privacy and security

- [ ] No real prompts, source, credentials, personal data, or production identifiers added
- [ ] New fields have capture semantics and privacy classification
- [ ] Security-sensitive changes received maintainer review

## Limits

State what this change does not prove or cover.
