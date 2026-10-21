# Checkmk agent plug-in: docker_cpu_normalized (Windows)
# Author: Marius Gielnik
# License: GNU General Public License v2 or later
#
# Windows variant. 'docker stats' on Windows already reports the CPU usage in
# percent of ALL host CPUs, so the value is converted to the Linux convention
# (100 % = one CPU core) before it is sent. Piggyback host names follow the
# option container_id of mk_docker.py (docker.cfg), default "short".
# Dependencies: docker CLI in PATH.

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { exit 0 }

$mode = 'short'
if ($env:MK_CONFDIR) {
    $cfg = Join-Path $env:MK_CONFDIR 'docker.cfg'
    if (Test-Path $cfg) {
        $m = Select-String -Path $cfg -Pattern '^\s*container_id\s*[:=]\s*(\S+)' | Select-Object -Last 1
        if ($m) { $mode = $m.Matches[0].Groups[1].Value }
    }
}

$hostCpus = 0
[void][int]::TryParse(((docker info --format '{{.NCPU}}' 2>$null) -join '').Trim(), [ref]$hostCpus)
if ($hostCpus -le 0) { $hostCpus = [Environment]::ProcessorCount }
$node = $env:COMPUTERNAME.ToLower()
$inv = [System.Globalization.CultureInfo]::InvariantCulture

docker stats --no-stream --format '{{.ID}};{{.CPUPerc}}' 2>$null | ForEach-Object {
    $id, $cpu = $_ -split ';', 2
    $cpu = ($cpu -replace '%', '').Trim()
    $pct = 0.0
    if (-not [double]::TryParse($cpu, [System.Globalization.NumberStyles]::Float, $inv, [ref]$pct)) { return }
    $info = (docker inspect --format '{{.Id}};{{.Name}};{{.HostConfig.NanoCpus}};{{.HostConfig.CpuQuota}};{{.HostConfig.CpuPeriod}};{{.HostConfig.CpuCount}}' $id 2>$null)
    if (-not $info) { return }
    $f = $info -split ';'
    $name = $f[1].TrimStart('/')
    switch ($mode) {
        'name'     { $target = $name }
        'long'     { $target = $f[0] }
        'combined' { $target = "${node}_$name" }
        default    { $target = $f[0].Substring(0, 12) }
    }
    $limit = 0.0
    if ([double]$f[2] -gt 0) { $limit = [double]$f[2] / 1e9 }
    elseif ([double]$f[3] -gt 0 -and [double]$f[4] -gt 0) { $limit = [double]$f[3] / [double]$f[4] }
    elseif ([double]$f[5] -gt 0) { $limit = [double]$f[5] }
    $raw = $pct * $hostCpus
    "<<<<$target>>>>"
    "<<<docker_cpu_normalized:sep(59)>>>"
    ('{0};{1};{2}' -f $raw.ToString('0.00', $inv), $hostCpus, $limit.ToString('0.000', $inv))
    "<<<<>>>>"
}
