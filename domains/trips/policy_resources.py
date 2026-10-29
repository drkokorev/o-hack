"""Validated, versioned dialogue content shared by routing and response policy."""
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class QuestionSpec(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    input_fields: frozenset[str]
    why: str = Field(min_length=1)
    example: str = Field(min_length=1)


class DialoguePolicy(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    questions: dict[str, QuestionSpec]
    replies: dict[str, str]
    event_autofill_max_days: int = Field(ge=1, le=31)


@lru_cache(maxsize=1)
def dialogue_policy() -> DialoguePolicy:
    path = Path(__file__).parent / 'data' / 'dialogue_policy.ru.json'
    policy = DialoguePolicy.model_validate_json(path.read_text(encoding='utf-8'))
    from .state import TripUpdate
    for key, spec in policy.questions.items():
        if not spec.input_fields <= TripUpdate.model_fields.keys():
            raise ValueError(f'Unknown input field in dialogue policy: {key}')
    required = {'greeting', 'thanks', 'pause', 'capabilities', 'repair', 'data_provenance',
                'unknown', 'empty_summary', 'preview', 'preview_unresolved'}
    if not required <= policy.replies.keys() or any(not text.strip() for text in policy.replies.values()):
        raise ValueError('Incomplete dialogue reply policy')
    return policy
