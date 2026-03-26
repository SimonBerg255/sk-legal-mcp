import asyncio

import httpx
from bs4 import BeautifulSoup


# ─────────────────────────────────────────────────────────────────────
# 1. Slovak Supreme Court (Najvyssi sud) — REST API at nsud.sk
# ─────────────────────────────────────────────────────────────────────

SUPREME_COURT_API = "https://www.nsud.sk/ws/opendata.php"
SUPREME_COURT_TIMEOUT = 60
SUPREME_COURT_HEADERS = {"User-Agent": "SlovakLegalMCP/1.0 (Open Data Research)"}

KOLEGIUM_MAP = {
    "1": "Civil",
    "2": "Commercial",
    "3": "Administrative",
    "4": "Criminal",
}


async def _fetch_decision(client: httpx.AsyncClient, decision_id: str) -> dict:
    """Fetch a single decision by ID. Injects the original ID since the API returns ID=''."""
    params = {"getDecision": "", "id": decision_id}
    resp = await client.get(
        SUPREME_COURT_API, params=params, headers=SUPREME_COURT_HEADERS
    )
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict):
        # The API returns "ID": "" — inject the known working ID
        data["_decision_id"] = decision_id
    return data


async def search_supreme_court(
    query: str = "",
    ecli: str = "",
    date_from: str = "",
    date_to: str = "",
    subject: str = "",
) -> list[dict]:
    """
    Search Slovak Supreme Court decisions via the nsud.sk OpenData API.

    Use this tool to find court rulings, case law, and judicial decisions
    from Slovakia's highest court. Supports searching by keywords in the
    decision text, ECLI identifier, date range, or subject matter.

    Over 104,000 decisions are available covering civil, commercial,
    administrative, and criminal law.

    Args:
        query: Natural language search keywords (searches decision content).
               Example: "ochrana osobnych udajov" or "restitucny narok"
        ecli: European Case Law Identifier to search for. Example: "ECLI:SK:NSSR:2023:..."
        date_from: Start date filter in YYYY-MM-DD format. Example: "2023-01-01"
        date_to: End date filter in YYYY-MM-DD format. Example: "2023-12-31"
        subject: Subject matter / merito keywords. Example: "nahrady skody"

    Returns:
        A list of matching court decisions with title, date, case number,
        court division, ECLI, URL, and text excerpt.
    """
    # The nsud.sk API uses the function name as a parameter key (not "fnc=")
    params: dict[str, str] = {"searchDecision": ""}
    if query:
        params["art_obsah"] = query
    if ecli:
        params["art_ecli"] = ecli
    if date_from:
        params["art_datum_od"] = date_from
    if date_to:
        params["art_datum_do"] = date_to
    if subject:
        params["art_merito"] = subject

    async with httpx.AsyncClient(timeout=SUPREME_COURT_TIMEOUT) as client:
        resp = await client.get(
            SUPREME_COURT_API, params=params, headers=SUPREME_COURT_HEADERS
        )
        resp.raise_for_status()
        data = resp.json()

    if not data:
        return [{"message": "No decisions found for the given criteria."}]

    # searchDecision returns a list of decision IDs (strings)
    ids = data if isinstance(data, list) else [data]

    # Fetch details for up to 10 decisions
    ids_to_fetch = ids[:10]

    async with httpx.AsyncClient(timeout=SUPREME_COURT_TIMEOUT) as client:
        tasks = [_fetch_decision(client, str(did)) for did in ids_to_fetch]
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

    results = []
    for item in raw_results:
        if isinstance(item, Exception):
            continue
        if not item:
            continue

        # Use _decision_id (injected by _fetch_decision) since API returns ID=""
        decision_id = item.get("_decision_id", "") or item.get("ID", "")
        text = item.get("obsah", "")
        excerpt = text[:500] + "..." if len(text) > 500 else text

        results.append({
            "id": decision_id,
            "title": item.get("cislo", ""),
            "date": item.get("datum", ""),
            "ecli": item.get("ecli", ""),
            "division": KOLEGIUM_MAP.get(
                item.get("kolegium", ""), item.get("kolegium", "")
            ),
            "senate": item.get("senat", ""),
            "judge": item.get("sudca", ""),
            "subject": item.get("merito", ""),
            "url": f"https://www.nsud.sk/rozhodnutia/{decision_id}/",
            "text_excerpt": excerpt,
        })

    total = len(ids)
    if total > 10:
        results.append({
            "note": f"Showing 10 of {total} total results. Refine your search or use date filters to narrow down."
        })

    return results if results else [{"message": "No decisions found for the given criteria."}]


async def get_supreme_court_decision(decision_id: str) -> dict:
    """
    Retrieve the full text of a specific Slovak Supreme Court decision by its ID.

    Use this after searching to get the complete text of a decision.

    Args:
        decision_id: The numeric ID of the decision. Example: "245188"

    Returns:
        The full decision including title, date, ECLI, division, full text, and URL.
    """
    params = {"getDecision": "", "id": decision_id}

    async with httpx.AsyncClient(timeout=SUPREME_COURT_TIMEOUT) as client:
        resp = await client.get(
            SUPREME_COURT_API, params=params, headers=SUPREME_COURT_HEADERS
        )
        resp.raise_for_status()
        data = resp.json()

    if not data:
        return {"error": f"Decision with ID {decision_id} not found."}

    item = data

    full_text = item.get("obsah", "")
    if not full_text:
        return {"error": f"Decision with ID {decision_id} not found."}

    return {
        "id": decision_id,
        "title": item.get("cislo", ""),
        "date": item.get("datum", ""),
        "ecli": item.get("ecli", ""),
        "division": KOLEGIUM_MAP.get(
            item.get("kolegium", ""), item.get("kolegium", "")
        ),
        "senate": item.get("senat", ""),
        "judge": item.get("sudca", ""),
        "subject": item.get("merito", ""),
        "url": f"https://www.nsud.sk/rozhodnutia/{decision_id}/",
        "full_text": full_text,
    }


async def get_recent_supreme_court_decisions(since_date: str) -> list[dict]:
    """
    Get Supreme Court decision IDs published since a given date.

    Useful for tracking new rulings and staying up to date with case law.
    Returns IDs that can be passed to get_supreme_court_decision for full text.

    Args:
        since_date: Date in YYYY-MM-DD format. Returns decisions from this date onward.
                    Example: "2026-03-01"

    Returns:
        A list of recent decision IDs. Use get_supreme_court_decision to fetch details.
    """
    params = {"getLastDecision": "", "date": since_date}

    async with httpx.AsyncClient(timeout=SUPREME_COURT_TIMEOUT) as client:
        resp = await client.get(
            SUPREME_COURT_API, params=params, headers=SUPREME_COURT_HEADERS
        )
        resp.raise_for_status()
        data = resp.json()

    if not data:
        return [{"message": f"No decisions found since {since_date}."}]

    ids = data if isinstance(data, list) else [data]

    # Fetch details for up to 15 decisions
    ids_to_fetch = ids[:15]

    async with httpx.AsyncClient(timeout=SUPREME_COURT_TIMEOUT) as client:
        tasks = [_fetch_decision(client, str(did)) for did in ids_to_fetch]
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

    results = []
    for item in raw_results:
        if isinstance(item, Exception):
            continue
        if not item:
            continue
        decision_id = item.get("_decision_id", "") or item.get("ID", "")
        results.append({
            "id": decision_id,
            "title": item.get("cislo", ""),
            "date": item.get("datum", ""),
            "ecli": item.get("ecli", ""),
            "division": KOLEGIUM_MAP.get(
                item.get("kolegium", ""), item.get("kolegium", "")
            ),
            "subject": item.get("merito", ""),
        })

    total = len(ids)
    if total > 15:
        results.append({
            "note": f"Showing 15 of {total} total results since {since_date}."
        })

    return results if results else [{"message": f"No decisions found since {since_date}."}]


# ─────────────────────────────────────────────────────────────────────
# 2. Slovak Collection of Laws (Zbierka zakonov) — static.slov-lex.sk
# ─────────────────────────────────────────────────────────────────────

SLOVLEX_BASE = "https://static.slov-lex.sk"
SLOVLEX_TIMEOUT = 20


async def search_slovak_legislation(
    query: str = "",
    year: int = 0,
    doc_type: str = "",
) -> list[dict]:
    """
    Search Slovak legislation from the Collection of Laws (Zbierka zakonov).

    Searches the official Slov-Lex legislative portal for Slovak laws, decrees,
    regulations, and other legislative documents from 1918 to present.

    Args:
        query: Search keywords in the legislation title or content.
               Example: "ochrana osobnych udajov" or "stavebny zakon"
        year: Filter by year of publication. Example: 2024
        doc_type: Filter by document type. Options include:
                  "Zakon" (law), "Nariadenie vlady" (government regulation),
                  "Vyhlaska" (decree), "Oznamenie" (notice),
                  "Ustavny zakon" (constitutional act)

    Returns:
        A list of matching legislative documents with title, document type,
        year, number, effective date, and URL.
    """
    if year == 0:
        year = 2025

    url = f"{SLOVLEX_BASE}/static/SK/ZZ/{year}/"

    try:
        async with httpx.AsyncClient(timeout=SLOVLEX_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            html = resp.text
    except httpx.HTTPStatusError:
        return [{"message": f"No legislation found for year {year}. Year may not exist in the database."}]

    soup = BeautifulSoup(html, "html.parser")
    links = soup.find_all("a", href=True)

    results = []
    query_lower = query.lower() if query else ""
    doc_type_lower = doc_type.lower() if doc_type else ""

    for link in links:
        href = link.get("href", "")
        text = link.get_text(strip=True)

        if not text or not href or href == "../":
            continue

        # The index page typically lists law numbers linking to subdirectories
        number_str = href.strip("/")
        if not number_str.isdigit():
            continue

        law_number = int(number_str)
        title = text

        if query_lower and query_lower not in title.lower():
            continue

        if doc_type_lower and doc_type_lower not in title.lower():
            continue

        results.append({
            "year": year,
            "number": law_number,
            "title": title,
            "url": f"https://www.slov-lex.sk/pravne-predpisy/SK/ZZ/{year}/{law_number}/",
            "static_url": f"{SLOVLEX_BASE}/static/SK/ZZ/{year}/{law_number}/",
        })

    if not results:
        return [{"message": f"No legislation found for year={year}, query='{query}'."}]

    return results[:30]


async def get_slovak_law(year: int, number: int) -> dict:
    """
    Retrieve the full text of a specific Slovak law by its year and number.

    Use this to get the complete text of a law from the Collection of Laws.

    Args:
        year: The year of publication. Example: 2024
        number: The law number. Example: 18 (for Act No. 18/2018 on Personal Data Protection)

    Returns:
        The full legislative text with title, effective date, and source URL.
    """
    version_url = f"{SLOVLEX_BASE}/static/SK/ZZ/{year}/{number}/"

    try:
        async with httpx.AsyncClient(timeout=SLOVLEX_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(version_url)
            resp.raise_for_status()
            html = resp.text
    except httpx.HTTPStatusError:
        return {"error": f"Law {number}/{year} not found. Check the year and number."}

    soup = BeautifulSoup(html, "html.parser")
    links = soup.find_all("a", href=True)

    # Only pick .html files that are direct children (not cross-references like ../../../ZZ/...)
    html_links = []
    for link in links:
        href = link.get("href", "")
        if href.endswith(".html") and "/" not in href:
            html_links.append(href)

    if not html_links:
        return {"error": f"No text found for law {number}/{year}."}

    latest = sorted(html_links)[-1]
    text_url = f"{SLOVLEX_BASE}/static/SK/ZZ/{year}/{number}/{latest}"

    try:
        async with httpx.AsyncClient(timeout=SLOVLEX_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(text_url)
            resp.raise_for_status()
            text_html = resp.text
    except httpx.HTTPStatusError:
        return {"error": f"Could not fetch text for law {number}/{year}."}

    text_soup = BeautifulSoup(text_html, "html.parser")

    for tag in text_soup(["script", "style", "nav", "header", "footer"]):
        tag.decompose()

    full_text = text_soup.get_text(separator="\n", strip=True)

    if len(full_text) > 15000:
        full_text = full_text[:15000] + "\n\n[... text truncated — full version available at the URL below ...]"

    return {
        "year": year,
        "number": number,
        "version": latest.replace(".html", ""),
        "text": full_text,
        "url": f"https://www.slov-lex.sk/pravne-predpisy/SK/ZZ/{year}/{number}/",
        "static_url": text_url,
    }


async def list_legislation_years() -> list[dict]:
    """
    List all available years in the Slovak Collection of Laws.

    Use this to discover which years of legislation are available,
    from 1918 to the present.

    Returns:
        A list of available years with links to their legislation indexes.
    """
    url = f"{SLOVLEX_BASE}/static/SK/ZZ/"

    async with httpx.AsyncClient(timeout=SLOVLEX_TIMEOUT, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        html = resp.text

    soup = BeautifulSoup(html, "html.parser")

    # Years are in <li class="singleYear"> elements with hrefs like /static/SK/ZZ/1918/
    years = []
    for li in soup.find_all("li", class_="singleYear"):
        year_link = li.find("a", href=True)
        if year_link:
            text = year_link.get_text(strip=True)
            if text.isdigit() and len(text) == 4:
                years.append({
                    "year": int(text),
                    "url": f"{SLOVLEX_BASE}/static/SK/ZZ/{text}/",
                })

    return sorted(years, key=lambda x: x["year"], reverse=True)


# ─────────────────────────────────────────────────────────────────────
# 3. Slovak Data Protection Authority (UOOU) — dataprotection.gov.sk
# ─────────────────────────────────────────────────────────────────────

UOOU_BASE = "https://dataprotection.gov.sk"
UOOU_TIMEOUT = 20


async def search_data_protection_guidelines(
    query: str = "",
    category: str = "",
) -> list[dict]:
    """
    Search guidelines and methodological documents from the Slovak Data
    Protection Authority (Urad na ochranu osobnych udajov).

    Covers GDPR guidelines, methodological instructions, EDPB guidance
    translations, and opinions on personal data protection in Slovakia.

    Args:
        query: Search keywords. Example: "kamerove zariadenia" or "GDPR cookies"
        category: Filter by category. Options:
                  "office_guideline" - Office methodological guidelines
                  "edpb" - EDPB guidance translations
                  "annual_report" - Annual reports

    Returns:
        A list of matching guidelines with title, category, date, and URL.
    """
    # Each source page and the path prefix for its actual guideline links
    source_pages = [
        {
            "url": f"{UOOU_BASE}/en/legislation/guidelines-faq/office-guidelines/",
            "prefix": "/en/legislation/guidelines-faq/office-guidelines/",
            "cat": "office_guideline",
        },
        {
            "url": f"{UOOU_BASE}/en/legislation/guidelines-faq/edpb-guidelines/",
            "prefix": "/en/legislation/guidelines-faq/edpb-guidelines/",
            "cat": "edpb",
        },
    ]

    if category == "office_guideline":
        source_pages = [source_pages[0]]
    elif category == "edpb":
        source_pages = [source_pages[1]]

    results = []
    query_lower = query.lower() if query else ""

    async with httpx.AsyncClient(timeout=UOOU_TIMEOUT, follow_redirects=True) as client:
        for source in source_pages:
            try:
                resp = await client.get(source["url"])
                resp.raise_for_status()
                html = resp.text
            except Exception:
                continue

            soup = BeautifulSoup(html, "html.parser")

            for link in soup.find_all("a", href=True):
                href = link.get("href", "")
                text = link.get_text(strip=True)

                if not text or len(text) < 15:
                    continue

                # Only accept links that are actual sub-pages of this guideline section
                # e.g. /en/legislation/guidelines-faq/office-guidelines/some-guideline/
                if not href.startswith(source["prefix"]):
                    continue

                # Skip the section index page itself
                if href.rstrip("/") == source["prefix"].rstrip("/"):
                    continue

                if query_lower and query_lower not in text.lower():
                    continue

                full_url = f"{UOOU_BASE}{href}"

                results.append({
                    "title": text,
                    "category": source["cat"],
                    "url": full_url,
                })

    # Also try the Slovak version for more content
    sk_urls = [
        f"{UOOU_BASE}/uoou/sk/hlavna-stranka/metodicke-usmernenia/",
    ]

    async with httpx.AsyncClient(timeout=UOOU_TIMEOUT, follow_redirects=True) as client:
        for page_url in sk_urls:
            try:
                resp = await client.get(page_url)
                resp.raise_for_status()
                html = resp.text
            except Exception:
                continue

            soup = BeautifulSoup(html, "html.parser")

            for link in soup.find_all("a", href=True):
                href = link.get("href", "")
                text = link.get_text(strip=True)

                if not text or len(text) < 10:
                    continue

                if query_lower and query_lower not in text.lower():
                    continue

                if href.endswith(".pdf") or "metodick" in href.lower():
                    full_url = href if href.startswith("http") else f"{UOOU_BASE}{href}"
                    results.append({
                        "title": text,
                        "category": "office_guideline",
                        "url": full_url,
                        "language": "sk",
                    })

    if not results:
        return [{"message": f"No guidelines found matching '{query}'."}]

    # Deduplicate by URL
    seen = set()
    unique_results = []
    for r in results:
        if r["url"] not in seen:
            seen.add(r["url"])
            unique_results.append(r)

    return unique_results[:30]


async def get_data_protection_document(url: str) -> dict:
    """
    Retrieve the full text of a specific document from the Slovak Data
    Protection Authority website.

    Use this after searching to read the full content of a guideline,
    opinion, or methodological document.

    Args:
        url: The URL of the document page. Must be from dataprotection.gov.sk.
             Example: "https://dataprotection.gov.sk/en/legislation/guidelines-faq/office-guidelines/methodological-guideline-1-2023..."

    Returns:
        The extracted text content of the document with its title and source URL.
    """
    if "dataprotection.gov.sk" not in url:
        return {"error": "URL must be from dataprotection.gov.sk"}

    async with httpx.AsyncClient(timeout=UOOU_TIMEOUT, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        html = resp.text

    soup = BeautifulSoup(html, "html.parser")

    title_tag = soup.find("h1") or soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else "Unknown"

    for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
        tag.decompose()

    main = soup.find("main") or soup.find("article") or soup.find("div", class_="content") or soup

    full_text = main.get_text(separator="\n", strip=True)

    if len(full_text) > 15000:
        full_text = full_text[:15000] + "\n\n[... text truncated — full version available at the URL below ...]"

    pdf_links = []
    for link in soup.find_all("a", href=True):
        href = link.get("href", "").strip()
        # Clean whitespace/newlines from href
        href = "".join(href.split())
        if href.endswith(".pdf"):
            full_href = href if href.startswith("http") else f"{UOOU_BASE}{href}"
            pdf_links.append(full_href)

    return {
        "title": title,
        "text": full_text,
        "url": url,
        "pdf_attachments": pdf_links,
        "note": "Most UOOU guidelines are published as PDF attachments. Check pdf_attachments for download links." if pdf_links else "",
    }
