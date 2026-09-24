import hashlib
import hmac
from langfuse import propagate_attributes

from remember_this.agent.agent import UserIdentifier, agent
from remember_this.config import get_settings
from remember_this.observability.tracing import langfuse

_settings = get_settings()


def hash_user_id(user_id: int) -> str:
    salt = _settings.user_id_salt.get_secret_value().encode()
    return hmac.new(salt, str(user_id).encode(), hashlib.sha256).hexdigest()


async def run_turn(user_id: int, message: str) -> str:
    with propagate_attributes(
        user_id=hash_user_id(user_id)
    ):
        with langfuse.start_as_current_observation(
            as_type="span",
            name="turn",
            input={"message": message},
        ) as span:
            result = await agent.run(message, deps=UserIdentifier(user_id))
            span.update(output={"reply": result.output})
            return result.output
