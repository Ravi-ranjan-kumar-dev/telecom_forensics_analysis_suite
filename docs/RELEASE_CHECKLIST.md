# Release Checklist

1. Work from a clean source copy; do not include operational evidence.
2. Install `requirements-dev.txt` in a fresh virtual environment.
3. Run `python tools/release_check.py`.
4. Run `python tools/release_check.py --with-db` only against a backed-up operational CGI database.
5. Confirm all tests pass and Python compilation succeeds.
6. Confirm ZIP excludes `.git`, virtual environments, caches, `data/`, `cases/`, `output/`, databases and logs.
7. Record SHA-256 for the release ZIP.
8. Test upgrade on a copy of the operational project before replacing the working installation.
9. Keep the dated pre-upgrade backup until representative CDR, Tower Dump, GPRS and IPDR workflows have been verified.
10. Never describe analytical indicators as proven facts without independent corroboration.
