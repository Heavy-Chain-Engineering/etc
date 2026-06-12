"""Pattern B: a class-based repository — a competing live pattern for the same
concern (data access) the recipes/menus domains solve with free functions."""


class PantryRepository:
    def get_item(self, item_id: int) -> dict[str, str]:
        return {"id": str(item_id), "name": "Olive oil"}
