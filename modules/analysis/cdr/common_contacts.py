import pandas as pd

def common_contacts(cdrs):
    """Identifies overlapping counterparty targets across multi-target investigations."""
    if cdrs is None or len(cdrs) < 2:
        return pd.DataFrame([{"System Alert": "Multi-CDR analysis demands a minimum of 2 structural target frames."}])

    contact_sets = {}
    for target, info in cdrs.items():
        df = info.get("df")
        if df is not None and "b_party" in df.columns:
            contacts = set(df["b_party"].dropna().astype(str).str.strip())
            contacts.discard("")
            contact_sets[target] = contacts

    if len(contact_sets) < 2:
        return pd.DataFrame([{"System Alert": "Insufficient counterparty columns present across datasets."}])

    common_numbers = set.intersection(*contact_sets.values())
    
    result = []
    for num in sorted(common_numbers):
        result.append({"Common Intercept Number": num, "Total Cross Matches": len(cdrs)})
        
    return pd.DataFrame(result) if result else pd.DataFrame([{"Analysis Result": "Strict Isolation: No common numbers intersect across targets."}])