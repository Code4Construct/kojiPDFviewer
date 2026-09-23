param([Parameter(Mandatory=$true)][string]$Path)
$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($env:VIRUSTOTAL_API_KEY)) { throw 'VIRUSTOTAL_API_KEY secret is required for release' }
$file = (Resolve-Path $Path).Path
$hash = (Get-FileHash $file -Algorithm SHA256).Hash.ToLowerInvariant()
$headers = @{ 'x-apikey' = $env:VIRUSTOTAL_API_KEY }
$uploadUrl = 'https://www.virustotal.com/api/v3/files'
if ((Get-Item $file).Length -gt 32MB) {
  $uploadUrl = (Invoke-RestMethod -Uri 'https://www.virustotal.com/api/v3/files/upload_url' -Headers $headers).data
}
if ((Get-Item $file).Length -gt 650MB) { throw 'MSI exceeds VirusTotal upload limit (650 MB)' }
$response = & curl.exe --fail --silent --show-error --request POST --url $uploadUrl --header "x-apikey: $env:VIRUSTOTAL_API_KEY" --form "file=@$file"
if ($LASTEXITCODE -ne 0) { throw 'VirusTotal upload failed' }
$analysisId = ($response | ConvertFrom-Json).data.id
if ([string]::IsNullOrWhiteSpace($analysisId)) { throw 'VirusTotal returned no analysis ID' }
for ($attempt = 0; $attempt -lt 30; $attempt++) {
  $analysis = Invoke-RestMethod -Uri "https://www.virustotal.com/api/v3/analyses/$analysisId" -Headers $headers
  if ($analysis.data.attributes.status -eq 'completed') {
    $stats = $analysis.data.attributes.stats
    if ($null -eq $stats) { throw 'VirusTotal returned no detection statistics' }
    if (([int]$stats.harmless + [int]$stats.undetected + [int]$stats.malicious + [int]$stats.suspicious) -eq 0) {
      throw 'VirusTotal returned no engine results; release blocked'
    }
    $url = "https://www.virustotal.com/gui/file/$hash/detection"
    Write-Host "VirusTotal: malicious=$($stats.malicious), suspicious=$($stats.suspicious), $url"
    if ([int]$stats.malicious -gt 0 -or [int]$stats.suspicious -gt 0) { throw 'VirusTotal detected the installer; release blocked' }
    exit 0
  }
  Start-Sleep -Seconds 20
}
throw 'VirusTotal analysis did not complete within 10 minutes; release blocked'
