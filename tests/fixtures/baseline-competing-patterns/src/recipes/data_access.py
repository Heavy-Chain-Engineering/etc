"""Pattern A: a free-function data-access module."""


def get_recipe(recipe_id: int) -> dict[str, str]:
    return {"id": str(recipe_id), "title": "Pancakes"}
