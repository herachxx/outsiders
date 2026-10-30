"""History annotation does not prove spam or alter sanctions/priority."""
def annotate_history(result, request, history, ticket_id, timestamp):
    count = history.observe(request, ticket_id, timestamp)
    if count is None:
        return result
    result['reasons'] = [r for r in result['reasons'] if r != 'history_unavailable']
    result['reasons'].append('history_exact_match_only')
    result['is_spam_or_duplicate'] = count >= 2
    if count >= 2:
        result['reasons'].append('duplicate_exact')
    if count >= 5:
        result['reasons'].append('five_tickets_within_hour')
        result['needs_human'] = True
    return result
