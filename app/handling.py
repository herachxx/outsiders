"""Who acts on a ticket: the service never sends anything, it only labels the safe lane.

auto      the clarification draft may be sent by the integrating system without review
review    an administrator approves or edits the draft (one click when it is fine)
escalate  an administrator must decide first (urgent, sensitive, appeal or failed safety gate)
"""
AUTO_CATEGORIES = {'report.question', 'report.offtopic'}
AUTO_MIN_CONFIDENCE = 0.6
LANES = ('auto', 'review', 'escalate')


def decide(category, priority, needs_human, confidence, reasons, mandatory_human):
    risky = (priority == 'p0' or category in mandatory_human
             or any(r in reasons for r in ('appeal_requires_human', 'sensitive_category_override', 'critical_review'))
             or any(r.startswith('safety_') for r in reasons))
    if risky:
        return 'escalate'
    if (category in AUTO_CATEGORIES and priority == 'p3' and not needs_human
            and confidence >= AUTO_MIN_CONFIDENCE and 'language_uncertain' not in reasons):
        return 'auto'
    return 'review'
