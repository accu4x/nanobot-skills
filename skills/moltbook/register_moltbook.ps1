param(
  [Parameter(Mandatory=$true)][string]$AgentName,
  [Parameter(Mandatory=$true)][string]$Description,
  [string]$Homepage = "https://fan-tasticshop.com",
  [string[]]$Tags = @("hockey","news","cards"),
  [string]$Visibility = "private"
)

Write-Host "Registering agent with Moltbook..."

$payload = @{
  name = $AgentName
  short_description = "$AgentName - daily headlines and search"
  description = $Description
  tags = $Tags
  homepage = $Homepage
  visibility = $Visibility
} | ConvertTo-Json -Depth 6

$uri = "https://www.moltbook.com/api/v1/agents/register"
$headers = @{ "Content-Type" = "application/json" }

try {
    # Use Invoke-RestMethod to post JSON and parse JSON response
    $resp = Invoke-RestMethod -Method Post -Uri $uri -Headers $headers -Body $payload -ErrorAction Stop

    if ($null -eq $resp) {
        Write-Error "No response from server."
        exit 1
    }

    # Expected fields: api_key, claim_url (may vary)
    $apiKey = $resp.api_key
    $claimUrl = $resp.claim_url

    if ($apiKey) {
        $credDir = Join-Path $env:USERPROFILE ".config\moltbook"
        if (-not (Test-Path $credDir)) { New-Item -ItemType Directory -Path $credDir -Force | Out-Null }

        $credPath = Join-Path $credDir "credentials.json"
        $creds = @{
           api_key = $apiKey
           agent_name = $AgentName
        } | ConvertTo-Json

        $creds | Out-File -FilePath $credPath -Encoding utf8

        Write-Host "Registration successful."
        Write-Host " - Credentials saved to: $credPath"
        if ($claimUrl) { Write-Host " - Claim URL: $claimUrl" }
        else { Write-Host " - No claim URL returned in response." }
    } else {
        Write-Warning "Registration response did not include an api_key. Raw response:"
        $resp | ConvertTo-Json | Write-Host
    }
}
catch {
    Write-Error "Failed to contact Moltbook. Exception:"
    Write-Error $_.Exception.Message
    if ($_.Exception.Response) {
        try {
            $body = $_.Exception.Response.GetResponseStream() | 
                   ForEach-Object { $_ } # no-op to access stream
        } catch {}
    }
    exit 1
}
