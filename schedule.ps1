param([switch]$Remove)
$ErrorActionPreference = 'Stop'
$taskName = 'CreatorOS-DailySync'
if ($Remove) { Unregister-ScheduledTask -TaskName $taskName -Confirm:$false; exit }
$pythonPath = (Get-Command python -ErrorAction Stop).Source
$scriptPath = Join-Path $PSScriptRoot 'app\sync.py'
# Convert the Beijing 08:00 schedule to the machine's local time zone.
$beijing = [TimeZoneInfo]::FindSystemTimeZoneById('China Standard Time')
$beijingNow = [TimeZoneInfo]::ConvertTimeFromUtc([DateTime]::UtcNow, $beijing)
$beijingNext = [DateTime]::SpecifyKind($beijingNow.Date.AddHours(8), [DateTimeKind]::Unspecified)
$localTime = [TimeZoneInfo]::ConvertTime($beijingNext, $beijing, [TimeZoneInfo]::Local)
$action = New-ScheduledTaskAction -Execute $pythonPath -Argument ('"' + $scriptPath + '"') -WorkingDirectory $PSScriptRoot
$trigger = New-ScheduledTaskTrigger -Daily -At $localTime
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 5) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Description 'CreatorOS 北京时间每日08:00同步已配置的平台数据集'
