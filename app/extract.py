"""Facts read straight from the player text: accused nickname, game server, rule point written in the message."""
import re


# Rule point named inside the message: "2.1 оп", "5.2 ОП", "пункт 4.1", "п. 2.4".
TEXT_REF = r"(?<![\d.])(\d{1,2}\.\d{1,2}(?:\.\d{1,2})?)(?![\d.])(?=\s*(?:оп\b|op\b|гз\b|gz\b|ппо))|(?<=пункт )(\d{1,2}\.\d{1,2}(?:\.\d{1,2})?)|(?<=п\. )(\d{1,2}\.\d{1,2}(?:\.\d{1,2})?)"


def extract_nickname(text: str) -> str | None:
    """First Nick_Name-looking token of the player text (accused player named in the message)."""
    match = re.search(r"(?<![A-Za-z0-9_])[A-Z][A-Za-z]{1,19}_[A-Z][A-Za-z]{1,19}\d{0,3}(?![A-Za-z0-9_])", text)
    return match.group(0) if match else None


def extract_server(text: str) -> str | None:
    """Game server number named in the text ("19 сервер", "сервер 17", "на 12-м сервере"); None if absent."""
    match = re.search(r"(?<!\d)(\d{1,3})\s*-?\s*(?:й|м|го|ом)?\s*(?:сервер|server)(?:е|а|у|ом)?(?![а-я])|(?:сервер|server)(?:е|а|у|ом)?(?![а-я])\s*(?:№|#|номер)?\s*(\d{1,3})(?!\d)", text)
    return next((g for g in match.groups() if g), None) if match else None
