"""Export the PDF example's citation format, retaining detailed sources internally."""
from .schemas import SubmissionResponse, TriageResponse


def to_submission(result: TriageResponse | dict) -> dict:
    result = TriageResponse.model_validate(result)
    data = result.model_dump()
    data['draft_reply']['cited'] = list(dict.fromkeys(c.ref for c in result.draft_reply.cited))
    data['extracted'].pop('claims', None)
    return SubmissionResponse.model_validate(data).model_dump()
