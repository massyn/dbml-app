"""Turn DBML table, column and project names into on-screen labels.

The DBML (and the database) keeps names exactly as written; this is applied only where a
name is displayed: order_number -> "Order Number".
"""

# Common acronyms written in capitals when a name has them in lower case: metric_id ->
# "Metric ID". Only whole words match, and only words written all in lower case; a word
# with any capital in it is left as the author wrote it.
ACRONYMS = frozenset(
    {
        "abn", "api", "csv", "dns", "gst", "html", "http", "https", "id", "ip", "json",
        "kpi", "mfa", "pdf", "sku", "sla", "slo", "sql", "sso", "uri", "url", "uuid",
        "vat", "vpn",
    }
)  # fmt: skip


def _word(word: str) -> str:
    if word in ACRONYMS:
        return word.upper()
    return word[:1].upper() + word[1:]


def label(name: str) -> str:
    """Replace underscores with spaces and capitalise the first letter of each word.

    Common acronyms in lower case are written in capitals (slo_min -> "SLO Min"). The
    rest of each word is left alone: MFA_status -> "MFA Status", "Order Items" ->
    "Order Items".
    """
    return " ".join(_word(word) for word in str(name).replace("_", " ").split())
