import re
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any, Tuple, List
import pdfplumber


@dataclass
class Extraction:
    value: Optional[str]
    page: Optional[int] = None
    snippet: Optional[str] = None
    confidence: float = 0.0
    notes: Optional[str] = None


def normalize_spaces(s: str) -> str:
    return re.sub(r'\s+', ' ', s).strip()

RE_LAST4 = re.compile(r'(?:Card(?:\s+ending\s+in| number| no\.?)|Account(?:\s+ending\s+in)|Acct(?:\.)?|ending|XXX-XXXX-)(?:[:\-]?\s*)?(\d{4})', re.I)
RE_DATE = re.compile(r'(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4})')
RE_DATE_WORD = re.compile(r'([A-Z][a-z]{2,8}\s+\d{1,2},\s*\d{4})')
RE_DUE = re.compile(r'(?:Payment Due Date|Due Date|Payment Due On|Pay By Date)\s*(?:[:\-]?\s*)([A-Za-z0-9 ,\/\-]+)', re.I)
RE_PERIOD = re.compile(r'(?:Statement Period|Billing Period|Statement Date Range|Account Activity)\s*(?:[:\-]?\s*)([A-Za-z0-9 ,\/\-\–to]+)', re.I)
RE_TOTAL_BAL = re.compile(r'(?:Total Amount Due|Total Outstanding|Total Due|New Balance|Amount Due|Balance Due)\s*(?:[:\-]?\s*)(₹?\s*[,\d]+(?:\.\d{2})?)', re.I)
RE_CURRENCY = re.compile(r'₹?\s*[,\d]+(?:\.\d{2})?')

# Issuer keywords
ISSUERS = {
    'pnb': ['pnb', 'punjab national bank'],
    'lena': ['lena', 'bofa', 'bankofamerica'],
    'hdfc': ['hdfc'],
    'sbi': ['sbi', 'state bank of india']
}


def text_from_pdf(pdf_path: str) -> List[str]:
    """Extract text from all pages of the PDF"""
    pages_text = []
    with pdfplumber.open(pdf_path) as pdf:
        for p in pdf.pages:
            text = p.extract_text() or ''
            pages_text.append(text)
    return pages_text


def snippet_around(text: str, match_span: Tuple[int, int], context=40) -> str:
    start = max(0, match_span[0] - context)
    end = min(len(text), match_span[1] + context)
    return normalize_spaces(text[start:end])


def find_issuer(all_text: str) -> Optional[str]:
    lc = all_text.lower()
    for key, tokens in ISSUERS.items():
        for tok in tokens:
            if tok in lc:
                return key
    return None


def extract_last4(pages: List[str]) -> Extraction:
    for i, text in enumerate(pages):
        m = RE_LAST4.search(text)
        if m:
            return Extraction(value=m.group(1), page=i+1, snippet=snippet_around(text, m.span()), confidence=0.95)
    return Extraction(value=None, confidence=0.0, notes="not found")


def extract_due_date(pages: List[str]) -> Extraction:
    for i, text in enumerate(pages):
        m = RE_DUE.search(text)
        if m:
            g = m.group(1)
            d = RE_DATE.search(g) or RE_DATE_WORD.search(g)
            if d:
                return Extraction(value=normalize_spaces(d.group(1)), page=i+1, snippet=snippet_around(text, m.span()), confidence=0.95)
    return Extraction(value=None, confidence=0.0, notes="not found")


def extract_statement_period(pages: List[str]) -> Extraction:
    for i, text in enumerate(pages):
        m = RE_PERIOD.search(text)
        if m:
            return Extraction(value=normalize_spaces(m.group(1)), page=i+1, snippet=snippet_around(text, m.span()), confidence=0.9)
    return Extraction(value=None, confidence=0.0, notes="not found")


def extract_total_balance(pages: List[str]) -> Extraction:
    for i, text in enumerate(pages):
        m = RE_TOTAL_BAL.search(text)
        if m:
            amt = RE_CURRENCY.search(m.group(1))
            if amt:
                return Extraction(value=amt.group(0), page=i+1, snippet=snippet_around(text, m.span()), confidence=0.95)
            else:
                return Extraction(value=normalize_spaces(m.group(1)), page=i+1, snippet=snippet_around(text, m.span()), confidence=0.8)
    return Extraction(value=None, confidence=0.0, notes="not found")


def extract_card_variant(pages: List[str], issuer_hint: Optional[str] = None) -> Extraction:
    if not issuer_hint:
        return Extraction(value=None, confidence=0.0, notes="issuer unknown")
    names = []
    if issuer_hint == 'chase':
        names = ['sapphire', 'freedom', 'ink', 'slate']
    elif issuer_hint == 'amex':
        names = ['platinum', 'gold', 'green', 'blue']
    elif issuer_hint == 'citi':
        names = ['thankyou', 'premier', 'double cash']
    elif issuer_hint == 'boa':
        names = ['cash rewards', 'customized cash']
    elif issuer_hint == 'hsbc':
        names = ['premier', 'advance']
    elif issuer_hint == 'sbi':
        names = ['prime', 'simplyclick', 'elite', 'classic']

    for i, text in enumerate(pages):
        lc = text.lower()
        for nm in names:
            if nm in lc:
                idx = lc.find(nm)
                snippet = normalize_spaces(text[max(0, idx-30): idx+30])
                return Extraction(value=nm.title(), page=i+1, snippet=snippet, confidence=0.85)
    return Extraction(value=None, confidence=0.0, notes="not found")


def parse_pdf(path: str) -> Dict[str, Any]:
    pages = text_from_pdf(path)
    fulltext = "\n".join(pages)
    issuer = find_issuer(fulltext)
    last4 = extract_last4(pages)
    due = extract_due_date(pages)
    period = extract_statement_period(pages)
    total = extract_total_balance(pages)
    variant = extract_card_variant(pages, issuer_hint=issuer)

    return {
        "issuer_hint": issuer,
        "card_last4": asdict(last4),
        "card_variant": asdict(variant),
        "statement_period": asdict(period),
        "payment_due_date": asdict(due),
        "total_balance": asdict(total)
    }

def parse_credit_card_statement(pdf_path: str):
    return parse_pdf(pdf_path)

if __name__ == "__main__":
    data = parse_credit_card_statement("statement/pnb.pdf")
    print(data)

