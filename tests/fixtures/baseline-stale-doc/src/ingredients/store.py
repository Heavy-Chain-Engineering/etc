"""Ingredients store — queries the DB inline, contradicting the convention doc."""


def list_ingredients() -> list[str]:
    # The doc says data access lives in data_access.py; here it is inline.
    return ["flour", "sugar", "butter"]
