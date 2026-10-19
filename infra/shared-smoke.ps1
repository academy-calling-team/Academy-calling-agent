$ErrorActionPreference = 'Stop'
$apiBase = 'https://team8-api.3.35.222.227.sslip.io/shared'
function Invoke-Utf8Json {
    param([string]$Uri, [string]$Method='GET', [hashtable]$Headers=@{}, [string]$Body)
    $requestArgs = @{ Uri=$Uri; Method=$Method; Headers=$Headers; UseBasicParsing=$true; TimeoutSec=15 }
    if ($PSBoundParameters.ContainsKey('Body')) {
        $requestArgs.ContentType = 'application/json; charset=utf-8'
        $requestArgs.Body = [System.Text.Encoding]::UTF8.GetBytes($Body)
    }
    $response = Invoke-WebRequest @requestArgs
    [System.Text.Encoding]::UTF8.GetString($response.RawContentStream.ToArray()) | ConvertFrom-Json
}
$suffix = [Guid]::NewGuid().ToString('N').Substring(0,10)
$credentials = @{ login_name = "pc_check_$suffix"; password = [Guid]::NewGuid().ToString('N') }
$body = $credentials | ConvertTo-Json -Compress
# 회원가입만 약관 동의를 받는다. 로그인 본문에 넣으면 422로 거부된다.
$registration = ($credentials + @{ terms_agreed = $true }) | ConvertTo-Json -Compress
Invoke-Utf8Json "$apiBase/auth/register" -Method Post -Body $registration | Out-Null
$session = Invoke-Utf8Json "$apiBase/auth/login" -Method Post -Body $body
$headers = @{ Authorization = "Bearer $($session.access_token)"; 'Idempotency-Key' = "pc-check-$suffix" }
try {
    $inquiry = @{ inquirer_id=$session.inquirer_id; academy_id='demo-academy'; student=@{grade='M2';subject='MATH';level='MID';region='대구 북구 침산동'};question_codes=@('shuttle','vacancy','class_time') }
    $created = Invoke-Utf8Json "$apiBase/api/inquiries" -Method Post -Headers $headers -Body ($inquiry | ConvertTo-Json -Depth 5 -Compress)
    Write-Host "Inquiry ID: $($created.inquiry_id)"
    $deadline = (Get-Date).AddSeconds(60)
    do {
        $detail = Invoke-Utf8Json "$apiBase/api/inquiries/$($created.inquiry_id)" -Headers $headers
        Write-Host "Status: $($detail.status)"
        if ($detail.status -eq 'completed') { break }
        if ($detail.status -eq 'failed') { throw 'Mock processing failed. Check server logs.' }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)
    if ($detail.status -ne 'completed' -or $detail.result.answers.Count -ne 3) { throw 'Shared mock workflow did not finish in 60 seconds.' }
    $detail.result.answers | Select-Object question_code,detail | Format-Table -AutoSize
    Write-Host 'PASS: this PC reached the shared API and received worker results.'
} finally {
    Invoke-Utf8Json "$apiBase/auth/logout" -Method Post -Headers $headers -Body '{}' | Out-Null
}
