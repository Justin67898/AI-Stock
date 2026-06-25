from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from xml.etree import ElementTree

import requests
import yfinance as yf

SEC_TICKER_CIK_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_ARCHIVE_DOC_URL = "https://www.sec.gov/Archives/edgar/data/{cik_num}/{accession_no}/{doc_name}"
SEC_HEADERS = {
    "User-Agent": "AI-StockBot/1.0 (contact: local-user@example.com)",
    "Accept-Encoding": "gzip, deflate",
}

_CIK_CACHE: dict[str, str] = {}


def get_historical_data(ticker: str) -> str:
    """
    Return the latest 30 calendar days of OHLCV data for a stock ticker as formatted text.
    
    Includes a system date header so AI systems stay aware of the current timeline.
    """
    now = datetime.now(timezone.utc)
    today_str = now.strftime("%Y-%m-%d %H:%M:%S UTC")
    
    end = now
    start = end - timedelta(days=30)

    history = yf.Ticker(ticker).history(
        start=start.date().isoformat(),
        end=(end + timedelta(days=1)).date().isoformat(),
        interval="1d",
        auto_adjust=False,
    )
    
    lines = [f"--- TODAY'S SYSTEM DATE: {today_str} ---", ""]
    
    if history.empty:
        lines.append(f"No historical data available for {ticker.upper()}")
        return "\n".join(lines)

    lines.append(f"Historical Price Data: {ticker.upper()}")
    lines.append("=" * 80)
    
    history = history.reset_index()
    for _, row in history.iterrows():
        date_str = row["Date"].strftime("%Y-%m-%d")
        open_price = float(row["Open"])
        high_price = float(row["High"])
        low_price = float(row["Low"])
        close_price = float(row["Close"])
        volume = int(row["Volume"])
        
        lines.append(
            f"{date_str} | O: ${open_price:>8.2f} | H: ${high_price:>8.2f} | "
            f"L: ${low_price:>8.2f} | C: ${close_price:>8.2f} | Vol: {volume:>12,}"
        )
    
    return "\n".join(lines)


def get_stock_news(ticker: str) -> list[dict[str, Any]]:
    """Return recent news items for a stock ticker from yfinance."""
    articles = yf.Ticker(ticker).news or []
    results: list[dict[str, Any]] = []

    for article in articles:
        publish_time = article.get("providerPublishTime")
        published_at = (
            datetime.fromtimestamp(publish_time, tz=timezone.utc).isoformat()
            if isinstance(publish_time, (int, float))
            else None
        )
        results.append(
            {
                "title": article.get("title"),
                "publisher": article.get("publisher"),
                "link": article.get("link") or article.get("url"),
                "published_at": published_at,
                "type": article.get("type"),
            }
        )

    return results


def get_insider_trading(ticker: str) -> list[dict[str, Any]]:
    """Fetch recent SEC Form 4 insider transactions for the given ticker."""
    cik = _resolve_cik_from_ticker(ticker)
    submissions = requests.get(
        SEC_SUBMISSIONS_URL.format(cik=cik), headers=SEC_HEADERS, timeout=15
    )
    submissions.raise_for_status()
    filings = submissions.json().get("filings", {}).get("recent", {})

    forms = filings.get("form", [])
    accession_numbers = filings.get("accessionNumber", [])
    filing_dates = filings.get("filingDate", [])
    primary_docs = filings.get("primaryDocument", [])

    transactions: list[dict[str, Any]] = []
    form4_indices = [i for i, form in enumerate(forms) if str(form).upper().startswith("4")]

    for idx in form4_indices[:5]:
        accession_number = str(accession_numbers[idx])
        accession_clean = accession_number.replace("-", "")
        filing_date = filing_dates[idx] if idx < len(filing_dates) else None
        doc_name = primary_docs[idx] if idx < len(primary_docs) else None
        if not doc_name:
            continue

        doc_url = SEC_ARCHIVE_DOC_URL.format(
            cik_num=str(int(cik)),
            accession_no=accession_clean,
            doc_name=doc_name,
        )
        doc_response = requests.get(doc_url, headers=SEC_HEADERS, timeout=15)
        if doc_response.status_code != 200 or not doc_name.lower().endswith(".xml"):
            transactions.append(
                {
                    "ticker": ticker.upper(),
                    "filing_date": filing_date,
                    "accession_number": accession_number,
                    "form": "4",
                    "source_url": doc_url,
                }
            )
            continue

        try:
            root = ElementTree.fromstring(doc_response.text)
        except ElementTree.ParseError:
            transactions.append(
                {
                    "ticker": ticker.upper(),
                    "filing_date": filing_date,
                    "accession_number": accession_number,
                    "form": "4",
                    "source_url": doc_url,
                }
            )
            continue

        owner_name = _xml_text(root, ".//reportingOwnerId/rptOwnerName")
        non_derivative_transactions = root.findall(".//nonDerivativeTransaction")

        if not non_derivative_transactions:
            transactions.append(
                {
                    "ticker": ticker.upper(),
                    "insider_name": owner_name,
                    "filing_date": filing_date,
                    "accession_number": accession_number,
                    "form": "4",
                    "source_url": doc_url,
                }
            )
            continue

        for trade in non_derivative_transactions:
            transactions.append(
                {
                    "ticker": ticker.upper(),
                    "insider_name": owner_name,
                    "filing_date": filing_date,
                    "accession_number": accession_number,
                    "security_title": _xml_text(trade, ".//securityTitle/value"),
                    "transaction_date": _xml_text(trade, ".//transactionDate/value"),
                    "transaction_code": _xml_text(trade, ".//transactionCoding/transactionCode"),
                    "transaction_type": _xml_text(
                        trade, ".//transactionAmounts/transactionAcquiredDisposedCode/value"
                    ),
                    "shares": _xml_text(trade, ".//transactionAmounts/transactionShares/value"),
                    "price_per_share": _xml_text(
                        trade, ".//transactionAmounts/transactionPricePerShare/value"
                    ),
                    "shares_after_transaction": _xml_text(
                        trade, ".//postTransactionAmounts/sharesOwnedFollowingTransaction/value"
                    ),
                    "source_url": doc_url,
                }
            )

    return transactions


def check_market_jumps() -> list[dict[str, Any]]:
    """
    Scan tracked stocks and print an alert if 15-minute move exceeds +/-3%.

    Returns matching alerts with prices and percent move.
    """
    tracked = ["AAPL", "NVDA", "TSLA"]
    alerts: list[dict[str, Any]] = []

    for ticker in tracked:
        history = yf.Ticker(ticker).history(period="1d", interval="1m")
        if history.empty:
            continue

        history = history.dropna(subset=["Close"])
        if len(history) < 16:
            continue

        last_ts = history.index[-1]
        reference_ts = last_ts - timedelta(minutes=15)
        prior_window = history[history.index <= reference_ts]
        if prior_window.empty:
            continue

        start_price = float(prior_window["Close"].iloc[-1])
        end_price = float(history["Close"].iloc[-1])
        if start_price <= 0:
            continue

        percent_change = ((end_price - start_price) / start_price) * 100.0
        if abs(percent_change) < 3.0:
            continue

        alert_message = (
            f"ALERT: {ticker} moved {percent_change:.2f}% in the last 15 minutes "
            f"({start_price:.2f} -> {end_price:.2f})"
        )
        print(alert_message)
        alerts.append(
            {
                "ticker": ticker,
                "start_price": start_price,
                "end_price": end_price,
                "percent_change": round(percent_change, 4),
                "alert": alert_message,
            }
        )

    return alerts


def _resolve_cik_from_ticker(ticker: str) -> str:
    ticker_upper = ticker.upper()
    if ticker_upper in _CIK_CACHE:
        return _CIK_CACHE[ticker_upper]

    response = requests.get(SEC_TICKER_CIK_URL, headers=SEC_HEADERS, timeout=15)
    response.raise_for_status()
    companies = response.json()

    for company in companies.values():
        if str(company.get("ticker", "")).upper() == ticker_upper:
            cik = str(company["cik_str"]).zfill(10)
            _CIK_CACHE[ticker_upper] = cik
            return cik

    raise ValueError(f"Could not find SEC CIK for ticker: {ticker}")


def _xml_text(node: ElementTree.Element, path: str) -> str | None:
    found = node.find(path)
    if found is None or found.text is None:
        return None
    return found.text.strip()


def analyze_asset(ticker: str) -> dict[str, Any]:
    """
    Combine historical data, news, and insider trading into a single structured dataset.

    Returns a dict with keys: ticker, historical_data, news, insider_trading.
    Includes error information if individual data fetches fail.
    """
    result: dict[str, Any] = {"ticker": ticker.upper()}

    try:
        result["historical_data"] = get_historical_data(ticker)
    except Exception as e:
        result["historical_data"] = {"error": str(e)}

    try:
        result["news"] = get_stock_news(ticker)
    except Exception as e:
        result["news"] = {"error": str(e)}

    try:
        result["insider_trading"] = get_insider_trading(ticker)
    except Exception as e:
        result["insider_trading"] = {"error": str(e)}

    return result
