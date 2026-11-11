<#
win_smb_shares.ps1 - Checkmk agent plug-in for Windows: SMB server share performance

Author:   Marius Gielnik
Project:  https://github.com/Majus420/checkmk/tree/main/MKP/windows_smb_share_performance
License:  GPL-2.0-or-later

Purpose:  Reads the raw performance counters of the object "SMB Server Shares"
          (latency per request type, average and current queue length,
          requests/s, throughput, open files and connections per share) and writes them as section <<<win_smb_shares>>>, plus the
          local path of every share (Win32_Share). Rates are computed on the
          Checkmk server, the plug-in only reads one snapshot per run.
Sources:  1. .NET System.Diagnostics.PerformanceCounter with the English counter
             names (.NET resolves English names on localized Windows, e.g. German
             "SMB-Serverfreigaben"). Same data as perfmon / Get-Counter.
          2. Fallback only if 1 fails: WMI Win32_PerfRawData_Counters_SMBServerShares.
             On some servers this class does not follow the real traffic (seen:
             0 requests in WMI while perfmon showed 1.6 requests/s), therefore the
             source is reported and shown in the service details.
Requires: Windows Server 2012 or newer (SMB 3), Windows PowerShell 2.0 or newer.
Deploy:   Agent Bakery rule "Windows: SMB share performance (agent plug-in)"
          or copy to C:\ProgramData\checkmk\agent\plugins\ by hand.
Test:     powershell -NoProfile -ExecutionPolicy Bypass -File win_smb_shares.ps1
Output:   <<<win_smb_shares:sep(9)>>>
          [source]<TAB>dotnet|wmi<TAB>detail
          [types]<TAB>Key=CounterType<TAB>...
          <Instance><TAB>Timestamp_PerfTime=..<TAB>Frequency_PerfTime=..<TAB>Timestamp_Sys100NS=..<TAB>Key=raw<TAB>Key_Base=raw...
          [share]<TAB><ShareName><TAB><LocalPath><TAB><Type>   (Win32_Share, optional)
          [error]<TAB>message     (no source worked, plug-in exits with 0)
#>

$ErrorActionPreference = 'Stop'

$Category = 'SMB Server Shares'
$WmiClass = 'Win32_PerfRawData_Counters_SMBServerShares'
# English counter name -> key in the section (keys = WMI property names)
$Counters = @(
    @('Avg. sec/Data Request', 'AvgsecPerDataRequest'),
    @('Avg. sec/Read', 'AvgsecPerRead'),
    @('Avg. sec/Write', 'AvgsecPerWrite'),
    @('Avg. sec/Request', 'AvgsecPerRequest'),
    @('Avg. Data Queue Length', 'AvgDataQueueLength'),
    @('Avg. Read Queue Length', 'AvgReadQueueLength'),
    @('Avg. Write Queue Length', 'AvgWriteQueueLength'),
    @('Current Data Queue Length', 'CurrentDataQueueLength'),
    @('Current Pending Requests', 'CurrentPendingRequests'),
    @('Data Requests/sec', 'DataRequestsPersec'),
    @('Read Requests/sec', 'ReadRequestsPersec'),
    @('Write Requests/sec', 'WriteRequestsPersec'),
    @('Metadata Requests/sec', 'MetadataRequestsPersec'),
    @('Data Bytes/sec', 'DataBytesPersec'),
    @('Read Bytes/sec', 'ReadBytesPersec'),
    @('Write Bytes/sec', 'WriteBytesPersec'),
    @('Current Open File Count', 'CurrentOpenFileCount'),
    @('Tree Connect Count', 'TreeConnectCount')
)
$BaseTypes = @(805438464, 1073874176)  # PERF_AVERAGE_TIMER, PERF_AVERAGE_BULK: need the base value

try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false) } catch { }

function Format-Value($v) {
    return ([Convert]::ToString($v, [Globalization.CultureInfo]::InvariantCulture))
}

function Clean([string]$s) {
    return ($s -replace '[\t\r\n]+', ' ')
}

function Add-Sample($result, [string]$instance, [string]$key, $sample) {
    if ([string]::IsNullOrEmpty($instance)) { return }
    $type = [int]$sample.CounterType
    $result.Types[$key] = $type
    if (-not $result.Rows.ContainsKey($instance)) {
        $result.Order += $instance
        $result.Rows[$instance] = @{
            'Timestamp_PerfTime' = $sample.TimeStamp
            'Frequency_PerfTime' = $sample.CounterFrequency
            'Timestamp_Sys100NS' = $sample.TimeStamp100nSec
        }
    }
    $row = $result.Rows[$instance]
    $row[$key] = $sample.RawValue
    if ($BaseTypes -contains $type) { $row[$key + '_Base'] = $sample.BaseValue }
}

function Read-DotNet {
    $result = @{ Source = 'dotnet'; Detail = ''; Types = @{}; Rows = @{}; Order = @() }
    if (-not [System.Diagnostics.PerformanceCounterCategory]::Exists($Category)) {
        throw "performance counter category '$Category' not found"
    }
    $cat = New-Object System.Diagnostics.PerformanceCounterCategory($Category)
    $instances = @($cat.GetInstanceNames())

    # fast path: all counters and instances in one read
    $data = $null
    try { $data = $cat.ReadCategory() } catch { $data = $null }
    $mode = 'readcategory'
    foreach ($c in $Counters) {
        $en = $c[0]; $key = $c[1]
        if ($null -ne $data -and $data.Contains($en)) {
            $coll = $data[$en]
            foreach ($k in @($coll.Keys)) {
                $item = $coll[$k]
                Add-Sample $result ([string]$item.InstanceName) $key $item.Sample
            }
        }
        else {
            # slow path: one counter object per instance (English name lookup by .NET)
            $mode = 'counters'
            foreach ($i in $instances) {
                try {
                    $pc = New-Object System.Diagnostics.PerformanceCounter($Category, $en, $i, $true)
                    try { Add-Sample $result $i $key $pc.NextSample() } finally { $pc.Dispose() }
                }
                catch { }
            }
        }
    }
    if ($result.Order.Count -eq 0 -and $instances.Count -gt 0) {
        throw "no counter of '$Category' could be read"
    }
    $result.Detail = $mode
    return $result
}

function Read-Wmi {
    $result = @{ Source = 'wmi'; Detail = ''; Types = @{}; Rows = @{}; Order = @() }
    $types = @{}
    if (Get-Command -Name Get-CimClass -ErrorAction SilentlyContinue) {
        $cls = Get-CimClass -Namespace 'root\cimv2' -ClassName $WmiClass
        foreach ($p in $cls.CimClassProperties) {
            $q = $p.Qualifiers['CounterType']
            if ($null -ne $q) { $types[$p.Name] = [int]$q.Value }
        }
        $instances = @(Get-CimInstance -Namespace 'root\cimv2' -ClassName $WmiClass)
    }
    else {
        $cls = [wmiclass]"root\cimv2:$WmiClass"
        foreach ($p in $cls.Properties) {
            try { $types[$p.Name] = [int]$p.Qualifiers['CounterType'].Value } catch { }
        }
        $instances = @(Get-WmiObject -Namespace 'root\cimv2' -Class $WmiClass)
    }
    foreach ($c in $Counters) {
        if ($types.ContainsKey($c[1])) { $result.Types[$c[1]] = $types[$c[1]] }
    }
    foreach ($inst in $instances) {
        $name = [string]$inst.Name
        if ([string]::IsNullOrEmpty($name)) { continue }
        $row = @{}
        foreach ($n in @('Timestamp_PerfTime', 'Frequency_PerfTime', 'Timestamp_Sys100NS')) {
            if ($null -ne $inst.$n) { $row[$n] = $inst.$n }
        }
        foreach ($key in @($result.Types.Keys)) {
            if ($null -ne $inst.$key) { $row[$key] = $inst.$key }
            $b = $key + '_Base'
            if ($null -ne $inst.$b) { $row[$b] = $inst.$b }
        }
        $result.Order += $name
        $result.Rows[$name] = $row
    }
    return $result
}

Write-Output '<<<win_smb_shares:sep(9)>>>'

$result = $null
$errors = @()
try { $result = Read-DotNet } catch { $errors += ('dotnet: ' + $_.Exception.Message) }
if ($null -eq $result) {
    try { $result = Read-Wmi } catch { $errors += ('wmi: ' + $_.Exception.Message) }
}
if ($null -eq $result) {
    Write-Output ("[error]`t" + (Clean ($errors -join ' | ')).Trim())
    exit 0
}

Write-Output ("[source]`t" + $result.Source + "`t" + (Clean ((@($result.Detail) + $errors) -join ' | ')).Trim())

$typeParts = @('[types]')
foreach ($c in $Counters) {
    if ($result.Types.ContainsKey($c[1])) { $typeParts += ($c[1] + '=' + (Format-Value $result.Types[$c[1]])) }
}
Write-Output ($typeParts -join "`t")

$fieldOrder = @('Timestamp_PerfTime', 'Frequency_PerfTime', 'Timestamp_Sys100NS')
foreach ($c in $Counters) { $fieldOrder += $c[1]; $fieldOrder += ($c[1] + '_Base') }
foreach ($name in $result.Order) {
    $row = $result.Rows[$name]
    $parts = @((Clean $name))
    foreach ($f in $fieldOrder) {
        if ($row.ContainsKey($f) -and $null -ne $row[$f]) { $parts += ($f + '=' + (Format-Value $row[$f])) }
    }
    Write-Output ($parts -join "`t")
}

# share name -> local path (optional, failures never break the section)
try {
    if (Get-Command -Name Get-CimInstance -ErrorAction SilentlyContinue) {
        $shares = @(Get-CimInstance -Namespace 'root\cimv2' -ClassName Win32_Share)
    }
    else {
        $shares = @(Get-WmiObject -Namespace 'root\cimv2' -Class Win32_Share)
    }
    foreach ($s in $shares) {
        $sn = [string]$s.Name
        if ([string]::IsNullOrEmpty($sn)) { continue }
        $line = @('[share]', (Clean $sn), (Clean ([string]$s.Path)), (Format-Value $s.Type))
        Write-Output ($line -join "`t")
    }
}
catch { }
exit 0
