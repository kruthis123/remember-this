FORGET_CONFIRM_PREFIX = "forget:confirm:"
FORGET_CANCEL_PREFIX = "forget:cancel:"


def forget_confirmation_keyboard(user_id: int) -> dict:
    """Inline keyboard for /forget. user_id is embedded for bookkeeping only --
    the callback handler must re-verify against callback_query["from"]["id"]
    before deleting anything, never trust this value alone.
    """
    return {
        "inline_keyboard": [
            [
                {"text": "Yes, delete everything", "callback_data": f"{FORGET_CONFIRM_PREFIX}{user_id}"},
                {"text": "Cancel", "callback_data": f"{FORGET_CANCEL_PREFIX}{user_id}"},
            ]
        ]
    }


def parse_forget_callback(callback_data: str) -> tuple[bool, int] | None:
    """Returns (confirmed, claimed_user_id), or None if callback_data doesn't
    belong to the /forget flow at all.
    """
    if callback_data.startswith(FORGET_CONFIRM_PREFIX):
        return True, int(callback_data[len(FORGET_CONFIRM_PREFIX):])
    if callback_data.startswith(FORGET_CANCEL_PREFIX):
        return False, int(callback_data[len(FORGET_CANCEL_PREFIX):])
    return None
