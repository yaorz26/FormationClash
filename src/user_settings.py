animations_enabled = True
show_arcanarch_in_draft = False


def toggle_animations() -> bool:
    global animations_enabled
    animations_enabled = not animations_enabled
    return animations_enabled


def toggle_arcanarch_in_draft() -> bool:
    global show_arcanarch_in_draft
    show_arcanarch_in_draft = not show_arcanarch_in_draft
    return show_arcanarch_in_draft
