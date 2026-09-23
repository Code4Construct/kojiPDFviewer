param([Parameter(Mandatory=$true)][string]$Path)
$ErrorActionPreference = 'Stop'
$pfx = $env:WINDOWS_CODESIGN_PFX_BASE64
$password = $env:WINDOWS_CODESIGN_PASSWORD
if (!$pfx -and !$password) { Write-Warning 'Code signing secrets are absent; artifact remains unsigned'; exit 0 }
if (!$pfx -or !$password) { throw 'Both code signing secrets are required' }
$tool = Get-ChildItem 'C:\Program Files (x86)\Windows Kits\10\bin' -Recurse -Filter signtool.exe -ErrorAction SilentlyContinue |
  Where-Object { $_.FullName -like '*\x64\signtool.exe' } |
  Sort-Object FullName -Descending | Select-Object -First 1 -ExpandProperty FullName
if (!$tool) { throw 'signtool.exe was not found' }
$certificate = Join-Path $env:RUNNER_TEMP 'codesign.pfx'
try {
  [IO.File]::WriteAllBytes($certificate, [Convert]::FromBase64String($pfx))
  & $tool sign /f $certificate /p $password /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 $Path
  if ($LASTEXITCODE -ne 0) { throw "Signing failed: $Path" }
  $signature = Get-AuthenticodeSignature $Path
  if ($signature.Status -ne 'Valid') { throw "Signature is not valid: $($signature.Status)" }
} finally {
  Remove-Item $certificate -Force -ErrorAction SilentlyContinue
}
