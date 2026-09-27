# cloud-ecommerce-analytics

End-to-end Cloud-Datenpipeline für WooCommerce + GA4 → Azure → Power BI
(IU Cloud Programming Portfolio, DLBSEPCP01_D)

## Architektur

Batch-Pipeline auf Azure, ausgelegt auf ein Budget von rund 10 € pro Monat. Gestrichelt = geplant.

```mermaid
flowchart LR
    subgraph Quellen["Datenquellen"]
        WC["WooCommerce REST API<br/>Bestellungen, Produkte, Kategorien"]
        GA4["GA4 Data API<br/>Traffic und Events"]
        GSC["Search Console API<br/>Suchanfragen"]
    end

    subgraph Extraktion["Extraktion"]
        PY["Python-Skripte<br/>data/extract_*.py"]
        FUNC["Azure Functions<br/>täglicher Abruf"]
    end

    subgraph SQL["Azure SQL Database (serverless, Auto-Pause)"]
        RAW[("raw<br/>Rohdaten")]
        STG[("staging<br/>bereinigt")]
        MART[("mart<br/>Dimensionen und Fakten")]
    end

    PBI["Power BI<br/>Dashboards"]
    DBT["dbt<br/>Transformationen"]
    TF["Terraform<br/>Infrastructure as Code"]
    GH["GitHub<br/>Versionskontrolle"]
    MON["Azure Monitor<br/>Logs und Alerts"]

    WC --> PY
    GA4 --> PY
    GSC --> PY
    PY --> RAW
    PY -.-> FUNC
    RAW --> STG --> MART --> PBI
    DBT -.-> STG
    DBT -.-> MART
    TF -.->|provisioniert| SQL
    TF -.->|provisioniert| FUNC
    GH --- TF
    MON -.->|überwacht| FUNC
    MON -.->|überwacht| SQL

    classDef geplant stroke-dasharray: 5 5
    class FUNC,DBT,TF,MON,STG,MART,PBI geplant
```

## Struktur

- `data/` – Python-Extraktionsskripte (`extract_*.py`): laden WooCommerce (Bestellungen, Bestellpositionen, Produkte, Kategorien), GA4 und Google Search Console per API und schreiben die Rohdaten ins Schema `raw` (Full Refresh)
- `sql/` – SQL-Skripte für Azure SQL Database: Schemas `raw`, `staging`, `mart` und die Tabellen der Raw-Schicht
- `dbt/` – Transformationsmodelle: `staging` (Bereinigung) → `mart` (Dimensionen und Fakten für Power BI) *(geplant)*
- `terraform/` – Infrastructure as Code: Azure-Ressourcen (Resource Group, SQL Server, Datenbank, Function App) *(geplant)*
- `function_app/` – Azure Functions (Python): automatisierter, zeitgesteuerter Ablauf der Extraktionsskripte *(geplant)*
- `docs/` – Tabellendesign und Projektlog
- `.env.example` – Vorlage für die Zugangsdaten; die echten Werte stehen in `.env` (nicht im Repository)

## Status

- Phase 1 (Konzeption): abgeschlossen
- Phase 2 (Umsetzung): in Arbeit
