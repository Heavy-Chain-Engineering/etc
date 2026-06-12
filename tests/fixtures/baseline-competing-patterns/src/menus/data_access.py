"""Pattern A (again): the free-function style, used by the menus domain too."""


def get_menu(menu_id: int) -> dict[str, str]:
    return {"id": str(menu_id), "name": "Brunch"}
