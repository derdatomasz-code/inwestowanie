from __future__ import annotations

from datetime import datetime
from io import StringIO
import math

import pandas as pd
import streamlit as st
import yfinance as yf

st.set_page_config(page_title="Income Investor AI", page_icon="📈", layout="wide")

DEFAULT_WATCHLIST = [
    {"ticker": "VWRL.L", "name": "Vanguard FTSE All-World UCITS ETF (distributing)", "type": "ETF"},
    {"ticker": "VWCE.DE", "name": "Vanguard FTSE All-World UCITS ETF (accumulating)", "type": "ETF"},
    {"ticker": "VHYL.L", "name": "Vanguard FTSE All-World High Dividend Yield UCITS ETF", "type": "ETF"},
    {"ticker": "ISPA.DE", "name": "iShares STOXX Global Select Dividend 100 UCITS ETF", "type": "ETF"},
    {"ticker": "KO", "name": "Coca-Cola", "type": "Akcja"},
    {"ticker": "JNJ", "name": "Johnson & Johnson", "type": "Akcja"},
    {"ticker": "PG", "name": "Procter & Gamble", "type": "Akcja"},
    {"ticker": "PEP", "name": "PepsiCo", "type": "Akcja"},
    {"ticker": "MSFT", "name": "Microsoft", "type": "Akcja"},
    {"ticker": "NESN.SW", "name": "Nestlé", "type": "Akcja"},
]
SAMPLE_PORTFOLIO = """ticker,units,avg_buy_price,currency
VWCE.DE,10,120,EUR
KO,5,60,USD
"""

st.title("📈 Income Investor AI")
st.caption("MVP 0.1 · Budowanie kapitału i reinwestowanie dywidend · dostęp z iPada")

st.info(
    "To prototyp edukacyjny, nie porada inwestycyjna. Dane z Yahoo Finance przez yfinance mogą być "
    "opóźnione, niekompletne lub błędne. Nie składaj zleceń na podstawie samego rankingu. "
    "Agent nie łączy się z kontem XTB i nie wykonuje transakcji."
)

with st.sidebar:
    st.header("Ustawienia")
    tickers_text = st.text_area(
        "Tickery do monitorowania (po jednym w wierszu)",
        value="\n".join(x["ticker"] for x in DEFAULT_WATCHLIST),
        height=220,
        help="Sprawdź symbol i giełdę w źródle danych oraz w XTB. To przykładowa lista, nie rekomendacja."
    )
    max_tickers = st.slider("Maksymalna liczba instrumentów w analizie", 3, 30, 10)
    st.caption("MVP pobiera dane na żądanie. Nie działa jeszcze automatycznie w tle.")

tab_today, tab_portfolio, tab_method, tab_sources = st.tabs(
    ["Briefing", "Portfel XTB", "Metodyka i ryzyko", "Źródła i ograniczenia"]
)

def safe_num(value):
    try:
        if value is None or pd.isna(value):
            return None
        val = float(value)
        if math.isfinite(val):
            return val
    except Exception:
        return None
    return None

@st.cache_data(ttl=3600, show_spinner=False)
def get_instrument_data(ticker: str):
    obj = yf.Ticker(ticker)
    hist = obj.history(period="2y", interval="1d", auto_adjust=True)
    info = {}
    try:
        info = obj.info or {}
    except Exception:
        info = {}
    if hist.empty or "Close" not in hist:
        return None
    close = hist["Close"].dropna()
    if len(close) < 30:
        return None
    last = safe_num(close.iloc[-1])
    if last is None:
        return None
    def ret(days):
        if len(close) <= days:
            return None
        old = safe_num(close.iloc[-days-1])
        return ((last / old) - 1) * 100 if old else None
    daily = close.pct_change().dropna()
    vol = safe_num(daily.tail(252).std() * (252 ** 0.5) * 100) if len(daily) >= 20 else None
    peak = close.cummax()
    dd = safe_num((close / peak - 1).tail(252).min() * 100)
    div_yield = safe_num(info.get("dividendYield"))
    if div_yield is not None and div_yield <= 1.5:
        div_yield_pct = div_yield * 100
    else:
        div_yield_pct = div_yield
    annual_div = safe_num(info.get("dividendRate"))
    currency = info.get("currency", "")
    name = info.get("shortName") or info.get("longName") or ticker
    exchange = info.get("exchange", "")
    sma50 = safe_num(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else None
    sma200 = safe_num(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else None
    return {
        "ticker": ticker,
        "name": name,
        "exchange": exchange,
        "currency": currency,
        "price": last,
        "date": str(close.index[-1].date()),
        "return_3m": ret(63),
        "return_6m": ret(126),
        "return_12m": ret(252),
        "dividend_yield": div_yield_pct,
        "annual_dividend": annual_div,
        "volatility": vol,
        "max_drawdown": dd,
        "sma50": sma50,
        "sma200": sma200,
        "source": "Yahoo Finance / yfinance",
    }

def pct(x, digits=2):
    return "—" if x is None else f"{x:.{digits}f}%"

def money(x, currency=""):
    if x is None:
        return "—"
    return f"{x:,.2f} {currency}".strip()

def preliminary_status(row):
    # Simple filter only; never a buy/sell instruction.
    y = row.get("dividend_yield")
    r6 = row.get("return_6m")
    price = row.get("price")
    sma200 = row.get("sma200")
    if y is not None and y > 8:
        return "Sprawdź ryzyko wysokiej stopy wypłaty"
    if r6 is not None and r6 < -15:
        return "Sprawdź przyczynę spadku"
    if sma200 is not None and price is not None and price > sma200 and r6 is not None and r6 > 0:
        return "Pozytywne momentum — sprawdź fundamenty"
    return "Obserwuj — brak jednoznacznego sygnału"

with tab_today:
    st.subheader("Briefing dzienny")
    st.write(
        "W MVP raport powstaje po kliknięciu przycisku. Po weryfikacji danych dodamy automatyczny harmonogram, "
        "AI do syntezy informacji i alerty Telegram."
    )
    run = st.button("🔄 Pobierz dane i wygeneruj briefing", type="primary", use_container_width=True)
    if run:
        tickers = list(dict.fromkeys(
            x.strip().upper() for x in tickers_text.splitlines() if x.strip()
        ))[:max_tickers]
        results = []
        with st.spinner(f"Pobieram dane dla {len(tickers)} instrumentów..."):
            progress = st.progress(0)
            for i, ticker in enumerate(tickers, start=1):
                try:
                    result = get_instrument_data(ticker)
                    if result:
                        result["status"] = preliminary_status(result)
                        results.append(result)
                except Exception:
                    pass
                progress.progress(i / len(tickers))
        if not results:
            st.error("Nie udało się pobrać danych. Sprawdź internet, tickery i spróbuj ponownie.")
        else:
            df = pd.DataFrame(results)
            st.session_state["latest_df"] = df
            st.session_state["generated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    if "latest_df" in st.session_state:
        df = st.session_state["latest_df"].copy()
        st.caption(f"Ostatni raport wygenerowano: {st.session_state.get('generated_at', '—')}")
        c1, c2, c3 = st.columns(3)
        c1.metric("Instrumenty z danymi", len(df))
        c2.metric("Z dodatnią stopą 6M", int((df["return_6m"].fillna(-999) > 0).sum()))
        c3.metric("Do sprawdzenia", int(df["status"].str.contains("Sprawdź", na=False).sum()))
        st.subheader("Najważniejsze do sprawdzenia")
        st.dataframe(
            df[["ticker", "name", "price", "currency", "dividend_yield", "return_6m", "volatility", "max_drawdown", "status"]]
            .rename(columns={
                "ticker":"Ticker", "name":"Instrument", "price":"Cena", "currency":"Waluta",
                "dividend_yield":"Stopa dywidendy* %", "return_6m":"Zwrot 6M %", "volatility":"Zmienność roczna %", 
                "max_drawdown":"Maks. obsunięcie 1Y %", "status":"Wstępny status"
            }),
            use_container_width=True, hide_index=True
        )
        st.caption("*Stopa dywidendy z publicznego źródła może być nieaktualna lub liczona według innej metodologii. Nie traktuj jej jako prognozy.")
        st.download_button(
            "Pobierz raport CSV",
            df.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"briefing_inwestycyjny_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
            use_container_width=True,
        )
    else:
        st.warning("Kliknij „Pobierz dane”, aby wygenerować pierwszy raport.")

with tab_portfolio:
    st.subheader("Portfel XTB — import CSV")
    st.write(
        "XTB nie udostępnia już API. W tej wersji wczytujesz ręcznie eksportowany plik lub przygotowany przez siebie CSV. "
        "Nie wpisuj haseł ani danych logowania do XTB."
    )
    st.download_button(
        "Pobierz przykładowy szablon CSV",
        SAMPLE_PORTFOLIO.encode("utf-8"),
        file_name="portfel_szablon.csv",
        mime="text/csv",
    )
    uploaded = st.file_uploader("Wczytaj CSV portfela", type=["csv"])
    if uploaded:
        try:
            pf = pd.read_csv(uploaded)
            required = {"ticker", "units", "avg_buy_price", "currency"}
            if not required.issubset(set(pf.columns)):
                st.error("CSV musi zawierać kolumny: ticker, units, avg_buy_price, currency.")
            else:
                pf["ticker"] = pf["ticker"].astype(str).str.upper().str.strip()
                pf["units"] = pd.to_numeric(pf["units"], errors="coerce")
                pf["avg_buy_price"] = pd.to_numeric(pf["avg_buy_price"], errors="coerce")
                st.write("Zaimportowane pozycje:")
                st.dataframe(pf, use_container_width=True, hide_index=True)
                st.info(
                    "Kolejny etap: połączenie pozycji z aktualnymi cenami i obliczanie wartości oraz zysku/straty. "
                    "W MVP nie przeliczamy jeszcze walut ani podatków."
                )
        except Exception as exc:
            st.error(f"Nie udało się odczytać pliku CSV: {exc}")
    else:
        st.caption("Nie przesłano jeszcze pliku portfela.")

with tab_method:
    st.subheader("Jak czytać wynik")
    st.markdown("""
**Ten MVP nie wydaje jeszcze rekomendacji kupna/sprzedaży.** Pokazuje wskaźniki i flaguje sytuacje do sprawdzenia.

- **Zwrot 3M / 6M / 12M:** historyczna zmiana ceny; nie jest prognozą.
- **Stopa dywidendy:** informacyjna wartość z dostawcy danych; wymaga potwierdzenia w dokumentacji funduszu lub spółki.
- **Zmienność roczna:** przybliżona zmienność na podstawie dziennych zwrotów.
- **Maksymalne obsunięcie:** spadek od lokalnego szczytu w obserwowanym okresie.
- **Wstępny status:** proste reguły filtrujące do dalszej analizy, a nie sygnał transakcyjny.

Docelowy model oceny długoterminowego portfela będzie osobno analizował:
1. jakość i trwałość wypłat,
2. kondycję finansową i zadłużenie,
3. wycenę,
4. dywersyfikację i nakładanie się ETF-ów,
5. koszty, podatki i waluty,
6. całkowitą stopę zwrotu wraz z reinwestowanymi dywidendami.
""")

with tab_sources:
    st.subheader("Źródła i ograniczenia")
    st.markdown("""
- **Dane cenowe i część danych o dywidendach:** Yahoo Finance przez bibliotekę `yfinance`.
- `yfinance` jest narzędziem społecznościowym, nieoficjalnym i przeznaczonym do użytku badawczego/osobistego; sprawdź warunki dostawcy danych.
- Dane mogą być opóźnione, brakujące lub błędne. Zawsze weryfikuj istotne informacje w raportach spółek, dokumentach ETF-ów i oficjalnych komunikatach.
- Ta aplikacja nie jest poradą inwestycyjną, nie przewiduje zysków i nie składa zleceń.
- Nie przechowuj tutaj danych logowania do XTB. Wersja MVP nie łączy się z rachunkiem maklerskim.
""")
    st.markdown("[Dokumentacja yfinance](https://ranaroussi.github.io/yfinance/)")
    st.markdown("[Oficjalne informacje XTB o API](https://www.xtb.com/pl/centrum-pomocy/platformy-tradingowe-5/czy-xtb-oferuje-narzedzia-automatyzacji-inwestowania)")
    st.markdown("[Dokumentacja wdrożenia Streamlit Community Cloud](https://docs.streamlit.io/deploy/streamlit-community-cloud)")

st.divider()
st.caption("Income Investor AI MVP 0.1 · Brak integracji transakcyjnej · Zweryfikuj dane przed podjęciem decyzji.")