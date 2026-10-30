# Configure this host's existing WXBridge-API task to run a hidden supervisor.
# This one-time installation affects only the current interactive Windows user.
param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('6v', 'noha')]
    [string] $Node,
    [Parameter(Mandatory=$true)]
    [string] $Bind
)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$pythonw = if ($Node -eq '6v') {
    Join-Path $root '.vendor\replica-db39\Scripts\pythonw.exe'
} else {
    Join-Path $root '.venv\Scripts\pythonw.exe'
}
$script = Join-Path $root 'tools\api_supervisor.py'
if (-not (Test-Path -LiteralPath $pythonw)) { throw 'missing_api_pythonw' }
if (-not (Test-Path -LiteralPath $script)) { throw 'missing_api_supervisor' }
if (-not (Test-Path -LiteralPath (Join-Path $root '.state\api-token.txt'))) {
    throw 'missing_api_token'
}
if ($Bind -notmatch '^100\.(6[4-9]|[7-9][0-9]|1[01][0-9]|12[0-7])\.\d{1,3}\.\d{1,3}$') {
    throw 'bind_must_be_tailscale_ip'
}
$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$action = New-ScheduledTaskAction -Execute $pythonw -Argument ('"{0}" --node {1} --bind {2}' -f $script, $Node, $Bind) -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([timespan]::Zero) -RestartCount 10 -RestartInterval (New-TimeSpan -Minutes 1) -StartWhenAvailable -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
$existing = Get-ScheduledTask -TaskName 'WXBridge-API' -ErrorAction SilentlyContinue
if ($null -ne $existing -and $existing.State -eq 'Running') {
    Stop-ScheduledTask -TaskName 'WXBridge-API' -ErrorAction Stop
    Start-Sleep -Seconds 2
}
Register-ScheduledTask -TaskName 'WXBridge-API' -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
Start-ScheduledTask -TaskName 'WXBridge-API'
Write-Output ('installed_supervisor_node=' + $Node)
Write-Output ('scheduled_task=' + (Get-ScheduledTask -TaskName 'WXBridge-API').State)
