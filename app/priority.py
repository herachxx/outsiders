"""Provisional routing policy; final taxonomy approval is still pending."""
from dataclasses import dataclass
import re

POLICY_VERSION = 'draft-2026-10-30'
MANDATORY_HUMAN = {'report.account', 'report.payment', 'complaint.admin'}


@dataclass(frozen=True)
class RouteDecision:
    priority: str
    needs_human: bool
    reasons: tuple[str, ...]


def route(category: str, text: str, has_attachments: bool = False) -> RouteDecision:
    text = text.casefold().replace('ё', 'е')
    reasons = ['policy_draft']
    human = category.startswith('complaint.') or category in {
        'report.account', 'report.payment', 'report.help', 'report.complaint', 'report.offtopic'}
    if category in MANDATORY_HUMAN:
        reasons.append('mandatory_human')
    urgent = bool(re.search(r'взлом|не могу войти|потер.{0,15}доступ|оплат|платеж|деньги спис|массов.{0,12}баг|угроз.{0,20}(жизн|вне игры)', text))
    appeal = bool(re.search(r'разбан|апелляц|обжал|бан.{0,15}без причин|мут.{0,15}без причин', text))
    if appeal:
        human = True
        reasons.append('appeal_requires_human')
    if category in {'report.account', 'report.payment'} or urgent:
        priority = 'p0'
        human = True
        reasons.append('critical_review')
    elif category.startswith('complaint.') and has_attachments:
        priority = 'p1'
        reasons.append('attachments_require_review')
    elif category in {'complaint.cheat', 'complaint.scam', 'complaint.rmt_ads'}:
        priority = 'p1'
    elif category in {'complaint.invalid', 'report.question', 'report.offtopic'}:
        priority = 'p3'
    else:
        priority = 'p2'
    return RouteDecision(priority, human, tuple(reasons))
