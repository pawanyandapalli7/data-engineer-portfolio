"""
Reconciliation checks between source and target datasets.
"""

def reconcile_counts(source_count: int, target_count: int, tolerance: float = 0.01):
    """
    Compare source and target record counts.
    """
    if source_count == 0:
        return False

    diff_ratio = abs(source_count - target_count) / source_count
    return diff_ratio <= tolerance
