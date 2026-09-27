# cloud-ecommerce-analytics

End-to-end Cloud-Datenpipeline für WooCommerce + GA4 → Azure → Power BI
(IU Cloud Programming Portfolio, DLBSEPCP01_D)

## Architektur

![E-Commerce Cloud-Architektur – Batch-Only-Konzept](docs/architecture.png)

Architekturkonzept aus der Konzeptionsphase (Quelle: [docs/architecture_concept.html](docs/architecture_concept.html)).

**Ergänzung in der Umsetzung: Google Search Console API.** Zusätzlich zu WooCommerce und GA4 wird die Search Console als dritte Datenquelle geladen. Sie liefert die Suchleistung der Website in der Google-Suche: Suchanfragen, Seiten, Impressionen, Klicks, Klickrate und durchschnittliche Position pro Tag, Land und Gerät. Damit ergänzt sie die SEO-Sicht, die GA4 allein nicht abdeckt: welche Suchbegriffe Besucher in den Shop bringen. Der Zugriff läuft über dasselbe Google-Cloud-Dienstkonto wie bei GA4, sodass kein zusätzlicher Dienst und keine zusätzlichen Kosten entstehen.

## Struktur

- `data/` – Python-Extraktionsskripte (`extract_*.py`): laden WooCommerce (Bestellungen, Bestellpositionen, Produkte, Kategorien), GA4 und Google Search Console per API und schreiben die Rohdaten ins Schema `raw` (Full Refresh)
- `sql/` – SQL-Skripte für Azure SQL Database: Schemas `raw`, `staging`, `mart` und die Tabellen der Raw-Schicht
- Azure Data Factory – Transformationen: `raw` → `staging` (Bereinigung) → `mart` (Dimensionen und Fakten für Power BI); wird im Azure-Portal erstellt *(geplant)*
- `terraform/` – Infrastructure as Code: Azure-Ressourcen (Resource Group, SQL Server, Datenbank, Function App) *(geplant)*
- `function_app/` – Azure Functions (Python): automatisierter, zeitgesteuerter Ablauf der Extraktionsskripte *(geplant)*
- `docs/` – Tabellendesign und Projektlog
- `.env.example` – Vorlage für die Zugangsdaten; die echten Werte stehen in `.env` (nicht im Repository)

## Status

- Phase 1 (Konzeption): abgeschlossen
- Phase 2 (Umsetzung): in Arbeit
