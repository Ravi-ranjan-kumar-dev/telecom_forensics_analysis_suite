import pandas as pd

def analyze_location(df):
    """Analyze the first cell ID towers profile."""
    if df is None or df.empty or 'first_cell_id' not in df.columns:
        return pd.DataFrame()
        
    location_summary = {
        "Metric": ["Total Logged Cell Sites", "Unique Cell Towers Discovered", "Primary/Most Frequent Cell Site"],
        "Value": [
            len(df),
            df['first_cell_id'].nunique(),
            df['first_cell_id'].mode().iloc[0] if not df['first_cell_id'].dropna().empty else "N/A"
        ]
    }
    return pd.DataFrame(location_summary)

def frequent_locations(df, top_n=5):
    """Returns a DataFrame of top cell towers (fixes behavioral intelligence crash)."""
    if df is None or df.empty or 'first_cell_id' not in df.columns:
        return pd.DataFrame(columns=["Cell ID", "Total Events"])
        
    counts = df['first_cell_id'].value_counts().head(top_n).reset_index()
    counts.columns = ["Cell ID", "Total Events"]
    return counts