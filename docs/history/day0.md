🛡️ Digital Investigation Suite (DIS)

Ye ek investigation platform hoga jisme alag-alag analysis engines honge.

                     Digital Investigation Suite
                               │
    ┌──────────────────────────┼──────────────────────────┐
    │                          │                          │
 CDR Analysis             Tower Analysis           IPDR Analysis
    │                          │                          │
    │                          │                          │
 Subscriber DB            CGI Database            IMEI Database
    │                          │                          │
    └────────────── Intelligence Engine ──────────────────┘
                               │
                         Report Generator
                               │
                     Excel | PDF | Dashboard



1. Receive CDR

↓

2. Detect Target Number

↓

3. Clean Data

↓

4. Find Important Contacts

↓

5. Subscriber Lookup (SDR)

↓

6. Cell ID Lookup (CGI)

↓

7. Find Frequent Towers

↓

8. IMEI Analysis

↓

9. Timeline Analysis

↓

10. Tower Dump Analysis (if available)

↓

11. IPDR Analysis (if available)

↓

12. Common Contact Analysis

↓

13. Generate Report

↓

14. Submit Investigation Report





.
├── data/                        # Ekdum sahi hai (CDR, IPDR, Tower Dump sorted hain)
├── database/                    # SQLite DB file (.db) yahan store hogi
├── main.py                      # Pure system ka AKELTA entry point (ya app.py for Streamlit)
├── modules/
│   ├── controllers/             # Orchestration Layer (Bina badlav ke sahi hai)
│   │   ├── cdr_controller.py
│   │   ├── ipdr_controller.py
│   │   └── tower_controller.py
│   │
│   ├── loader/                  # Data read karne ki akeli jagah (Faltu duplicate files yahan se hatao)
│   │   ├── single_loader.py
│   │   ├── multi_loader.py
│   │   └── path_manager.py
│   │
│   ├── mapper/                  # Top-notch! Operator mapping ke liye perfect hai
│   │   ├── jio.py | airtel.py | vi.py | bsnl.py
│   │   └── mapper.py            # Central mapping coordinator
│   │
│   ├── database/                # SDR aur CGI mapping database logic
│   │   ├── cgi.py               # CGI Tower Address lookups
│   │   └── subscriber.py        # SDR lookups (Name, Address)
│   │
│   ├── analysis/                # Asli core analysis core logic (Cleanup ke baad)
│   │   ├── cdr/                 # Keep only 1 file per feature (e.g., direct timeline.py, movement.py)
│   │   ├── ipdr/
│   │   └── towerdump/
│   │
│   └── reports.py               # Outputs (PDF/HTML/Print) export karne ke liye
└── requirements.txt



Final recomended order-

Phase A: Project safety + clean structure
Phase B: Common Scalable Processing Layer
Phase C: DuckDB staging database
Phase D: Uncommon Number / Rare Visitor function
Phase E: Apply scalable mode to Tower IPDR, Tower CDR, GPRS, Multiple CDR, Multiple IPDR
Phase F: GUI-ready service layer
Phase G: GUI version