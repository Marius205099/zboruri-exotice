# 🌴 Zboruri exotice de iarnă

Site care arată cele mai ieftine zboruri dus-întors pentru o familie (2 adulți + 2 copii de 3 și 5 ani):

- **Plecare din:** Timișoara (TSR), Cluj-Napoca (CLJ), Budapesta (BUD), Belgrad (BEG)
- **Destinații:** Maldive (MLE), Bali (DPS), Thailanda (BKK, HKT), Mauritius (MRU)
- **Plecare:** 26 decembrie 2026 – 18 ianuarie 2027
- **Cazare:** 7 nopți numărate de la aterizare (plecare 10 ian, aterizare 11 ian, retur 18 ian)
- **Zborul dus:** maxim 20 de ore, cu cel mult o escală
- **Bagaje:** tab separat pentru transfer automat (un singur bilet) și pentru transfer manual (bilete separate)

Un GitHub Action ([scan.yml](.github/workflows/scan.yml)) rulează [scanner/scan.py](scanner/scan.py) de două ori pe zi
(pornește ≈07:30 și 19:30 ora României), caută pe Google Flights 1.440 de combinații și salvează rezultatele în
`docs/data/`. Site-ul din `docs/` este publicat cu GitHub Pages.

## Combinații cu oprire 1–2 zile (bilete separate)

[scanner/scan_stopover.py](scanner/scan_stopover.py) caută și variante mai ieftine cu bilete separate:
casă → oraș-hub (ex. Timișoara → Milano cu Wizz Air), 1–2 nopți acolo, apoi hub ⇄ destinație exotică
dus-întors, iar la întoarcere încă 1–2 nopți în hub și zbor spre casă. Hub-uri: Milano, Roma, Madrid,
Barcelona, Londra, Paris, München, Viena, Atena, Istanbul, Dubai, Abu Dhabi, Doha.
Rezultatele sunt în `docs/data/stopovers.json` și apar în primul tab al site-ului.

Scanare manuală: tab-ul **Actions** → *Scanare zboruri* → **Run workflow**.

Rulare locală:

```bash
pip install -r scanner/requirements.txt
python scanner/scan.py        # toate combinațiile
python scanner/scan.py 20     # doar primele 20, pentru test
```
