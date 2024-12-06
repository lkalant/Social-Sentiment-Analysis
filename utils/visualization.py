# utils/visualization.py

# Placeholder module for additional visualization utilities if needed.
# Currently, main graph logic is in the app class. If desired, refactor graph updates here.

def smooth_values(values, window=20):
    import pandas as pd
    return pd.Series(values).rolling(window=window, min_periods=1).mean()
