# आसान Installation / Upgrade Guide

## बड़े local database वाले project के लिए source-only update

अगर project में बड़ा `database/`, `data/` या `cases/` folder है, तो full-backup
installer चलाने से पहले free disk space जाँचें। Source-only release archive के
लिए extracted source को project पर overlay करना कम disk space लेता है:

```bash
mkdir -p ~/Desktop/telecom_source_update
tar -xzf ~/Downloads/telecom_forensics_cdr_fast_bottom_enrichment_20260823.tar.gz \
  -C ~/Desktop/telecom_source_update

cp -a \
  ~/Desktop/telecom_source_update/telecom_forensics_analysis_suite/. \
  ~/Desktop/telecom_forensics_analysis_suite/
```

यह तरीका केवल उस release archive के लिए use करें जिसमें `database/`, `data/`,
`cases/` और `output/` runtime content नहीं है। Overlay से पहले current source
का patch/untracked backup रखना सही है।

## Full installer तरीका

नई ZIP को पुराने project के ऊपर सीधे extract न करें। पहले उसे अलग folder में extract करें। मान लेते हैं नया extracted folder `~/Downloads/telecom_forensics_analysis_suite_final` है।

```bash
cd ~/Downloads/telecom_forensics_analysis_suite_final
python tools/install_or_upgrade.py --destination ~/Desktop/telecom_forensics_analysis_suite
```

यह tool अपने आप:

- पुराने project का date/time वाला पूरा backup बनाएगा;
- नया source staging folder में copy करेगा;
- पुराने `data/`, `cases/`, `output/` और operational database files preserve करेगा;
- installation fail होने पर पुराने project को restore करने की कोशिश करेगा।

Full installer destination की पूरी backup और staging copy बनाता है। इसलिए free
space लगभग existing project के दो अतिरिक्त copies जितनी होनी चाहिए। बड़े
database वाले project में पर्याप्त space न हो तो ऊपर वाला source-only overlay
use करें।

## Dependencies

```bash
cd ~/Desktop/telecom_forensics_analysis_suite
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

## Verification

```bash
python -m pytest -q
git diff --check
```

सभी tests pass होने चाहिए और `git diff --check` को कोई output नहीं देना चाहिए।

Test के बाद:

```bash
python3 -u run_gui.py
```

`qt.accessibility.atspi` वाला message सामान्य desktop accessibility warning है;
यह analysis failure नहीं है।

## जरूरी सावधानी

- Backup folder को तुरंत delete न करें।
- Real evidence files पर test करने से पहले anonymized/sample data पर workflow check करें।
- Existing database पर `--with-db` check चलाने से पहले database backup रखें।
- `data`, `cases`, reports या database वाली ZIP किसी public service पर upload न करें।
