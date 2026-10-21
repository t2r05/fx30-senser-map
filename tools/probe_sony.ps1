# read-only Sony camera USB probe (ASCII only, safe for PowerShell 5.1)
# usage: powershell -ExecutionPolicy Bypass -File probe_sony.ps1

Write-Output "=== Sony USB devices (VID_054C) ==="
$devs = Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue |
        Where-Object { $_.InstanceId -match 'VID_054C' }

if (-not $devs) {
    Write-Output "NO_SONY_DEVICE"
    return
}

foreach ($d in $devs) {
    $pidv = if ($d.InstanceId -match 'PID_([0-9A-Fa-f]{4})') { $Matches[1].ToUpper() } else { '----' }
    Write-Output "--------------------------------------------"
    Write-Output ("PID        : 0x" + $pidv)
    Write-Output ("Name       : " + $d.FriendlyName)
    Write-Output ("Class      : " + $d.Class)
    Write-Output ("Status     : " + $d.Status)

    $svc = Get-PnpDeviceProperty -InstanceId $d.InstanceId -KeyName 'DEVPKEY_Device_Service' -ErrorAction SilentlyContinue
    if ($svc) { Write-Output ("Service    : " + $svc.Data) }

    $bus = Get-PnpDeviceProperty -InstanceId $d.InstanceId -KeyName 'DEVPKEY_Device_BusReportedDeviceDesc' -ErrorAction SilentlyContinue
    if ($bus) { Write-Output ("BusDesc    : " + $bus.Data) }

    $cid = Get-PnpDeviceProperty -InstanceId $d.InstanceId -KeyName 'DEVPKEY_Device_CompatibleIds' -ErrorAction SilentlyContinue
    if ($cid) { Write-Output ("Compatible : " + ($cid.Data -join ' | ')) }

    $inf = Get-PnpDeviceProperty -InstanceId $d.InstanceId -KeyName 'DEVPKEY_Device_DriverInfPath' -ErrorAction SilentlyContinue
    if ($inf) { Write-Output ("DriverInf  : " + $inf.Data) }
}

Write-Output ""
Write-Output "=== verdict hints ==="
Write-Output "Class_08  => mass storage only (no vendor service channel)"
Write-Output "Class_06  => PTP / MTP (image class, may expose vendor extensions)"
Write-Output "Class_FF  => vendor specific (this is what a service channel looks like)"
