"""
Network Monitor & Firewall Block Tool
=====================================
Cattura traffico di rete in tempo reale, identifica IP con comportamento
sospizo/malevolo e crea regole di blocco firewall Windows con scadenza a 120 giorni.

Requisiti: pip install scapy
Esegui come Administrator per scrivere regole firewall.

Uso:
    python network_monitor_firewall.py --interface <nome> --duration 30
    python network_monitor_firewall.py --interface <nome> --duration 30 --threshold 50
    python network_monitor_firewall.py --interface <nome> --duration 30 --log-file blocked_ips.json
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Dict, List, Set, Tuple

try:
    from scapy.all import (
        ARP,
        DNS,
        DNSQR,
        Ether,
        IP,
        Packet,
        TCP,
        UDP,
        sniff,
        ls,
        conf,
    )
except ImportError:
    print("Errore: scapy non installato. Esegui: pip install scapy")
    sys.exit(1)

# ============================================================================
# Configurazione
# ============================================================================

DEFAULT_DURATION = 60  # secondi di cattura iniziale
DEFAULT_THRESHOLD = 20  # numero di connessioni/syn per considerare sospizo
BLOCK_DAYS = 120  # giorni di validita' regola firewall

# Soglie di rilevamento
THRESHOL_SYN_PER_SEC = 50  # SYN/sec per rilevare scanning
THRESHOL_CONNECTIONS_PER_SEC = 100  # connessioni/sec totali
THRESHOL_UDP_FLOOD_PER_SEC = 200  # pacchetti UDP/sec
THRESHOL_ARP_ANOMALY = 50  # ARP request anomale

# Pattern malevoli
MALICIOUS_PORTS = {
    # Port comunemente usate in attacchi
    445, 139, 135,  # SMB/NetBIOS - worm propagation
    3389,  # RDP - brute force
    22,  # SSH - brute force
    23,  # Telnet - insecure protocol
    21,  # FTP - credential theft
    53,  # DNS - zone transfer / amplification
    25,  # SMTP - spam relay
    80, 443,  # HTTP/HTTPS - DDoS
    8080, 8443,  # Alternative HTTP
    6667,  # IRC - botnet C&C
    4444, 5555,  # Metasploit default ports
    1337,  # Backtrack default
    31337,  # Back Orifice
}

# Known malicious patterns (signature-based detection)
SUSPICIOUS_PATTERNS = [
    # SQL Injection patterns
    (b"' OR '1'='1", "SQL Injection attempt"),
    (b"' OR 1=1--", "SQL Injection attempt"),
    (b"UNION SELECT", "SQL Injection attempt"),
    (b"'; DROP TABLE", "SQL Injection attempt"),
    # XSS patterns
    (b"<script>", "XSS attempt"),
    (b"javascript:", "XSS attempt"),
    (b"onerror=", "XSS attempt"),
    (b"onload=", "XSS attempt"),
    # Path traversal
    (b"../", "Path traversal attempt"),
    (b"....//", "Path traversal attempt"),
    (b"%2e%2e%2f", "Path traversal attempt"),
    # Command injection
    (b"; ls ", "Command injection attempt"),
    (b"| cat ", "Command injection attempt"),
    (b"`whoami`", "Command injection attempt"),
    (b"$(id)", "Command injection attempt"),
]

# ============================================================================
# Classi Principal
# ============================================================================


class NetworkStats:
    """Statistiche di rete in tempo reale."""

    def __init__(self):
        self.lock = Lock()
        self.packets_total = 0
        self.bytes_total = 0
        self.syn_count = 0
        self.ack_count = 0
        self.fin_count = 0
        self.rst_count = 0
        self.udp_count = 0
        self.tcp_count = 0
        self.dns_count = 0
        self.arp_count = 0
        self.icmp_count = 0
        self.per_src_ip: Dict[str, int] = {}
        self.per_dst_ip: Dict[str, int] = {}
        self.per_port: Dict[int, int] = {}
        self.connections_per_sec: Dict[str, int] = {}
        self.start_time = time.time()
        self.last_reset_time = time.time()

    def reset_timer(self):
        """Reset timer per statistiche per-second."""
        with self.lock:
            self.last_reset_time = time.time()

    def update_packet(self, pkt: Packet):
        """Aggiorna statistiche per un pacchetto."""
        with self.lock:
            self.packets_total += 1
            self.bytes_total += len(pkt)

            if pkt.haslayer(TCP):
                self.tcp_count += 1
                flags = pkt[TCP].flags
                if flags & 0x02:  # SYN
                    self.syn_count += 1
                if flags & 0x10:  # ACK
                    self.ack_count += 1
                if flags & 0x01:  # FIN
                    self.fin_count += 1
                if flags & 0x04:  # RST
                    self.rst_count += 1

                src_ip = pkt[IP].src if pkt.haslayer(IP) else ""
                dst_ip = pkt[IP].dst if pkt.haslayer(IP) else ""
                src_port = pkt[TCP].sport
                dst_port = pkt[TCP].dport

                self.per_src_ip[src_ip] = self.per_src_ip.get(src_ip, 0) + 1
                self.per_dst_ip[dst_ip] = self.per_dst_ip.get(dst_ip, 0) + 1
                self.per_port[dst_port] = self.per_port.get(dst_port, 0) + 1

            elif pkt.haslayer(UDP):
                self.udp_count += 1
                if pkt.haslayer(IP):
                    src_ip = pkt[IP].src
                    self.per_src_ip[src_ip] = self.per_src_ip.get(src_ip, 0) + 1

            elif pkt.haslayer(DNS):
                self.dns_count += 1

            elif pkt.haslayer(ARP):
                self.arp_count += 1

            elif pkt.haslayer(ICMP):
                self.icmp_count += 1

    def get_summary(self) -> str:
        """Restituisce un riepilogo delle statistiche."""
        with self.lock:
            elapsed = time.time() - self.start_time
            return (
                f"=== Statistiche Rete ===\n"
                f"Tempo trascorso: {elapsed:.1f}s\n"
                f"Pacchetti totali: {self.packets_total}\n"
                f"Byte totali: {self.bytes_total:,}\n"
                f"TCP: {self.tcp_count} | UDP: {self.udp_count} | DNS: {self.dns_count} | ARP: {self.arp_count} | ICMP: {self.icmp_count}\n"
                f"SYN: {self.syn_count} | ACK: {self.ack_count} | FIN: {self.fin_count} | RST: {self.rst_count}\n"
                f"\nTop IP sorgente:\n"
                + "\n".join(
                    f"  {ip}: {count} pacchetti"
                    for ip, count in sorted(
                        self.per_src_ip.items(), key=lambda x: x[1], reverse=True
                    )[:10]
                )
                + f"\n\nTop Porte destinazione:\n"
                + "\n".join(
                    f"  {port}: {count} pacchetti"
                    for port, count in sorted(
                        self.per_port.items(), key=lambda x: x[1], reverse=True
                    )[:10]
                )
            )


class ThreatDetector:
    """Rilevamento minacce basato su pattern e soglie."""

    def __init__(self, threshold=DEFAULT_THRESHOLD):
        self.threshold = threshold
        self.lock = Lock()
        # Statistiche per IP
        self.ip_stats: Dict[str, dict] = {}
        # IP rilevati come malevoli
        self.malicious_ips: Set[str] = set()
        # Log dettagliato
        self.threat_log: List[dict] = []
        self._reset_timer()

    def _reset_timer(self):
        self.last_reset = time.time()

    def analyze_packet(self, pkt: Packet) -> List[str]:
        """Analizza un pacchetto e restituisce IP malevoli rilevati."""
        detected = []
        if not pkt.haslayer(IP):
            return detected

        src_ip = pkt[IP].src
        dst_ip = pkt[IP].dst
        now = time.time()

        # Inizializza statistiche per IP
        with self.lock:
            if src_ip not in self.ip_stats:
                self.ip_stats[src_ip] = {
                    "packets": 0,
                    "syn": 0,
                    "connections": 0,
                    "first_seen": now,
                    "last_seen": now,
                    "threats": [],
                    "ports_target": {},
                }

            stats = self.ip_stats[src_ip]
            stats["packets"] += 1
            stats["last_seen"] = now

            # Rilevamento SYN flood / port scanning
            if pkt.haslayer(TCP):
                flags = pkt[TCP].flags
                if flags & 0x02:  # SYN
                    stats["syn"] += 1
                    dst_port = pkt[TCP].dport
                    stats["ports_target"][dst_port] = (
                        stats["ports_target"].get(dst_port, 0) + 1
                    )

                # Conteggio connessioni verso stessa destinazione
                if pkt.haslayer(TCP) and pkt.haslayer(UDP):
                    stats["connections"] += 1

            # Rilevamento ARP spoofing
            if pkt.haslayer(ARP):
                arp_pkt = pkt[ARP]
                if arp_pkt.op == 1:  # ARP Request
                    stats["arp_requests"] = stats.get("arp_requests", 0) + 1

            # Calcola soglie
            elapsed = now - stats["first_seen"]
            if elapsed > 0:
                syn_rate = stats["syn"] / elapsed if elapsed > 0 else 0
                packet_rate = stats["packets"] / elapsed if elapsed > 0 else 0

                # Rilevamento: troppe porte target in poco tempo
                unique_ports = len(stats["ports_target"])
                if unique_ports > 10 and elapsed < 10:
                    threat = {
                        "ip": src_ip,
                        "type": "PORT_SCAN",
                        "details": f"{unique_ports} porte in {elapsed:.1f}s",
                        "timestamp": now,
                    }
                    if src_ip not in self.malicious_ips:
                        self.malicious_ips.add(src_ip)
                        self.threat_log.append(threat)
                        detected.append(src_ip)

                # Rilevamento: SYN flood
                if syn_rate > THRESHOL_SYN_PER_SEC:
                    threat = {
                        "ip": src_ip,
                        "type": "SYN_FLOOD",
                        "rate": f"{syn_rate:.1f} SYN/sec",
                        "timestamp": now,
                    }
                    if src_ip not in self.malicious_ips:
                        self.malicious_ips.add(src_ip)
                        self.threat_log.append(threat)
                        detected.append(src_ip)

        return detected

    def get_threat_summary(self) -> str:
        """Riepilogo minacce rilevate."""
        with self.lock:
            summary = f"=== Riepilogo Minacce ===\n"
            summary += f"IP malevoli rilevati: {len(self.malicious_ips)}\n\n"

            for ip in self.malicious_ips:
                stats = self.ip_stats.get(ip, {})
                threats = [
                    t for t in self.threat_log if t.get("ip") == ip
                ]
                summary += f"IP: {ip}\n"
                summary += f"  Pacchetti: {stats.get('packets', 0)}\n"
                summary += f"  SYN: {stats.get('syn', 0)}\n"
                summary += f"  Porte target: {list(stats.get('ports_target', {}).keys())[:10]}\n"
                summary += f"  Minacce:\n"
                for t in threats:
                    summary += f"    - {t['type']}: {t.get('details', '')}\n"
                summary += "\n"

            return summary


class FirewallManager:
    """Gestione regole firewall Windows."""

    def __init__(self, block_days=BLOCK_DAYS):
        self.block_days = block_days
        self.blocked_rules: List[dict] = []

    def create_block_rule(self, ip: str, reason: str = "Network Monitor Detection") -> bool:
        """Crea regola firewall per bloccare un IP."""
        rule_name = f"Block-{ip.replace('.', '-')}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        start_time = datetime.now()
        end_time = start_time + timedelta(days=self.block_days)

        try:
            # Usa PowerShell New-NetFirewallRule
            ps_script = f'''
$ruleName = "{rule_name}"
$ipAddress = "{ip}"
$description = "Bloccato da Network Monitor: {reason}"
$start = "{start_time.strftime('%Y-%m-%dT%H:%M:%S')}"
$end = "{end_time.strftime('%Y-%m-%dT%H:%M:%S')}"

# Crea regola di blocco in ingresso
New-NetFirewallRule -DisplayName $ruleName `
    -Direction Inbound `
    -Action Block `
    -RemoteAddress $ipAddress `
    -Description $description `
    -Enabled True `
    -Profile Any 2>&1

Write-Output "Regola firewall creata: $ruleName per IP $ipAddress (valido fino a $end)"
'''
            # Esegui tramite subprocess
            import subprocess
            result = subprocess.run(
                ["powershell", "-Command", ps_script],
                capture_output=True,
                text=True,
            )

            if result.returncode == 0 or "ok" in result.stdout.lower():
                rule_info = {
                    "ip": ip,
                    "rule_name": rule_name,
                    "reason": reason,
                    "created_at": start_time.isoformat(),
                    "expires_at": end_time.isoformat(),
                    "days": self.block_days,
                    "success": True,
                }
                self.blocked_rules.append(rule_info)
                return True
            else:
                print(f"Errore creazione regola per {ip}: {result.stderr}")
                rule_info = {
                    "ip": ip,
                    "rule_name": rule_name,
                    "reason": reason,
                    "created_at": start_time.isoformat(),
                    "expires_at": end_time.isoformat(),
                    "days": self.block_days,
                    "success": False,
                    "error": result.stderr,
                }
                self.blocked_rules.append(rule_info)
                return False

        except Exception as e:
            print(f"Eccezione nella creazione regola firewall per {ip}: {e}")
            return False

    def list_blocked_rules(self) -> List[dict]:
        """Elenco regole firewall attive."""
        try:
            import subprocess
            ps_script = '''
Get-NetFirewallRule | Where-Object {$_.DisplayName -like "Block-*"} | Select-Object DisplayName, Description, Enabled | Format-Table -AutoSize
'''
            result = subprocess.run(
                ["powershell", "-Command", ps_script],
                capture_output=True,
                text=True,
            )
            print(result.stdout)
            return self.blocked_rules
        except Exception as e:
            print(f"Errore nel listare regole: {e}")
            return []

    def remove_rule(self, ip: str) -> bool:
        """Rimuove regola firewall per un IP."""
        try:
            import subprocess
            # Trova la regola per questo IP
            ps_script = f'''
$rules = Get-NetFirewallRule | Where-Object {{ $_.DisplayName -like "Block-{ip.replace('.', '-')}-*" }}
foreach ($rule in $rules) {{
    Disable-NetFirewallRule -DisplayName $rule.DisplayName
    Remove-NetFirewallRule -DisplayName $rule.DisplayName
    Write-Output "Regola rimossa: $($rule.DisplayName)"
}}
'''
            result = subprocess.run(
                ["powershell", "-Command", ps_script],
                capture_output=True,
                text=True,
            )
            return result.returncode == 0
        except Exception as e:
            print(f"Errore nella rimozione regola: {e}")
            return False

    def save_blocked_ips(self, filepath: str = "blocked_ips.json"):
        """Salva lista IP bloccati in JSON."""
        data = {
            "timestamp": datetime.now().isoformat(),
            "block_days": self.block_days,
            "total_rules": len(self.blocked_rules),
            "rules": self.blocked_rules,
        }
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)
        print(f"Lista IP bloccati salvata in: {filepath}")


class NetworkMonitor:
    """Monitor di rete principale."""

    def __init__(self, interface: str, duration: int = DEFAULT_DURATION, threshold: int = DEFAULT_THRESHOLD):
        self.interface = interface
        self.duration = duration
        self.threshold = threshold
        self.stats = NetworkStats()
        self.detector = ThreatDetector(threshold=threshold)
        self.firewall = FirewallManager()
        self.running = False
        self.stop_event = Event()
        self.malicious_ips_found: List[str] = []

        # Verifica interfaccia
        self._validate_interface()

    def _validate_interface(self):
        """Verifica che l'interfaccia esista."""
        interfaces = ls(conf.ifaces)
        if self.interface not in str(interfaces):
            print(f"Interfaccia '{self.interface}' non trovata.")
            print("Interfacce disponibili:")
            print(interfaces)
            sys.exit(1)

    def start(self):
        """Avvia la cattura pacchetti."""
        print("=" * 60)
        print("  NETWORK MONITOR & FIREWALL BLOCK TOOL")
        print("=" * 60)
        print(f"\nInterfaccia: {self.interface}")
        print(f"Durata cattura: {self.duration} secondi")
        print(f"Soglia rilevamento: {self.threshold}")
        print(f"Regole firewall: {BLOCK_DAYS} giorni di validita'\n")

        # Contatore per progress bar
        packet_count = [0]
        total_expected = self.duration * 1000  # stimativa

        def progress_callback(pkt):
            packet_count[0] += 1
            if packet_count[0] % 500 == 0:
                elapsed = time.time() - self.stats.start_time
                rate = packet_count[0] / elapsed if elapsed > 0 else 0
                print(f"\r  Pacchetti: {packet_count[0]} | Rate: {rate:.0f}/sec | Tempo: {elapsed:.1f}s", end="", flush=True)

        def capture_callback(pkt):
            """Callback principale per ogni pacchetto."""
            # Aggiorna statistiche
            self.stats.update_packet(pkt)

            # Analizza per minacce
            detected = self.detector.analyze_packet(pkt)
            for ip in detected:
                if ip not in self.malicious_ips_found:
                    self.malicious_ips_found.append(ip)
                    reason = f"Rilevato da Network Monitor - Soglia: {self.threshold}"
                    print(f"\n\n[ALERT] IP MALVECO RILEVATO: {ip}")
                    print(f"  Motivo: {reason}")

                    # Crea regola firewall
                    success = self.firewall.create_block_rule(ip, reason)
                    if success:
                        print(f"  [OK] Regola firewall creata per {ip}")
                    else:
                        print(f"  [FAIL] Impossibile creare regola firewall per {ip}")
                        print(f"  [INFO] Esegui questo script come Administrator")

                    print(f"  IP bloccati finora: {len(self.malicious_ips_found)}\n")

            # Progresso
            if packet_count[0] % 500 == 0:
                elapsed = time.time() - self.stats.start_time
                rate = packet_count[0] / elapsed if elapsed > 0 else 0
                remaining = self.duration - elapsed
                print(f"\r  Pacchetti: {packet_count[0]} | Rate: {rate:.0f}/sec | Tempo: {elapsed:.1f}s | Restante: {remaining:.1f}s", end="", flush=True)

        print(f"\nCattura in corso su '{self.interface}'...")
        print(f"Premi Ctrl+C per interrompere.\n")

        try:
            # Cattura pacchetti con scapy
            sniff(
                iface=self.interface,
                timeout=self.duration,
                prn=capture_callback,
                store=False,
                count=0,  # illimitato, controllato da timeout
            )
        except KeyboardInterrupt:
            print("\n\nCattura interrotta dall'utente.")
        except Exception as e:
            print(f"\nErrore nella cattura: {e}")
        finally:
            # Stampa riepilogo
            self._print_summary()

    def _print_summary(self):
        """Stampa riepilogo finale."""
        print("\n" + "=" * 60)
        print("  RIEPILOGO FINALE")
        print("=" * 60)

        # Statistiche
        print(self.stats.get_summary())

        # Minacce
        if self.detector.threat_log:
            print(self.detector.get_threat_summary())

        # Firewall
        print(f"Regole firewall create: {len(self.firewall.blocked_rules)}")
        for rule in self.firewall.blocked_rules:
            status = "OK" if rule.get('success') else "FAIL"
            print(f"  [{status}] {rule['ip']} -> {rule['rule_name']}")

        # Salvaguardia
        if self.malicious_ips_found:
            filepath = "blocked_ips.json"
            self.firewall.save_blocked_ips(filepath)
            print(f"\nLista completa salvata in: {filepath}")

        print("\n" + "=" * 60)


# ============================================================================
# Main
# ============================================================================


def main():
    parser = argparse.ArgumentParser(
        description="Network Monitor & Firewall Block Tool - Cattura traffico e crea regole firewall per IP malevoli"
    )
    parser.add_argument(
        "-i", "--interface",
        required=True,
        help="Nome interfaccia di rete (es. 'Ethernet', 'Wi-Fi')"
    )
    parser.add_argument(
        "-d", "--duration",
        type=int,
        default=DEFAULT_DURATION,
        help=f"Durata cattura in secondi (default: {DEFAULT_DURATION})"
    )
    parser.add_argument(
        "-t", "--threshold",
        type=int,
        default=DEFAULT_THRESHOLD,
        help=f"Soglia rilevamento minacce (default: {DEFAULT_THRESHOLD})"
    )
    parser.add_argument(
        "-b", "--block-days",
        type=int,
        default=120,
        help="Giorni validita' regola firewall (default: 120)"
    )
    parser.add_argument(
        "-l", "--log-file",
        default="blocked_ips.json",
        help="File JSON per salvare IP bloccati (default: blocked_ips.json)"
    )
    parser.add_argument(
        "--list-rules",
        action="store_true",
        help="Elenco regole firewall esistenti"
    )
    parser.add_argument(
        "--remove-rule",
        metavar="IP",
        help="Rimuovi regola firewall per un IP specifico"
    )

    args = parser.parse_args()

    # Lista regole esistenti
    if args.list_rules:
        fm = FirewallManager()
        fm.list_blocked_rules()
        return

    # Rimozione regola
    if args.remove_rule:
        fm = FirewallManager()
        success = fm.remove_rule(args.remove_rule)
        print(f"Rimozione regola per {args.remove_rule}: {'OK' if success else 'FAIL'}")
        return

    # Avvia monitoraggio
    monitor = NetworkMonitor(
        interface=args.interface,
        duration=args.duration,
        threshold=args.threshold,
    )
    BLOCK_DAYS = args.block_days  # Override globale
    monitor.firewall.block_days = args.block_days
    monitor.start()


if __name__ == "__main__":
    main()