# Tanulói teljesítmény elemző webapp

Streamlit alkalmazás egy kiválasztott tanuló kompetenciamérési eredményeinek több tanéven át történő megjelenítésére.

## Helyi futtatás

```bash
pip install -r requirements.txt
streamlit run app.py
```

## GitHub + Streamlit Cloud

1. Töltsd fel az `app.py`, `requirements.txt` és `.streamlit/config.toml` fájlokat egy GitHub repositoryba.
2. Streamlit Cloudon válaszd ki a repositoryt.
3. Main file path: `app.py`.
4. Deploy.

## Excel elvárt szerkezete

- Az egyes tanévek külön munkalapon szerepelnek, például `2023-2024`, `2024-2025`, `2025-2026`.
- A `Azonosítók` munkalap tartalmazza a mérési azonosítókat és a neveket.
- A kompetenciaterületek az első sorban, a mérési időszakok a második sorban, az oszlopnevek a harmadik sorban vannak.
- A tanulók sorai a negyedik sortól kezdődnek.
