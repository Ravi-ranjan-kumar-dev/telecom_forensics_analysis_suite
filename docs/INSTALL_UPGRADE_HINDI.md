# आसान Installation / Upgrade Guide

## सबसे सुरक्षित तरीका

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
python tools/release_check.py
```

Expected:

```text
46 passed
RELEASE CHECK: PASS
```

Test के बाद:

```bash
python main.py
```

## जरूरी सावधानी

- Backup folder को तुरंत delete न करें।
- Real evidence files पर test करने से पहले anonymized/sample data पर workflow check करें।
- Existing database पर `--with-db` check चलाने से पहले database backup रखें।
- `data`, `cases`, reports या database वाली ZIP किसी public service पर upload न करें।
