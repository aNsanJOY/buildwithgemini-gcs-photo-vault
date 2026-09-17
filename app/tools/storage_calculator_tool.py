"""Storage cost calculator tool for GCS Photo Vault."""


def calculate_storage_cost_savings(
    library_size_gb: float,
    target_storage_class: str = "COLDLINE",
    current_storage_class: str = "STANDARD",
) -> str:
    """Calculates estimated monthly storage costs and savings when changing GCS storage tiers.

    Args:
        library_size_gb: Total size of photos or media in Gigabytes (GB).
        target_storage_class: Target storage class (e.g., NEARLINE, COLDLINE, ARCHIVE).
        current_storage_class: Current storage class (default: STANDARD).

    Returns:
        A breakdown of monthly costs and estimated monthly savings.
    """
    rates = {
        "STANDARD": 0.020,
        "NEARLINE": 0.010,
        "COLDLINE": 0.004,
        "ARCHIVE": 0.0012,
    }

    curr_class = current_storage_class.upper()
    targ_class = target_storage_class.upper()

    curr_rate = rates.get(curr_class, 0.020)
    targ_rate = rates.get(targ_class, 0.004)

    curr_cost = library_size_gb * curr_rate
    targ_cost = library_size_gb * targ_rate
    monthly_savings = curr_cost - targ_cost

    return (
        f"For {library_size_gb:.1f} GB of media:\n"
        f"• Current ({curr_class}): ${curr_cost:.2f}/month\n"
        f"• Target ({targ_class}): ${targ_cost:.2f}/month\n"
        f"• Estimated Monthly Savings: ${monthly_savings:.2f}"
    )
