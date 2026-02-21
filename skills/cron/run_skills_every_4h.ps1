# Run skills in sequence every 4 hours via Task Scheduler or manual invocation
# This script runs the news_ingestor, moltbook, deadinternet, and self-improvement skills once in order.

$python = "python"
$base = "C:\Users\hn2_f\.nanobot\workspace\skills"

$cmds = @(
    "$python $base\news_ingestor\ingest_rss.py --once",
    "$python $base\moltbook\ingest.py --once",
    "$python $base\deadinternet\skill_deadinternet.py --heartbeat",
    "$python $base\self-improvement\ingest.py --process-new"
)

foreach ($c in $cmds) {
    Write-Output "Running: $c"
    try {
        & cmd /c $c
    } catch {
        Write-Output "Command failed: $c"
        Write-Output $_
    }
    Start-Sleep -Seconds 5
}

Write-Output "Skill sequence run completed at $(Get-Date -Format o)"
