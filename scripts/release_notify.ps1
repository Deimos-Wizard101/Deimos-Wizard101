param(
    [Parameter(Mandatory=$true)]
    [string]$WebhookUrl = "",
   
    [Parameter(Mandatory=$true)]
    [string]$VersionTag = "3.11.0",
   
    [Parameter(Mandatory=$true)]
    [string]$Repository = "https://github.com/Deimos-Wizard101/Deimos-Wizard101",
   
    [Parameter(Mandatory=$true)]
    [string]$ChangelogUrl = "",
   
    [Parameter(Mandatory=$true)]
    [string]$UserId = "263123145333014530"
)

Write-Host "Sending Discord notification for release $VersionTag..."

try {
    # Construct clean message with changelog link
    $content = "<@$UserId> A new release is out: **$VersionTag**`n" +
               "📦 Download: $Repository/releases/tag/$VersionTag`n" +
               "📋 Full Changelog: $ChangelogUrl"
    
    $payload = @{ content = $content } | ConvertTo-Json -Depth 2
    
    # Send the webhook
    Invoke-RestMethod -Uri $WebhookUrl -Method Post -Body $payload -ContentType "application/json"
    Write-Host "✅ Discord notification sent successfully"
    
} catch {
    Write-Error "❌ Failed to send Discord notification: $($_.Exception.Message)"
    exit 1
}