# inwestowanie
# Income Investor AI — MVP 0.1

Aplikacja webowa działająca w przeglądarce, zaprojektowana z myślą o iPadzie. W tej wersji:
- pobiera historyczne dane cenowe i część danych o dywidendach przez `yfinance`;
- pokazuje prosty briefing oraz wskaźniki ryzyka;
- pozwala wczytać CSV portfela XTB;
- pozwala pobrać raport CSV;
- nie łączy się z XTB i nie składa zleceń.

## Uruchomienie lokalne

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Wdrożenie z iPada

1. Utwórz prywatne repozytorium na GitHub.
2. Dodaj do niego `app.py`, `requirements.txt` i `README.md`.
3. Otwórz https://share.streamlit.io/ i zaloguj się przez GitHub.
4. Wybierz **Create app**, wskaż repozytorium, gałąź `main` i plik `app.py`.
5. Kliknij **Deploy**. Po uruchomieniu otwórz link aplikacji w Safari na iPadzie.

Instrukcja oficjalna: https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app

## Portfel XTB

W zakładce „Portfel XTB” możesz wczytać CSV z kolumnami:
`ticker,units,avg_buy_price,currency`

Przykładowy plik jest dostępny w przycisku w aplikacji. To szablon, nie uniwersalny format eksportu XTB — dane z eksportu trzeba dopasować do tych kolumn. Nie podawaj loginu ani hasła.

## Ważne ograniczenia

- Dane `yfinance` są nieoficjalne i przeznaczone do użytku badawczego/osobistego. Sprawdź warunki dostawcy.
- Stopa dywidendy może być nieaktualna lub nieporównywalna pomiędzy instrumentami.
- Dochód netto nie jest jeszcze liczony; wymaga uwzględnienia podatku u źródła, polskich zasad podatkowych, typu instrumentu i indywidualnej sytuacji.
- Nie ma jeszcze codziennego harmonogramu, AI do analizy wiadomości ani alertów. To kolejne etapy rozwoju.
- Nie jest to porada inwestycyjna ani gwarancja wyników.
