"""Turn DBML table, column and project names into on-screen labels.

The DBML (and the database) keeps names exactly as written; this is applied only where a
name is displayed: order_number -> "Order Number".
"""


def label(name: str) -> str:
    """Replace underscores with spaces and capitalise the first letter of each word.

    The rest of each word is left alone, so acronyms survive: slo_min -> "Slo Min",
    MFA_status -> "MFA Status", "Order Items" -> "Order Items".
    """
    return " ".join(
        word[:1].upper() + word[1:] for word in str(name).replace("_", " ").split()
    )
