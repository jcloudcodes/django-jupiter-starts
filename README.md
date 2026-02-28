######Run this command to get argocd temporary PWD
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d; echo
#Change Password Using ArgoCD CLI (Recommended) from mac or any where gke was created
argocd account update-password \
  --account admin \
  --current-password CURRENT_PASSWORD \
  --new-password NEW_STRONG_PASSWORD \
  --server argocd.jcloudcodes.com \
  --insecure
#option 2 For the jenkins account:
argocd account update-password \
  --account jenkins \
  --current-password CURRENT_PASSWORD \
  --new-password NEW_STRONG_PASSWORD \
  --server argocd.jcloudcodes.com \
  --insecure

#If You Forgot Admin Password (Reset Method)
#If admin password is lost, reset via Kubernetes secret.
#Step 1 — Patch secret to clear password, only when lost
kubectl -n argocd patch secret argocd-secret \
  -p '{"stringData": {"admin.password": "", "admin.passwordMtime": ""}}'

#Restart ArgoCD server
kubectl -n argocd rollout restart deployment argocd-server
#status after restart
kubectl -n argocd rollout status deployment argocd-server

#Now ArgoCD will regenerate a new initial admin password.
#Retrieve new password
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath="{.data.password}" | base64 -d; echo

#Disable Admin Account (Production Recommended)
#Once Jenkins account works, disable admin:
#Edit argocd-cm:
#data:
  admin.enabled: "false"

#Check Which Accounts Exist
argocd account list \
  --server argocd.jcloudcodes.com \
  --insecure

#generate token for jenkins
Step 3 — Generate token for Jenkins
argocd account generate-token \
  --account jenkins \
  --server argocd.jcloudcodes.com \
  --insecure

#Step 4 — Create Jenkins Credential (CLI Way)

  If you want to create it via Jenkins CLI (optional advanced):

  First download Jenkins CLI:
  curl -O http://jenkins.jcloudcodes.com/jnlpJars/jenkins-cli.jar

#Then create credential XML:
cat <<EOF > argocd-token.xml
<com.cloudbees.plugins.credentials.impl.StringCredentialsImpl>
  <scope>GLOBAL</scope>
  <id>argocd-token</id>
  <description>ArgoCD API Token</description>
  <secret>PASTE_TOKEN_HERE</secret>
</com.cloudbees.plugins.credentials.impl.StringCredentialsImpl>
EOF


#Then upload:
java -jar jenkins-cli.jar \
  -s http://jenkins.jcloudcodes.com \
  create-credentials-by-xml system::system::jenkins _ < argocd-token.xml

#Test From Jenkins Slave
argocd app list \
  --server argocd.jcloudcodes.com \
  --auth-token <PASTE_TOKEN_HERE> \
  --insecure


#!/usr/bin/env python3
"""
gce_services.py

Start/stop GCE instances (jenkins, jslave, sonar, nexus-box) and then
update Cloud DNS A records for jenkins/sonarqube/nexus using their *current*
public IPs.

Notes:
  - The server key "sonar" maps to the instance name "sonarqube".
  - Script does NOT crash if an instance is missing; it warns & skips.
  - DNS remove uses existing TTL from DNS (safer than assuming TTL=300).
  - Optional --map to override instance names without editing code.

Examples: start
  python3 gce_services.py start --all --sleep 60 --dns
  python3 gce_services.py start --servers jenkins jslave
  python3 gce_services.py start --servers sonarqube --dns
  python3 gce_services.py start --servers nexus-box --dns
Examples: stop
  python3 gce_services.py stop --all --sleep 60 --dns
  python3 gce_services.py stop --servers jenkins jslave
  python3 gce_services.py stop --servers sonarqube --dns
  python3 gce_services.py stop --servers nexus-box --dns
"""

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


# -----------------------------
# Config
# -----------------------------

@dataclass(frozen=True)
class ServerConfig:
    key: str
    name: str
    zone: str
    dns_name: Optional[str] = None  # if None, no DNS update for this instance

# ✅ FIX: this must be the *managed zone name* in Cloud DNS, not the domain.
# Your managed zone name is "jcloudcodes" (as shown in your Cloud DNS UI).
GCLOUD_DNS_ZONE = "jcloudcodes"

DNS_TTL = 300  # TTL we will set when adding the NEW record

BASE_SERVERS: Dict[str, ServerConfig] = {
    "jenkins": ServerConfig(key="jenkins", name="jenkins", zone="us-east1-b", dns_name="jenkins.jcloudcodes.com."),
    "jslave": ServerConfig(key="jslave", name="jslave", zone="us-east1-b", dns_name=None),  # no DNS requested
    # IMPORTANT: instance name is "sonarqube" (key stays "sonar" for CLI convenience)
    "sonar": ServerConfig(key="sonar", name="sonarqube", zone="us-east1-b", dns_name="sonarqube.jcloudcodes.com."),
    "nexus-box": ServerConfig(key="nexus-box", name="nexus-box", zone="us-east1-c", dns_name="nexus.jcloudcodes.com."),
}

# DNS names we will update (mapped to server key)
DNS_TARGETS: Dict[str, str] = {
    "jenkins.jcloudcodes.com.": "jenkins",
    "sonarqube.jcloudcodes.com.": "sonar",
    "nexus.jcloudcodes.com.": "nexus-box",
}


# -----------------------------
# Helpers
# -----------------------------

def run(cmd: List[str], check: bool = True, capture: bool = True) -> subprocess.CompletedProcess:
    """Run a command and return CompletedProcess."""
    return subprocess.run(
        cmd,
        check=check,
        text=True,
        capture_output=capture,
    )


def gcloud_json(cmd: List[str]) -> Tuple[Optional[object], Optional[str]]:
    """
    Run gcloud command that returns JSON.
    Returns: (parsed_json_or_None, error_message_or_None)
    Never raises for non-zero exit; caller decides.
    """
    cp = run(cmd + ["--format=json"], check=False, capture=True)
    if cp.returncode != 0:
        err = (cp.stderr or cp.stdout or "").strip()
        return None, err if err else f"gcloud failed with exit code {cp.returncode}"
    out = (cp.stdout or "").strip()
    if not out:
        return {}, None
    try:
        return json.loads(out), None
    except json.JSONDecodeError:
        return None, f"Failed to parse JSON output for command: {' '.join(cmd)}"


def is_not_found_error(err: str) -> bool:
    e = (err or "").lower()
    return ("was not found" in e) or ("not found" in e) or ("could not fetch resource" in e)


def get_instance_status(name: str, zone: str) -> Optional[str]:
    """Return instance status (RUNNING/TERMINATED/etc.) or None if not found/unreadable."""
    data, err = gcloud_json(["gcloud", "compute", "instances", "describe", name, "--zone", zone])
    if err:
        if is_not_found_error(err):
            print(f"[WARN] Instance not found: {name} ({zone}). Skipping.")
            return None
        print(f"[WARN] Failed to describe instance {name} ({zone}): {err}")
        return None

    if isinstance(data, dict):
        return data.get("status")
    return None


def start_or_stop_instances(action: str, servers: Dict[str, ServerConfig], server_keys: List[str]) -> None:
    """
    Start if action=start, stop if action=stop.
    Uses the instance status to avoid unnecessary calls.
    """
    assert action in ("start", "stop")

    for key in server_keys:
        cfg = servers[key]
        status = get_instance_status(cfg.name, cfg.zone)
        if not status:
            continue

        if action == "start":
            if status.upper() == "RUNNING":
                print(f"[OK] {cfg.name} already RUNNING ({cfg.zone}) - no action.")
                continue
            print(f"[ACTION] Starting {cfg.name} ({cfg.zone}) - current status={status}")
            cp = run(["gcloud", "compute", "instances", "start", cfg.name, "--zone", cfg.zone], check=False, capture=True)
            if cp.returncode == 0:
                print(f"[DONE] Start requested for {cfg.name}")
            else:
                err = (cp.stderr or cp.stdout or "").strip()
                print(f"[WARN] Failed to start {cfg.name} ({cfg.zone}): {err}")

        else:
            if status.upper() in ("TERMINATED", "STOPPED"):
                print(f"[OK] {cfg.name} already STOPPED/TERMINATED ({cfg.zone}) - no action.")
                continue
            print(f"[ACTION] Stopping {cfg.name} ({cfg.zone}) - current status={status}")
            cp = run(["gcloud", "compute", "instances", "stop", cfg.name, "--zone", cfg.zone], check=False, capture=True)
            if cp.returncode == 0:
                print(f"[DONE] Stop requested for {cfg.name}")
            else:
                err = (cp.stderr or cp.stdout or "").strip()
                print(f"[WARN] Failed to stop {cfg.name} ({cfg.zone}): {err}")


def get_public_ip(name: str, zone: str) -> Optional[str]:
    """Return the first external/public IPv4 for the instance, or None."""
    data, err = gcloud_json(["gcloud", "compute", "instances", "describe", name, "--zone", zone])
    if err:
        if is_not_found_error(err):
            print(f"[WARN] Instance not found while fetching IP: {name} ({zone}).")
            return None
        print(f"[WARN] Failed to describe instance for IP {name} ({zone}): {err}")
        return None

    if not isinstance(data, dict):
        return None

    nics = data.get("networkInterfaces", []) or []
    for nic in nics:
        access = nic.get("accessConfigs", []) or []
        for ac in access:
            ip = ac.get("natIP")
            if ip:
                return ip
    return None


def get_current_a_record(dns_name: str) -> Tuple[List[str], Optional[int]]:
    """
    Return (current A record rrdatas, ttl) for a name.
    """
    data, err = gcloud_json([
        "gcloud", "dns", "record-sets", "list",
        "--zone", GCLOUD_DNS_ZONE,
        "--name", dns_name,
        "--type", "A",
    ])
    if err:
        print(f"[WARN] Failed to read DNS record {dns_name}: {err}")
        return [], None

    if not isinstance(data, list) or not data:
        return [], None

    rrdatas = data[0].get("rrdatas", []) or []
    ttl = data[0].get("ttl")
    return list(rrdatas), int(ttl) if ttl is not None else None


def dns_transaction_start() -> bool:
    cp = run(["gcloud", "dns", "record-sets", "transaction", "start", "--zone", GCLOUD_DNS_ZONE],
             check=False, capture=True)
    if cp.returncode != 0:
        err = (cp.stderr or cp.stdout or "").strip()
        print(f"[WARN] Could not start DNS transaction: {err}")
        return False
    return True


def dns_transaction_abort() -> None:
    run(["gcloud", "dns", "record-sets", "transaction", "abort", "--zone", GCLOUD_DNS_ZONE],
        check=False, capture=True)


def dns_transaction_execute() -> bool:
    cp = run(["gcloud", "dns", "record-sets", "transaction", "execute", "--zone", GCLOUD_DNS_ZONE],
             check=False, capture=True)
    if cp.returncode != 0:
        err = (cp.stderr or cp.stdout or "").strip()
        print(f"[WARN] DNS transaction execute failed: {err}")
        return False
    return True


def dns_transaction_remove_a(dns_name: str, ip: str, ttl: int) -> bool:
    cp = run([
        "gcloud", "dns", "record-sets", "transaction", "remove",
        "--zone", GCLOUD_DNS_ZONE,
        "--name", dns_name,
        "--type", "A",
        "--ttl", str(ttl),
        ip,
    ], check=False, capture=True)
    if cp.returncode != 0:
        err = (cp.stderr or cp.stdout or "").strip()
        print(f"[WARN] Failed remove A {dns_name} -> {ip} (ttl={ttl}): {err}")
        return False
    return True


def dns_transaction_add_a(dns_name: str, ip: str) -> bool:
    cp = run([
        "gcloud", "dns", "record-sets", "transaction", "add",
        "--zone", GCLOUD_DNS_ZONE,
        "--name", dns_name,
        "--type", "A",
        "--ttl", str(DNS_TTL),
        ip,
    ], check=False, capture=True)
    if cp.returncode != 0:
        err = (cp.stderr or cp.stdout or "").strip()
        print(f"[WARN] Failed add A {dns_name} -> {ip} (ttl={DNS_TTL}): {err}")
        return False
    return True


def update_dns_for_targets(servers: Dict[str, ServerConfig]) -> None:
    """
    For jenkins/sonarqube/nexus:
      - print OLD IPs (and TTL) from DNS
      - fetch NEW public IP from instance
      - remove old A record(s) (if any) using the current TTL
      - add new A record using DNS_TTL
      - execute one transaction for all changes
    """
    plan: List[Tuple[str, List[str], int, str]] = []  # (dns_name, old_ips, ttl_to_use, new_ip)

    for dns_name, server_key in DNS_TARGETS.items():
        cfg = servers[server_key]
        old_ips, old_ttl = get_current_a_record(dns_name)
        ttl_to_use = old_ttl if old_ttl is not None else DNS_TTL
        new_ip = get_public_ip(cfg.name, cfg.zone)

        print(f"\n[DNS] {dns_name}")
        print(f"  OLD IP(s) from DNS: {old_ips if old_ips else 'None'}")
        print(f"  OLD TTL from DNS:   {old_ttl if old_ttl is not None else 'None'}")
        print(f"  NEW IP from instance {cfg.name} ({cfg.zone}): {new_ip if new_ip else 'None'}")

        if not new_ip:
            print(f"  [WARN] No public IP found for {cfg.name}. Skipping DNS update for {dns_name}.")
            continue

        if old_ips and len(old_ips) == 1 and old_ips[0] == new_ip:
            print("  [OK] DNS already matches instance IP. No change needed.")
            continue

        plan.append((dns_name, old_ips, ttl_to_use, new_ip))

    if not plan:
        print("\n[DNS] No DNS changes needed.")
        return

    dns_transaction_abort()  # clean any previous transaction
    if not dns_transaction_start():
        print("[WARN] Skipping DNS updates because transaction could not start.")
        return

    try:
        for dns_name, old_ips, ttl_to_use, new_ip in plan:
            for ip in old_ips:
                print(f"[DNS] Removing A {dns_name} -> {ip} (ttl={ttl_to_use})")
                dns_transaction_remove_a(dns_name, ip, ttl_to_use)

            print(f"[DNS] Adding   A {dns_name} -> {new_ip} (ttl={DNS_TTL})")
            dns_transaction_add_a(dns_name, new_ip)

        print("\n[DNS] Executing transaction...")
        if dns_transaction_execute():
            print("[DNS] Transaction executed successfully.")
        else:
            print("[DNS] Transaction failed; attempting abort.")
            dns_transaction_abort()
    except Exception as e:
        print(f"[ERROR] DNS transaction failed: {e}", file=sys.stderr)
        print("[DNS] Aborting transaction...", file=sys.stderr)
        dns_transaction_abort()
        raise


# -----------------------------
# CLI
# -----------------------------

def parse_map(items: Optional[List[str]]) -> Dict[str, str]:
    """Parse --map key=value entries."""
    mapping: Dict[str, str] = {}
    if not items:
        return mapping
    for item in items:
        if "=" not in item:
            print(f"[WARN] Ignoring invalid --map entry (expected key=value): {item}")
            continue
        k, v = item.split("=", 1)
        k = k.strip()
        v = v.strip()
        if not k or not v:
            print(f"[WARN] Ignoring invalid --map entry: {item}")
            continue
        mapping[k] = v
    return mapping


def build_servers_with_overrides(name_overrides: Dict[str, str]) -> Dict[str, ServerConfig]:
    """Apply --map overrides to instance names (not zones)."""
    servers: Dict[str, ServerConfig] = {}
    for key, cfg in BASE_SERVERS.items():
        new_name = name_overrides.get(key, cfg.name)
        servers[key] = ServerConfig(key=cfg.key, name=new_name, zone=cfg.zone, dns_name=cfg.dns_name)
    return servers


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Start/stop GCE servers and update Cloud DNS A records.")
    p.add_argument("action", choices=["start", "stop"], help="Whether to start or stop the instances.")

    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--all", action="store_true", help="Apply action to all servers.")
    g.add_argument(
        "--servers",
        nargs="+",
        choices=list(BASE_SERVERS.keys()),
        help="One or more servers: jenkins jslave sonar nexus-box",
    )

    p.add_argument("--sleep", type=int, default=45, help="Seconds to sleep after start/stop (default: 45).")
    p.add_argument("--dns", action="store_true", help="Update DNS A records for jenkins/sonarqube/nexus.")

    p.add_argument("--map", nargs="*", help="Override instance names: key=value (example: --map sonar=sonarqube).")

    return p.parse_args()


def main() -> int:
    args = parse_args()
    name_overrides = parse_map(args.map)
    servers = build_servers_with_overrides(name_overrides)

    server_keys = list(servers.keys()) if args.all else args.servers

    print(f"[INFO] Action={args.action}  Servers={server_keys}")
    if name_overrides:
        print(f"[INFO] Name overrides: {name_overrides}")

    start_or_stop_instances(args.action, servers, server_keys)

    if args.sleep and args.sleep > 0:
        print(f"\n[INFO] Sleeping for {args.sleep} seconds...")
        time.sleep(args.sleep)

    if args.dns:
        if args.action == "stop":
            print("\n[WARN] You requested --dns after stop. Instances may have no public IP. Proceeding anyway.\n")
        update_dns_for_targets(servers)

    print("\n[OK] Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
