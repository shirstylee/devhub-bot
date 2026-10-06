from bot.services.render_history import render_history_store
from bot.services.render_settings import render_settings_store
from bot.services.user_preferences import user_preferences_store


PRIVATE_STORES = (user_preferences_store, render_settings_store, render_history_store)


async def prune_non_admin_data() -> int:
    return sum([await store.prune_non_admins() for store in PRIVATE_STORES])


async def forget_user_data(user_id: int) -> None:
    for store in PRIVATE_STORES:
        await store.forget_user(user_id)
