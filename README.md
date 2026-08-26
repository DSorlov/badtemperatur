# Badtemperatur

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/)
[![Validate](https://github.com/dsorlov/badtemperatur/actions/workflows/validate.yml/badge.svg)](https://github.com/dsorlov/badtemperatur/actions/workflows/validate.yml)

Home Assistant-integration som hämtar **badtemperatur (havsytetemperatur)** från
[Copernicus Marine Service](https://marine.copernicus.eu/) – satellitdata som bland
annat bygger på **Sentinel-3 SLSTR**.

*Svenska nedan, [English further down](#english).*

---

## Funktioner

- 🌊 Vattentemperatur för valfri kustnära position, direkt från satellitdata
- 🗺️ Full GUI-konfiguration med kartväljare – ingen YAML
- 📍 Flera badplatser: lägg till en post per plats, var och en blir en egen enhet
- 🛰️ Automatiskt val av bästa datakälla (Östersjön 0,02°, europeiska hav 0,01°, globalt 0,05°)
- 🔎 Hittar automatiskt närmaste havsruta när markören hamnar på land
- 🇸🇪 Svenska och engelska översättningar
- 🔁 Konfigurera om plats, sökradie och uppdateringsintervall när som helst
- 🩺 Stöd för diagnostikfiler

Inga extra Python-beroenden installeras – integrationen använder Copernicus
WMTS-tjänsten (`GetFeatureInfo`) via vanliga HTTP-anrop.

## Installation

### HACS (rekommenderas)

1. Gå till **HACS → Integrationer → ⋮ → Anpassade arkiv**.
2. Lägg till `https://github.com/dsorlov/badtemperatur` som kategori **Integration**.
3. Sök upp **Badtemperatur**, installera och starta om Home Assistant.

### Manuellt

Kopiera mappen `custom_components/badtemperatur` till din `config/custom_components/`
och starta om Home Assistant.

## Konfiguration

**Inställningar → Enheter och tjänster → Lägg till integration → Badtemperatur**

| Fält | Beskrivning |
| --- | --- |
| Namn | Visas som enhetens namn, t.ex. `Tylösand` |
| Plats | Peka ut badplatsen på kartan |
| Sökradie | Hur långt (0–25 km) integrationen får leta efter en havsruta |
| Datakälla | `Automatiskt` eller en specifik Copernicus-produkt |

Upprepa för varje badplats du vill följa.

Uppdateringsintervallet ändras via **Konfigurera** på integrationen. Plats, sökradie
och datakälla ändras via **Konfigurera om**.

### Om sökradien

Satellitprodukterna är rutnät där land är maskerat. En markör mitt i en smal vik
eller innerskärgård kan därför sakna värde. Integrationen söker då utåt i ringar
och väljer den närmaste rutan med giltig data. Avståndet redovisas i attributet
`distance_km`.

## Entiteter

| Entitet | Beskrivning |
| --- | --- |
| `sensor.<plats>_vattentemperatur` | Havsytetemperatur i °C (`measurement`, loggas i statistik) |
| `sensor.<plats>_observationsdatum` | Datum för det satellitdygn värdet gäller (diagnostik) |

Attribut på temperatursensorn: `dataset`, `dataset_name`, `measurement_latitude`,
`measurement_longitude`, `distance_km`.

### Exempel på automation

```yaml
automation:
  - alias: Dags att bada
    triggers:
      - trigger: numeric_state
        entity_id: sensor.tylosand_vattentemperatur
        above: 18
    actions:
      - action: notify.mobile_app
        data:
          message: >-
            Vattnet i Tylösand är {{ states('sensor.tylosand_vattentemperatur') }} °C.
```

## Datakällor

| Nyckel | Produkt | Upplösning | Täckning |
| --- | --- | --- | --- |
| `baltic` | `SST_BAL_SST_L4_NRT_OBSERVATIONS_010_007_b` | 0,02° | Östersjön, Kattegatt, Skagerrak |
| `atlantic` | `SST_ATL_SST_L4_NRT_OBSERVATIONS_010_025` | 0,01° | Nordatlanten och europeiska hav |
| `mediterranean` | `SST_MED_SST_L4_NRT_OBSERVATIONS_010_004` | 0,01° | Medelhavet |
| `black_sea` | `SST_BS_SST_L4_NRT_OBSERVATIONS_010_006` | 0,01° | Svarta havet |
| `global` | `SST_GLO_SST_L4_NRT_OBSERVATIONS_010_001` | 0,05° | Hela världshavet |

L4-produkterna är dygnsvisa analyser som slår ihop observationer från flera
satelliter, däribland Sentinel-3 SLSTR. Värdet är alltså ett dygnsmedel för
ytvattnet – inte en momentanmätning vid badbryggan.

## Utveckling

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-test.txt
ruff check . && ruff format --check .
pytest
```

## Attribution

> Generated using E.U. Copernicus Marine Service Information.

Data tillhandahålls av Copernicus Marine Service och omfattas av deras
[användarvillkor](https://marine.copernicus.eu/user-corner/service-commitments-and-licence).
Projektet är inte anslutet till eller godkänt av Copernicus, Mercator Ocean
International eller EU.

## Licens

[MIT](LICENSE)

---

## English

Home Assistant integration that fetches **bathing water temperature (sea surface
temperature)** from the [Copernicus Marine Service](https://marine.copernicus.eu/),
based on satellite observations including **Sentinel-3 SLSTR**.

- Water temperature for any coastal position
- Full GUI configuration with a map picker, no YAML
- Multiple bathing spots – one config entry and device per location
- Automatic selection of the highest resolution product covering the location
- Automatically finds the nearest sea grid cell when the marker lands on land
- Swedish and English translations
- Reconfigure location, search radius and update interval at any time

Install through HACS as a custom repository
(`https://github.com/dsorlov/badtemperatur`, category *Integration*), restart
Home Assistant and add the integration from **Settings → Devices & services**.

No additional Python dependencies are installed; the integration talks to the
Copernicus WMTS `GetFeatureInfo` endpoint over plain HTTP.
