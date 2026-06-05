# mssql_version_check

CheckMK MKP — Monitors installed Microsoft SQL Server versions per instance and checks whether updates are available.

## What does this plugin do?

One service `MSSQL <instance> Version` is created per SQL Server instance, e.g.:

```
OK   MSSQL MSSQLSERVER Version   Version: Microsoft SQL Server 2025 (RTM) (17.0.4045.5) - Enterprise Evaluation Edition (64-bit) | Up to date (latest CU + GDR: 17.0.4045.5)
OK   MSSQL DIAMANTP Version      Version: Microsoft SQL Server 2022 (RTM) (16.0.4255.1) - Standard Edition (64-bit) | Up to date (latest CU + GDR: 16.0.4255.1)
WARN MSSQL BIKE Version          Version: Microsoft SQL Server 2022 (RTM) (16.0.4245.2) - Standard Edition (64-bit) | Update available - latest CU + GDR: 16.0.4255.1
```

The latest build numbers are fetched automatically from the **official Microsoft Learn documentation** and cached at `$OMD_ROOT/var/check_mk/mssql_latest_builds.json`. The cache refreshes once per day automatically — no cronjob required.

Supported SQL Server versions: **2014, 2016, 2017, 2019, 2022, 2025**

## CU vs CU + GDR

Microsoft publishes two types of updates:

- **CU (Cumulative Update)** — regular feature and bug fix updates
- **GDR (General Distribution Release)** — security patches on top of a CU

Both are cached separately. Via the WATO rule you can choose which one to use as reference:

| Setting | Reference build | Effect |
|---|---|---|
| Latest CU | e.g. `15.0.4430.1` | Hosts on CU without GDR are OK |
| Latest CU + GDR *(default)* | e.g. `15.0.4470.1` | Hosts without the latest security patch are WARN/CRIT |

## Data source

Official Microsoft Learn build version pages:
- `https://learn.microsoft.com/en-us/troubleshoot/sql/releases/sqlserver-2022/build-versions`
- `https://learn.microsoft.com/en-us/troubleshoot/sql/releases/sqlserver-2019/build-versions`
- (and so on for each supported version)

Note: Microsoft Learn may take a few days to mark a new build as "latest" after release. This plugin always takes the highest build number found on the page regardless of the marker, so it stays current.

## Requirements

- CheckMK 2.4.0+
- Windows Agent with `mssql.vbs` or `mk-sql.exe` plugin
- Outbound HTTPS access from the CMK server to `learn.microsoft.com`

## Repository structure

```
mssql_version_check/
├── bin/
│   └── mssql_fetch_builds.py              # Optional CLI tool for manual cache refresh
├── mssql_version_check/
│   ├── agent_based/
│   │   └── mssql_version_check.py         # Main plugin: parse, discovery, check logic
│   ├── rulesets/
│   │   └── mssql_version_check.py         # WATO rule: state, CU vs CU+GDR
│   └── checkman/
│       └── mssql_version_check            # Inline help shown in the CMK UI
├── info                                   # MKP metadata (Python dict)
├── info.json                              # MKP metadata (JSON)
└── mssql_version_check-1_0_21.mkp        # Ready-to-install MKP
```

## Installation

### Via CMK Web UI

1. Upload the MKP under **Setup → Extension packages**
2. Enable the package
3. Bake and deploy agents
4. Run service discovery on affected hosts

### Via CLI

```bash
mkp add mssql_version_check-1_0_21.mkp
mkp enable mssql_version_check 1.0.21
cmk -II <hostname>
```

## Manual cache refresh

```bash
# Show result without writing
python3 ~/local/bin/mssql_fetch_builds.py --show

# Force cache update
python3 ~/local/bin/mssql_fetch_builds.py
```

## WATO rule

Under **Setup → Service monitoring rules → MSSQL Version (online update check)** you can configure per host or instance:

- Whether an outdated version triggers `WARN` or `CRIT` (default: `WARN`)
- Whether to compare against the latest **CU** or the latest **CU + GDR** (default: `CU + GDR`)

## Author

Marius Gielnik — COMRAMO AG
