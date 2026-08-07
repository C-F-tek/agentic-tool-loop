# ============================================================================
# Network Monitor & Firewall Block Tool - PowerShell Wrapper
# ============================================================================
# Questo script PowerShell avvia il tool Python di network monitoring
# e gestisce le regole firewall in modo integrato.
#
# Esegui come Administrator per scrivere regole firewall.
#
# Uso:
#   .\network_monitor_firewall.ps1 -Interface "Wi-Fi" -Duration 60
#   .\network_monitor_firewall.ps1 -Interface "Ethernet" -Duration 120 -Threshold 30
#   .\network_monitor_firewall.ps1 -ListRules
#   .\network_monitor_firewall.ps1 -RemoveRule "192.168.1.100"
# ============================================================================

[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$Interface,

    [Parameter(Position = 1)]
    [int]$Duration = 60,

    [Parameter(Position = 2)]
    [int]$Threshold = 20,

    [Parameter(Position = 3)]
    [int]$BlockDays = 120,

    [Parameter()]
    [switch]$ListRules,

    [Parameter()]
    [switch]$ShowStatus,

    [Parameter()]
    [string]$RemoveRule,

    [Parameter()]
    [string]$LogFile = "blocked_ips.json"
)

# ============================================================================
# Funzioni Helper
# ============================================================================

function Write-Header {
    param($Text)
    Write-Host ""
    Write-Host ("=" * 60) -ForegroundColor Cyan
    Write-Host "  $Text" -ForegroundColor Cyan
    Write-Host ("=" * 60) -ForegroundColor Cyan
    Write-Host ""
}

function Write-Info {
    param($Text)
    Write-Host "  [INFO] $Text" -ForegroundColor Yellow
}

function Write-Success {
    param($Text)
    Write-Host "  [OK] $Text" -ForegroundColor Green
}

function Write-Error {
    param($Text)
    Write-Host "  [ERROR] $Text" -ForegroundColor Red
}

function Write-Alert {
    param($Text)
    Write-Host "  [ALERT] $Text" -ForegroundColor Magenta
}

# ============================================================================
# Verifica privilegi Administrator
# ============================================================================

function Test-IsAdministrator {
    $currentUser = New-Object System.Security.Principal.WindowsPrincipal([System.Security.Principal.WindowsIdentity]::GetCurrent())
    return $currentUser.IsInRole([System.Security.Principal.WindowsBuiltInRole]::Administrator)
}

# ============================================================================
# Verifica dipendenze
# ============================================================================

function Test-ScapyInstalled {
    try {
        $result = python -c "import scapy; print('OK')" 2>&1
        if ($result.Contains("OK")) {
            return $true
        }
    } catch {
        return $false
    }
    return $false
}

function Test-PowerShellFirewallCmdlets {
    $cmdlets = Get-Command New-NetFirewallRule -ErrorAction SilentlyContinue
    return $null -ne $cmdlets
}

# ============================================================================
# Funzioni Firewall
# ============================================================================

function Get-FirewallBlockedRules {
    Write-Header "Regole Firewall di Blocco Attive"
    
    try {
        $rules = Get-NetFirewallRule | Where-Object { 
            $_.DisplayName -like "Block-*" 
        } | Select-Object DisplayName, Description, Enabled, Direction, Action
        
        if ($rules) {
            Write-Host ""
            Write-Host "  N° Regola | DisplayName | Stato | Direzione | Azione" -ForegroundColor White
            Write-Host "  " + ("-" * 70) -ForegroundColor Gray
            
            $i = 1
            foreach ($rule in $rules) {
                $state = if ($rule.Enabled) { "Attiva" } else { "Disattivata" }
                Write-Host "  $($i.ToString().PadRight(3)) | $($rule.DisplayName.PadRight(25)) | $state.PadRight(8) | $($rule.Direction).PadRight(8) | $($rule.Action)"
                $i++
            }
            
            Write-Host ""
            Write-Host "  Totali: $($rules.Count)" -ForegroundColor Yellow
        } else {
            Write-Info "Nessuna regola di blocco attiva."
        }
    } catch {
        Write-Error "Errore nel listare regole firewall: $_"
    }
}

function Remove-FirewallRuleByIP {
    param($TargetIP)
    
    Write-Header "Rimozione Regola Firewall per IP: $TargetIP"
    
    try {
        $pattern = "Block-$($TargetIP.Replace('.', '-'))-*"
        $rules = Get-NetFirewallRule | Where-Object { 
            $_.DisplayName -like $pattern 
        }
        
        if ($rules) {
            foreach ($rule in $rules) {
                Remove-NetFirewallRule -DisplayName $rule.DisplayName -Confirm:$false
                Write-Success "Regola rimossa: $($rule.DisplayName)"
            }
            Write-Success "Tutte le regole per $TargetIP rimosse."
        } else {
            Write-Info "Nessuna regola trovata per $TargetIP"
        }
    } catch {
        Write-Error "Errore nella rimozione: $_"
    }
}

# ============================================================================
# Main
# ============================================================================

Write-Host ""
Write-Host "  .:" -ForegroundColor Cyan
Write-Host "   ." -ForegroundColor Cyan
Write-Host "    Network Monitor & Firewall Block Tool" -ForegroundColor Cyan
Write-Host "" -ForegroundColor Cyan

# Gestione modalita'
if ($ListRules) {
    Get-FirewallBlockedRules
    exit 0
}

if ($RemoveRule) {
    Remove-FirewallRuleByIP -TargetIP $RemoveRule
    exit 0
}

# Verifica interfaccia
if (-not $Interface) {
    Write-Error "Devi specificare un'interfaccia con -Interface <nome>"
    Write-Info "Interfacce disponibili:"
    Get-NetAdapter | Select-Object Name, InterfaceDescription, Status | Format-Table
    exit 1
}

# Verifica interfaccia esista
$iface = Get-NetAdapter | Where-Object { $_.Name -like "*$Interface*" }
if (-not $iface) {
    Write-Error "Interfaccia '$Interface' non trovata."
    Write-Info "Interfacce disponibili:"
    Get-NetAdapter | Select-Object Name, InterfaceDescription, Status | Format-Table
    exit 1
}

Write-Info "Interfaccia selezionata: $Interface"
Write-Info "Durata cattura: $Duration secondi"
Write-Info "Soglia rilevamento: $Threshold"
Write-Info "Regole firewall: $BlockDays giorni di validita'"

# Verifica scapy
if (-not (Test-ScapyInstalled)) {
    Write-Error "scapy non installato."
    Write-Info "Esegui: pip install scapy"
    exit 1
}

Write-Success "scapy installato."

# Verifica privilegi per firewall
$isAdmin = Test-IsAdministrator
if (-not $isAdmin) {
    Write-Alert "Non sei in modalita' Administrator."
    Write-Alert "Le regole firewall potrebbero non essere scritte."
    Write-Info "Esegui PowerShell come Administrator per scrivere regole firewall."
} else {
    Write-Success "Modalita' Administrator attiva."
}

# Verifica cmdlets firewall
if (-not (Test-PowerShellFirewallCmdlets)) {
    Write-Error "Cmdlets NetFirewall non disponibili."
    Write-Info "Assicurati che il ruolo 'Firewall' sia installato su Windows."
    exit 1
}

Write-Success "Cmdlets firewall disponibili."

# Avvia cattura
Write-Header "Avvio Network Monitor"
Write-Info "Cattura pacchetti su '$Interface'..."
Write-Info "Premi Ctrl+C per interrompere."
Write-Host ""

try {
    # Costruisce comando Python
    $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    $pythonScript = Join-Path $scriptDir "network_monitor_firewall.py"
    
    # Verifica che lo script esista
    if (-not (Test-Path $pythonScript)) {
        Write-Error "Script Python non trovato: $pythonScript"
        exit 1
    }
    
    # Esegue script Python con argomenti
    Write-Info "Esecuzione: python $pythonScript -i $Interface -d $Duration -t $Threshold -b $BlockDays -l $LogFile"
    
    # Usa Call operator per eseguire con argomenti corretti
    $output = & python $pythonScript -i $Interface -d $Duration -t $Threshold -b $BlockDays -l $LogFile 2>&1
    
    Write-Host ""
    Write-Header "Riepilogo"
    
    Write-Success "Monitor completato."
    
    if ($output) {
        Write-Host ""
        Write-Host $output
    }
    
    # Mostra IP bloccati
    if (Test-Path $LogFile) {
        Write-Info "File log: $LogFile"
        $logData = Get-Content $LogFile | ConvertFrom-Json
        
        Write-Host ""
        Write-Host "  IP Bloccati:" -ForegroundColor White
        foreach ($ip in $logData.rules) {
            $status = if ($ip.success) { "[OK]" } else { "[FAIL]" }
            Write-Host "    $status $($ip.ip) -> $($ip.rule_name)"
        }
        
        Write-Host ""
        Write-Info "Per elencare regole firewall: .\network_monitor_firewall.ps1 -ListRules"
        Write-Info "Per rimuovere regola: .\network_monitor_firewall.ps1 -RemoveRule <IP>"
    }
    
} catch {
    Write-Error "Errore durante la cattura: $_"
    exit 1
}

Write-Host ""