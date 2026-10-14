import hashlib
import hmac
from langfuse import propagate_attributes
from pydantic import BaseModel

from remember_this.agent.agent import UserIdentifier, agent
from remember_this.config import get_settings
from remember_this.llm.answer import Answer
from remember_this.llm.extraction import ExtractionResult
from remember_this.observability.tracing import langfuse

_settings = get_settings()


def hash_user_id(user_id: int) -> str:
    salt = _settings.user_id_salt.get_secret_value().encode()
    return hmac.new(salt, str(user_id).encode(), hashlib.sha256).hexdigest()


class TurnResult(BaseModel):
    reply: str
    tool_called: str | None
    cited_memory_ids: list[int]
    # True/False only for a search_memories turn; None for save_memories or no tool
    # call, where "did it abstain" isn't a meaningful question. Derived from the
    # tool's own return value (an empty citation list on search_memories only ever
    # happens via the hardcoded abstain branch in tools.py), not from the reply
    # text -- a well-formed abstention can be worded many ways ("the dinner was
    # cancelled, so there's no location" is a correct abstention that never says
    # "nothing recorded"), so matching on fixed phrases in the reply is unreliable.
    abstained: bool | None


def _extract_tool_call(messages: list) -> tuple[str | None, list[int], bool | None]:
    """Pull which tool ran, any cited memory ids, and whether it abstained out of
    the run's message history.
    """
    for message in messages:
        for part in getattr(message, "parts", []):
            tool_name = getattr(part, "tool_name", None)
            content = getattr(part, "content", None)
            if tool_name is None or content is None:
                continue
            if isinstance(content, Answer):
                return tool_name, content.cited_memory_ids, not content.cited_memory_ids
            if isinstance(content, ExtractionResult):
                return tool_name, [], None
    return None, [], None


async def run_turn(user_id: int, message: str) -> TurnResult:
    with propagate_attributes(
        user_id=hash_user_id(user_id)
    ):
        with langfuse.start_as_current_observation(
            as_type="span",
            name="turn",
            input={"message": message},
        ) as span:
            result = await agent.run(message, deps=UserIdentifier(user_id))
            tool_called, cited_memory_ids, abstained = _extract_tool_call(result.all_messages())
            span.update(
                output={"reply": result.output},
                metadata={
                    "tool_called": tool_called,
                    "cited_memory_ids": cited_memory_ids,
                    "abstained": abstained,
                },
            )
            return TurnResult(
                reply=result.output,
                tool_called=tool_called,
                cited_memory_ids=cited_memory_ids,
                abstained=abstained,
            )
