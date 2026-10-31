"""Provisional routing policy; final taxonomy approval is still pending."""
from dataclasses import dataclass
import re

POLICY_VERSION = 'draft-2026-10-30'
MANDATORY_HUMAN = {'report.account', 'report.payment', 'complaint.admin'}


def multilingual_sensitive_category(text: str) -> str | None:
    """Conservative kk/Latin uz signals; not a complete language classifier."""
    text = ' '.join(text.casefold().split())
    for mark in ('‘', '’', 'ʻ', 'ʼ', '`'):
        text = text.replace(mark, "'")
    # Keep explicit negative hack claims out of this signal. Do not suppress a
    # separate access failure elsewhere in the message or downgrade its category.
    hack = r"бұзылды\b|бұзылған\b(?!\s+жоқ)|buzib kir(?:ildi|ilgan)\b(?!\s+emas)"
    account = rf"(?:аккаунт|тіркелгі|akkaunt|hisob)[^.!?;]{{0,30}}(?:кіре алмай|kira olmay|{hack})"
    payment = r"төлем.{0,25}жасады|ақша.{0,20}(?:түспеді|шешілді)|pul.{0,20}yechild|to'lov.{0,20}qild|(?:donat|донат).{0,20}kelmadi"
    if re.search(account, text):
        return 'report.account'
    if re.search(payment, text):
        return 'report.payment'
    return None


@dataclass(frozen=True)
class RouteDecision:
    priority: str
    needs_human: bool
    reasons: tuple[str, ...]


def route(category: str, text: str, has_attachments: bool = False) -> RouteDecision:
    text = text.casefold().replace('ё', 'е')
    reasons = ['policy_draft']
    # taxonomy.needs_human_always (account, payment, admin complaints) plus stuck/bug requests;
    # other complaints are only escalated by the signals below.
    human = category in MANDATORY_HUMAN or category == 'report.help'
    if category in MANDATORY_HUMAN:
        reasons.append('mandatory_human')
    urgent = bool(multilingual_sensitive_category(text) or re.search(r'взлом|не могу войти|потер.{0,15}доступ|оплат|платеж|деньги спис|массов.{0,12}баг|угроз.{0,20}(жизн|вне игры)', text))
    appeal = bool(re.search(r'разбан|апелляц|обжал|бан.{0,15}без причин|мут.{0,15}без причин', text))
    if appeal:
        human = True
        reasons.append('appeal_requires_human')
    if category in {'report.account', 'report.payment'} or urgent:
        priority = 'p0'
        human = True
        reasons.append('critical_review')
    # Attachments never change the priority: every launcher complaint carries at least one,
    # so treating them as a signal would put all complaints into p1.
    elif category in {'complaint.cheat', 'complaint.scam', 'complaint.rmt_ads'}:
        priority = 'p1'
    elif category in {'complaint.invalid', 'report.question', 'report.offtopic'}:
        priority = 'p3'
    else:
        priority = 'p2'
    return RouteDecision(priority, human, tuple(reasons))
