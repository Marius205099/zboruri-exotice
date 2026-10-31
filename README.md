# 🌴 Zboruri exotice de iarnă

Site care arată cele mai ieftine zboruri dus-întors pentru o familie (2 adulți + 2 copii de 3 și 5 ani):

- **Plecare din:** Timișoara (TSR), Cluj-Napoca (CLJ), Budapesta (BUD), Belgrad (BEG)
- **Destinații:** Maldive (MLE), Bali (DPS), Thailanda (BKK, HKT), Mauritius (MRU)
- **Plecare:** 26 decembrie 2026 – 3 ianuarie 2027, sejur de 7, 8 sau 9 nopți
- **Durata zborului dus:** maxim 25 de ore

Un GitHub Action ([scan.yml](.github/workflows/scan.yml)) rulează [scanner/scan.py](scanner/scan.py) de două ori pe zi
(≈07:00 și 19:00 ora României), caută pe Google Flights toate cele 540 de combinații și salvează rezultatele în
`docs/data/`. Site-ul din `docs/` este publicat cu GitHub Pages.

Scanare manuală: tab-ul **Actions** → *Scanare zboruri* → **Run workflow**.

Rulare locală:

```bash
pip install -r scanner/requirements.txt
python scanner/scan.py        # toate combinațiile
python scanner/scan.py 20     # doar primele 20, pentru test
```
