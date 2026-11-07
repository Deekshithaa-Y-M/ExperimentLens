"""Typed errors raised while reading and validating raw datasets."""


class IngestionError(ValueError):
    """Base error for a dataset that cannot be safely ingested."""


class UnreadableInputError(IngestionError):
    """The supplied stream or file could not be read as CSV."""


class SchemaError(IngestionError):
    """The schema or semantic column mapping is invalid."""

