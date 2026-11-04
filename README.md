# 🌴 Zboruri exotice de iarnă

Site care arată cele mai ieftine zboruri dus-întors pentru o familie (2 adulți + 2 copii de 3 și 5 ani):

- **Plecare din:** Timișoara (TSR), Cluj-Napoca (CLJ), Budapesta (BUD), Belgrad (BEG)
- **Destinații:** Maldive (MLE), Bali (DPS), Thailanda (Phuket, HKT), Mauritius (MRU)
- **Plecare:** de azi până pe 10 ianuarie 2028, cu returul până pe 18 ianuarie 2028 (Google arată zboruri cu cel mult 330 de zile înainte, restul apar pe măsură ce se apropie)
- **Cazare:** 7 nopți numărate de la aterizare (plecare 10 ian, aterizare 11 ian, retur 18 ian)
- **Transfer automat (un singur bilet):** dus și retur de maxim 20 de ore fiecare, cu cel mult o escală
- **Transfer manual (bilete separate):** cel mult o escală pe fiecare zbor, zborul lung poate depăși 20 de ore
- **Tur și retur:** ambele sunt verificate și afișate pentru fiecare ofertă, iar prețul este al biletului cu acel retur

Un GitHub Action ([scan.yml](.github/workflows/scan.yml)) rulează [scanner/scan.py](scanner/scan.py) de două ori pe zi
(pornește ≈07:30 și 19:30 ora României), împarte căutările pe 20 de joburi paralele și salvează rezultatele în
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
python scanner/scan.py 0 1        # toate combinațiile (partea 0 din 1)
python scanner/scan.py merge      # scrie rezultatele în docs/data
```
