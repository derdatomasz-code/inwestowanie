from __future__ import annotations

from datetime import datetime, timedelta
import math

import pandas as pd
import streamlit as st
import yfinance as yf

st.set_page_config(page_title="Income Investor AI", page_icon="📈", layout="wide")

DEFAULT_WATCHLIST = [
    "VWRL.L", "VWCE.DE", "VHYL.L", "ISPA.DE", "KO", "JNJ", "PG", "PEP", "MSFT", "NESN.SW"
]
SAMPLE_PORTFOLIO = """ticker,units,avg_buy_price,currency
VWCE.DE,10,120,EUR
KO,5,60,USD
"""
BASE_CURRENCY = "PLN"
FX_TICKERS = {"EUR": "EURPLN=X", "USD": "USDPLN=X", "GBP": "GBPPLN=X", "CHF": "CHFPLN=X", "PLN": None}

st.title("📈 Income Investor AI")
st.caption("MVP 0.3 · Panel kapitału, wycena w PLN i reinwestowanie dywidend · dostęp z iPada")
st.info("Prototyp edukacyjny, nie porada inwestycyjna. Dane z Yahoo Finance przez yfinance mogą być opóźnione, niekompletne lub błędne. Aplikacja nie łączy się z kontem XTB i nie wykonuje transakcji.")

with st.sidebar:
    st.header("Ustawienia")
    tickers_text = st.text_area("Tickery do monitorowania (po jednym w wierszu)", value="\n".join(DEFAULT_WATCHLIST), height=220)
    max_tickers = st.slider("Maksymalna liczba instrumentów w analizie", 3, 30, 10)
    st.caption("Dane pobierane są na żądanie. Aplikacja nie działa automatycznie w tle.")
    st.markdown("**Waluta bazowa portfela: PLN**")

tab_dashboard, tab_today, tab_portfolio, tab_div, tab_method, tab_sources = st.tabs(["Panel kapitału", "Briefing", "Portfel XTB", "Dywidendy i reinwestowanie", "Metodyka i ryzyko", "Źródła i ograniczenia"])

def safe_num(value):
    try:
        if value is None or pd.isna(value): return None
        value = float(value)
        return value if math.isfinite(value) else None
    except Exception:
        return None

def fmt_num(value, digits=2):
    return "—" if value is None or pd.isna(value) else f"{value:,.{digits}f}".replace(",", "X").replace(".", ",").replace("X", ".")

def fmt_pln(value):
    return "—" if value is None or pd.isna(value) else f"{fmt_num(value)} zł"

@st.cache_data(ttl=3600, show_spinner=False)
def get_fx_to_pln(currency: str):
    currency = str(currency).upper().strip()
    if currency == "PLN": return 1.0
    ticker = FX_TICKERS.get(currency)
    if not ticker: return None
    try:
        hist = yf.Ticker(ticker).history(period="5d", interval="1d")
        if hist.empty: return None
        return safe_num(hist["Close"].dropna().iloc[-1])
    except Exception:
        return None

@st.cache_data(ttl=3600, show_spinner=False)
def get_instrument_data(ticker: str):
    obj = yf.Ticker(ticker)
    hist = obj.history(period="2y", interval="1d", auto_adjust=True)
    if hist.empty or "Close" not in hist: return None
    close = hist["Close"].dropna()
    if len(close) < 2: return None
    last = safe_num(close.iloc[-1])
    if last is None: return None
    try: info = obj.info or {}
    except Exception: info = {}
    def ret(days):
        if len(close) <= days: return None
        old = safe_num(close.iloc[-days-1])
        return ((last / old) - 1) * 100 if old else None
    daily = close.pct_change().dropna()
    volatility = safe_num(daily.tail(252).std() * math.sqrt(252) * 100) if len(daily) >= 20 else None
    drawdown = safe_num((close / close.cummax() - 1).tail(252).min() * 100)
    # Use actual distributions in the last 365 days when available, rather than relying only on info.dividendYield.
    try:
        dividends = obj.dividends
        cutoff = pd.Timestamp.now(tz=dividends.index.tz) - pd.Timedelta(days=365) if len(dividends) and dividends.index.tz else pd.Timestamp.now() - pd.Timedelta(days=365)
        trailing_dividend = safe_num(dividends[dividends.index >= cutoff].sum()) if len(dividends) else 0.0
    except Exception:
        trailing_dividend = None
    if trailing_dividend is not None and trailing_dividend <= 0: trailing_dividend = 0.0
    div_yield = (trailing_dividend / last * 100) if trailing_dividend is not None and last > 0 else safe_num(info.get("dividendYield"))
    if div_yield is not None and div_yield <= 1.5: div_yield *= 100
    sma50 = safe_num(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else None
    sma200 = safe_num(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else None
    return {"ticker": ticker, "name": info.get("shortName") or info.get("longName") or ticker,
            "currency": str(info.get("currency") or "—").upper(), "price": last,
            "date": str(close.index[-1].date()), "return_3m": ret(63), "return_6m": ret(126),
            "return_12m": ret(252), "dividend_yield": div_yield, "annual_dividend_per_unit": trailing_dividend,
            "volatility": volatility, "max_drawdown": drawdown, "sma50": sma50, "sma200": sma200,
            "source": "Yahoo Finance / yfinance"}

def preliminary_status(row):
    y, r6 = row.get("dividend_yield"), row.get("return_6m")
    if y is not None and y > 8: return "Sprawdź ryzyko wysokiej stopy dywidendy"
    if r6 is not None and r6 < -15: return "Sprawdź przyczynę spadku"
    if row.get("sma200") is not None and row.get("price") is not None and row["price"] > row["sma200"] and r6 is not None and r6 > 0:
        return "Pozytywne momentum — sprawdź fundamenty"
    return "Obserwuj — brak jednoznacznego sygnału"

with tab_dashboard:
    st.subheader("Panel kapitału — PLN")
    st.write("Zbiorczy widok wartości portfela, wyniku i historycznych wypłat dywidend. Najpierw wczytaj CSV w zakładce Portfel XTB.")
    saved = st.session_state.get("portfolio_valuation")
    if isinstance(saved, pd.DataFrame) and not saved.empty and "Wartość teraz [PLN]" in saved.columns:
        valid_saved = saved[saved["Wartość teraz [PLN]"].notna()].copy()
        if not valid_saved.empty:
            total_value = safe_num(valid_saved["Wartość teraz [PLN]"].sum())
            total_pnl = safe_num(valid_saved["Wynik [PLN, przybliżony]"].sum()) if "Wynik [PLN, przybliżony]" in valid_saved else None
            total_div = safe_num(valid_saved["Dywidenda roczna [PLN, szacunek]"].sum(min_count=1)) if "Dywidenda roczna [PLN, szacunek]" in valid_saved else None
            total_cost_pln = safe_num((valid_saved["Koszt zakupu [waluta]"] * valid_saved["Kurs PLN"]).sum()) if "Koszt zakupu [waluta]" in valid_saved and "Kurs PLN" in valid_saved else None
            a, b, c, d = st.columns(4)
            a.metric("Wartość portfela", fmt_pln(total_value))
            b.metric("Wynik przybliżony", fmt_pln(total_pnl))
            c.metric("Szacowane dywidendy 12M", fmt_pln(total_div))
            d.metric("Wartość dywidend / portfel", f"{total_div / total_value * 100:.2f}%" if total_div is not None and total_value and total_value > 0 else "—")
            if "Ticker" in valid_saved:
                st.markdown("**Udział pozycji w wartości portfela**")
                allocation = valid_saved.groupby("Ticker", as_index=False)["Wartość teraz [PLN]"].sum().sort_values("Wartość teraz [PLN]", ascending=False)
                allocation["Udział portfela %"] = allocation["Wartość teraz [PLN]"] / total_value * 100 if total_value else 0
                st.bar_chart(allocation.set_index("Ticker")["Udział portfela %"])
                st.dataframe(allocation.rename(columns={"Ticker":"Ticker", "Wartość teraz [PLN]":"Wartość [PLN]"}), use_container_width=True, hide_index=True)
            st.caption("Dane pochodzą z ostatniej wyceny wykonanej w zakładce Portfel XTB. Wynik w PLN jest przybliżony, bo koszt zakupu przeliczany jest po bieżącym, a nie historycznym kursie waluty.")
        else:
            st.info("Nie ma jeszcze poprawnie wycenionych pozycji. Przejdź do Portfel XTB i wczytaj plik CSV.")
    else:
        st.info("Panel czeka na wycenę portfela. Otwórz Portfel XTB i wczytaj testowy lub własny plik CSV, aby wypełnić ten widok.")
    st.markdown("**Ważne rozróżnienie**")
    st.write("ETF akumulujący, taki jak VWCE, reinwestuje dochody wewnątrz funduszu i zwykle nie wypłaca ich inwestorowi gotówką. Dlatego dywidenda gotówkowa może wynosić 0, mimo że dochody z aktywów bazowych wpływają na wartość funduszu. Nie porównuj wyłącznie gotówkowej stopy dywidendy — patrz na całkowity zwrot.")

with tab_today:
    st.subheader("Briefing rynkowy")
    st.write("Pobierz najnowsze dostępne notowania i podstawowe wskaźniki. Dodatni zwrot historyczny nie jest rekomendacją zakupu.")
    if st.button("🔄 Pobierz dane i wygeneruj briefing", type="primary", use_container_width=True):
        tickers = list(dict.fromkeys(x.strip().upper() for x in tickers_text.splitlines() if x.strip()))[:max_tickers]
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
                progress.progress(i / max(len(tickers), 1))
        if results:
            st.session_state["latest_df"] = pd.DataFrame(results)
            st.session_state["generated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        else: st.error("Nie udało się pobrać danych. Sprawdź tickery i spróbuj ponownie.")
    if "latest_df" in st.session_state:
        df = st.session_state["latest_df"].copy()
        st.caption(f"Ostatnia aktualizacja: {st.session_state.get('generated_at', '—')} · dane cenowe z {df['date'].max()}")
        c1, c2, c3 = st.columns(3)
        c1.metric("Instrumenty z danymi", len(df))
        c2.metric("Dodatni zwrot 6M", int((df["return_6m"].fillna(-999) > 0).sum()))
        c3.metric("Do sprawdzenia", int(df["status"].str.contains("Sprawdź", na=False).sum()))
        cols = ["ticker", "name", "price", "currency", "return_6m", "return_12m", "dividend_yield", "volatility", "max_drawdown", "status"]
        st.dataframe(df[cols].rename(columns={"ticker":"Ticker", "name":"Instrument", "price":"Cena", "currency":"Waluta ceny", "return_6m":"Zwrot 6M %", "return_12m":"Zwrot 12M %", "dividend_yield":"Dywidenda 12M / cena %", "volatility":"Zmienność roczna %", "max_drawdown":"Obsunięcie 1Y %", "status":"Wstępna flaga"}), use_container_width=True, hide_index=True)
        st.download_button("Pobierz briefing CSV", df.to_csv(index=False).encode("utf-8-sig"), file_name="briefing_inwestycyjny.csv", mime="text/csv")
    else: st.warning("Kliknij przycisk, aby pobrać dane.")

with tab_portfolio:
    st.subheader("Portfel — wycena w PLN")
    st.write("CSV powinien zawierać: ticker, units, avg_buy_price, currency. Cena zakupu jest w walucie wskazanej w kolumnie currency.")
    st.download_button("Pobierz szablon CSV", SAMPLE_PORTFOLIO.encode("utf-8"), file_name="portfel_szablon.csv", mime="text/csv")
    uploaded = st.file_uploader("Wczytaj CSV portfela", type=["csv"], key="portfolio_csv")
    if uploaded:
        try:
            pf = pd.read_csv(uploaded)
            required = {"ticker", "units", "avg_buy_price", "currency"}
            if not required.issubset(pf.columns): st.error("CSV musi zawierać kolumny: ticker, units, avg_buy_price, currency.")
            else:
                pf["ticker"] = pf["ticker"].astype(str).str.upper().str.strip()
                pf["currency"] = pf["currency"].astype(str).str.upper().str.strip()
                pf["units"] = pd.to_numeric(pf["units"], errors="coerce")
                pf["avg_buy_price"] = pd.to_numeric(pf["avg_buy_price"], errors="coerce")
                pf = pf.dropna(subset=["ticker", "units", "avg_buy_price"])
                pf = pf[(pf["units"] > 0) & (pf["avg_buy_price"] >= 0)]
                if pf.empty: st.warning("Nie znaleziono poprawnych pozycji w CSV.")
                else:
                    rows = []
                    with st.spinner("Pobieram ceny i kursy walut..."):
                        bar = st.progress(0)
                        for i, r in enumerate(pf.to_dict("records"), start=1):
                            try:
                                data = get_instrument_data(r["ticker"])
                                fx = get_fx_to_pln(r["currency"])
                                if data is None: raise ValueError("Brak ceny rynkowej")
                                if fx is None: raise ValueError(f"Brak kursu {r['currency']}/PLN")
                                units, buy = float(r["units"]), float(r["avg_buy_price"])
                                current = data["price"]
                                market_value_local = units * current
                                cost_local = units * buy
                                pnl_local = market_value_local - cost_local
                                market_pln = market_value_local * fx
                                # Approximation: applies today's FX to both purchase cost and market value.
                                pnl_pln_approx = pnl_local * fx
                                div_per_unit = data.get("annual_dividend_per_unit")
                                annual_div_local = units * div_per_unit if div_per_unit is not None else None
                                rows.append({"Ticker": r["ticker"], "Instrument": data["name"], "Waluta": r["currency"], "Ilość": units,
                                    "Cena zakupu": buy, "Cena teraz": current, "Wartość teraz [waluta]": market_value_local,
                                    "Wartość teraz [PLN]": market_pln, "Koszt zakupu [waluta]": cost_local,
                                    "Wynik [waluta]": pnl_local, "Wynik %": ((current / buy - 1) * 100 if buy else None),
                                    "Wynik [PLN, przybliżony]": pnl_pln_approx, "Kurs PLN": fx,
                                    "Dywidenda 12M / jednostkę": div_per_unit,
                                    "Dywidenda roczna [PLN, szacunek]": annual_div_local * fx if annual_div_local is not None else None,
                                    "Data ceny": data["date"]})
                            except Exception as exc:
                                rows.append({"Ticker": r["ticker"], "Błąd": str(exc)})
                            bar.progress(i / len(pf))
                    out = pd.DataFrame(rows)
                    valid = out[out.get("Wartość teraz [PLN]", pd.Series(index=out.index, dtype=float)).notna()] if "Wartość teraz [PLN]" in out else pd.DataFrame()
                    if not valid.empty:
                        st.session_state["portfolio_valuation"] = valid.copy()
                        total_value = valid["Wartość teraz [PLN]"].sum()
                        total_div = valid["Dywidenda roczna [PLN, szacunek]"].sum(min_count=1)
                        total_pnl = valid["Wynik [PLN, przybliżony]"].sum()
                        m1, m2, m3 = st.columns(3)
                        m1.metric("Wartość portfela", fmt_pln(total_value))
                        m2.metric("Wynik niezrealizowany*", fmt_pln(total_pnl))
                        m3.metric("Szacowane dywidendy roczne", fmt_pln(total_div))
                        if total_value > 0 and pd.notna(total_div): st.metric("Szacowana stopa wypłat portfela", f"{total_div / total_value * 100:.2f}%")
                        st.dataframe(out, use_container_width=True, hide_index=True)
                        st.download_button("Pobierz wycenę portfela CSV", out.to_csv(index=False).encode("utf-8-sig"), file_name="wycena_portfela.csv", mime="text/csv")
                        st.caption("*Wynik w PLN jest przybliżony: dla ceny zakupu zastosowano dzisiejszy kurs walutowy, nie historyczny kurs z dnia zakupu. Pomija prowizje, podatki, wpłaty/wypłaty i corporate actions. Weryfikuj ceny oraz kursy przed decyzją.")
                    else:
                        st.warning("Nie udało się wycenić pozycji. Sprawdź tickery, waluty i dostępność danych.")
                        st.dataframe(out, use_container_width=True, hide_index=True)
        except Exception as exc: st.error(f"Nie udało się odczytać CSV: {exc}")
    else: st.caption("Możesz przetestować import szablonem. Nie wysyłaj haseł ani danych logowania do XTB.")

with tab_div:
    st.subheader("Dywidendy i reinwestowanie")
    st.write("Moduł szacuje wypłaty na podstawie dywidend odnotowanych w danych za ostatnie 365 dni. Nie jest to gwarancja przyszłych wypłat.")
    st.markdown("**Symulator długoterminowego wzrostu**")
    st.caption("Możesz porównać dwa scenariusze, zmieniając opcję reinwestowania. Dla uczciwego porównania używaj tej samej założonej stopy całkowitego zwrotu i pamiętaj, że scenariusz nie przewiduje przyszłych wyników.")
    c1, c2 = st.columns(2)
    with c1:
        initial = st.number_input("Kapitał początkowy (PLN)", min_value=0.0, value=20000.0, step=1000.0)
        monthly = st.number_input("Dopłata miesięczna (PLN)", min_value=0.0, value=1000.0, step=100.0)
        years = st.slider("Horyzont (lata)", 1, 40, 20)
    with c2:
        annual_return = st.number_input("Założona roczna stopa całkowitego zwrotu (%)", min_value=-50.0, max_value=50.0, value=6.0, step=0.5)
        reinvest = st.checkbox("Reinwestuj zyski i dywidendy", value=True)
        div_yield = st.number_input("W tym: założona stopa dywidendy (%)", min_value=0.0, max_value=30.0, value=2.0, step=0.5)
    st.caption("Model edukacyjny: stopa całkowitego zwrotu obejmuje wzrost ceny i dywidendy. Jeśli zaznaczysz reinwestowanie, dywidendy pozostają w kapitale; nie dodawaj ich drugi raz do stopy zwrotu.")
    if st.button("Oblicz scenariusz", use_container_width=True):
        # If dividends are not reinvested, treat the input total return as price growth + dividend yield.
        price_return = annual_return if reinvest else annual_return - div_yield
        monthly_rate = (1 + price_return / 100) ** (1/12) - 1
        balance = initial
        cash_dividends = 0.0
        total_contrib = initial
        rows = []
        for month in range(1, years * 12 + 1):
            balance *= (1 + monthly_rate)
            if not reinvest:
                cash_dividends += max(balance, 0) * (div_yield / 100) / 12
            balance += monthly
            total_contrib += monthly
            if month % 12 == 0:
                total_wealth = balance + cash_dividends
                rows.append({"Rok": month // 12, "Wartość inwestycji [PLN]": balance, "Dywidendy gotówkowe narastająco [PLN]": cash_dividends, "Łączny majątek [PLN]": total_wealth, "Wpłacony kapitał [PLN]": total_contrib, "Zysk ponad wpłaty [PLN]": total_wealth-total_contrib, "Szacowana dywidenda roczna [PLN]": balance * div_yield / 100})
        sim = pd.DataFrame(rows)
        last = sim.iloc[-1]
        a, b, c = st.columns(3)
        a.metric("Łączny majątek po okresie", fmt_pln(last["Łączny majątek [PLN]"]))
        b.metric("Suma wpłat", fmt_pln(last["Wpłacony kapitał [PLN]"]))
        c.metric("Zysk ponad wpłaty", fmt_pln(last["Zysk ponad wpłaty [PLN]"]))
        st.line_chart(sim.set_index("Rok")[["Łączny majątek [PLN]", "Wpłacony kapitał [PLN]"]])
        st.dataframe(sim, use_container_width=True, hide_index=True)
        st.download_button("Pobierz symulację CSV", sim.to_csv(index=False).encode("utf-8-sig"), file_name="symulacja_reinwestowania.csv", mime="text/csv")
    st.warning("Symulacja jest hipotetyczna. Nie uwzględnia podatków, opłat, inflacji, zmienności stóp zwrotu ani ryzyka walutowego. Nie stanowi prognozy ani obietnicy wyniku.")

with tab_method:
    st.subheader("Metodyka i ryzyko")
    st.markdown("""
- **Wartość portfela w PLN:** liczba jednostek × ostatnia dostępna cena × aktualny kurs waluty do PLN.
- **Wynik w walucie instrumentu:** (ostatnia cena − średnia cena zakupu) × liczba jednostek.
- **Wynik w PLN:** przybliżenie przeliczające wynik w walucie instrumentu po dzisiejszym kursie. Dokładny wynik wymaga historii transakcji i kursów walut z dat zakupu.
- **Dywidendy:** suma wypłat odnotowanych przez dostawcę danych w ostatnich 365 dniach. Mogą brakować wypłat, a przyszłe dywidendy mogą być obniżone lub zawieszone.
- **Stopa dywidendy:** dywidendy z ostatnich 365 dni / bieżąca cena. To wskaźnik historyczny, nie obietnica przyszłego dochodu.
- **Symulacja:** scenariusz matematyczny stałej stopy całkowitego zwrotu, nie prognoza.

Przed decyzją sprawdzaj oficjalne raporty emitenta, dokumentację ETF, koszty, podatki, walutę notowania i warunki instrumentu. Sama wysoka stopa dywidendy ani dodatni wynik 6M nie stanowią sygnału kupna.
""")

with tab_sources:
    st.subheader("Źródła i ograniczenia")
    st.markdown("""
- Notowania, historia i część danych o dywidendach: Yahoo Finance przez bibliotekę `yfinance`.
- Kursy walut: symbole Yahoo Finance, np. EURPLN=X i USDPLN=X; dostępność może się zmieniać.
- `yfinance` jest narzędziem nieoficjalnym. Dane mogą być opóźnione, brakujące lub błędne.
- W przypadku ETF-ów notowanych w innej jednostce (np. pensach) zweryfikuj walutę i skalę ceny przed importem.
- Aplikacja nie jest poradą inwestycyjną, nie przewiduje zysków i nie składa zleceń.
""")