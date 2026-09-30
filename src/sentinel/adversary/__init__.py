"""
sentinel.adversary
==================
Attack catalog and adversary models.

Attacks act on physics (channels, which pairs Eve holds, correction bits,
which states a dishonest signer sends) or on protocol messages (envelopes,
declared labels, delivery timing and destination). They never touch
verification reports or assessments.
"""

from sentinel.adversary.catalog import CATALOG, AttackSpec, catalog_entry, validate_spec

__all__ = ["CATALOG", "AttackSpec", "catalog_entry", "validate_spec"]
