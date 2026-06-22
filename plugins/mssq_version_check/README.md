# mssql_version_check

CheckMK 2.4 Plugin — monitors installed MSSQL version per instance and checks for available CU/GDR updates via Microsoft Learn.

## Changelog
- **1.0.27**: **Important fix.** Removed the plugin's own `AgentSection(name="mssql_instance", ...)`
  registration. It collided with CheckMK's built-in section of the same name
  (`cmk.plugins.mssql.agent_based.mssql_instance`), which silently broke the official
  "MS SQL: General State" check and the MSSQL HW/SW inventory on every host running this
  MKP (visible as `WARNING: mssql_instance: failed: 'list' object has no attribute 'items'`
  in the Check_MK HW/SW Inventory service, and as a load-time error in `cmk -d`).
  The plugin now subscribes to the already-registered official section instead
  (`sections=["mssql_instance"]`) and adapts its `Mapping[str, Mapping[str, str]]` format
  directly - the pattern CheckMK's own docs describe for extending an existing section.
  No functional change to the version/CU-GDR check logic itself.
- **1.0.26**: Parse the `state` row from `mssql_instance`. When the agent failed to query
  the live instance (e.g. missing OLE DB provider) and the check falls back to the RTM
  version from the registry, the actual connection error is now shown as a WARN notice
  instead of the generic "config line" note.
- **1.0.25**: Restored robust regex extraction of the version string in `parse_mssql_version_check`
  (`re.search(r"\b(1[2-7]\.0\.\d+\.\d+)\b", raw_version)`), which was missing in 1.0.24.
  Prevents KB/hyphen-suffixed version strings from breaking major-version parsing.
- **1.0.24**: Restored `name="mssql_instance"` + `parsed_section_name="mssql_version_check"` to fix service naming. Re-added rulesets and checkman.
- **1.0.23**: Version bump.
- **1.0.22**: Fixed AgentSection name conflict using `supersedes` (reverted in 1.0.24).
- **1.0.21**: CU/GDR tracking, WATO rule, fetching from Microsoft Learn HTML.

## Requirements
- CheckMK >= 2.4.0
- Internet access from CMK server to `learn.microsoft.com`

## Installation
```bash
mkp add mssql_version_check-1_0_27.mkp
mkp enable mssql_version_check 1.0.27
cmk -II <hostname>
```

After updating, verify the collision is gone:
```bash
cmk -d <hostname> 2>&1 | grep -i "already defined"
```
Should print nothing. The official "MSSQL <instance> General State" services should also
reappear on next discovery, and the HW/SW Inventory warning should clear.
