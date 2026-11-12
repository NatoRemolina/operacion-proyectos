# Fuentes de los datos geográficos

Preparados con `python -m datos.geografia` el 2026-11-12. Se cargan a la base con la semilla, que registra cada carga en `cargas_datos`.

- **Aeropuertos y países:** [OurAirports](https://ourairports.com/data/), dominio público. Solo aeropuertos con código IATA, servicio regular y tipo grande, mediano o pequeño.
- **Lugares y regiones:** [GeoNames](https://www.geonames.org/), licencia [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Ciudades y pueblos de más de 1.000 habitantes (`cities1000`). Cambios: se conservan nombre, nombres alternativos en alfabeto latino (de 3 a 40 letras), país, región, coordenadas y población.
- **Nombres de países en español:** estándar ICU, con `Intl.DisplayNames` de Node.

## Archivos descargados

| Archivo | URL | Huella SHA-256 |
|---|---|---|
| `airports.csv` | https://davidmegginson.github.io/ourairports-data/airports.csv | `11e7a1edf9e5bef91aa4492e3ab42bb5b38b5f2df81358a235ed5a393a571e54` |
| `countries.csv` | https://davidmegginson.github.io/ourairports-data/countries.csv | `2a9dbee691125b0cdb8ceb5fe227c48c903f99c488963b8e53e2ab366521c639` |
| `cities1000.zip` | https://download.geonames.org/export/dump/cities1000.zip | `17c26b51dbaed1a8c5dd0aa2552bdb3ce6f12ac29c92eba3e7df73e4cbea37ec` |
| `admin1CodesASCII.txt` | https://download.geonames.org/export/dump/admin1CodesASCII.txt | `2e4867f5397acb056ea26377601b57af37cb4c81399770225018e9e439e91ad3` |

## Archivos preparados

| Archivo | Filas | Huella SHA-256 |
|---|---|---|
| `aeropuertos.csv` | 4008 | `9262ae0d2e59f9be193dbd59f8d912dd7124dda21e15b1a796a57dfebd9f6b1f` |
| `lugares.csv.gz` | 171838 | `8f40c41fd71a0edae431affe5a90691e2ae8ecd8ef61f31d6b0a3cd37f97cecd` |
| `paises.csv` | 249 | `0122e854ff210dece65de5558147115c75a3ced18d9512738f5d884ed94974ae` |
| `regiones.csv` | 3865 | `9c953be78414546d20f3b0d59e87a3f3c4356b1d64f08081301236493dc8ddbb` |
