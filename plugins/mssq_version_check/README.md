# mssql_version_check

CheckMK 2.4 Plugin — monitors installed MSSQL version per instance and checks for available CU/GDR updates via Microsoft Learn.

## Changelog
- **1.0.24**: Restored `name="mssql_instance"` + `parsed_section_name="mssql_version_check"` to fix service naming. Re-added rulesets and checkman.
- **1.0.23**: Version bump.
- **1.0.22**: Fixed AgentSection name conflict using `supersedes` (reverted in 1.0.24).
- **1.0.21**: CU/GDR tracking, WATO rule, fetching from Microsoft Learn HTML.

## Requirements
- CheckMK >= 2.4.0
- Internet access from CMK server to `learn.microsoft.com`

## Installation
```bash
mkp add mssql_version_check-1.0.24.mkp
mkp enable mssql_version_check
```
