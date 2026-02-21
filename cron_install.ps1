# Cron install / Task Scheduler helper
# Use Task Scheduler to run ingest.py on a schedule, or use Windows Task Scheduler UI.
# Example PowerShell to create a scheduled task that runs every hour:
$action = New-ScheduledTaskAction -Execute "python" -Argument "C:\Users\hn2_f\.nanobot\workspace\skills\self-improvement\ingest.py"
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).Date -RepetitionInterval (New-TimeSpan -Minutes 60) -RepetitionDuration ([TimeSpan]::MaxValue)
Register-ScheduledTask -TaskName "nanobot_selfimprove_ingest" -Action $action -Trigger $trigger -Description "Hourly ingest for self-improvement skill"
