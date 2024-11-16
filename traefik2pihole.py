import logging
import os
import re

import paramiko
import requests
from dotenv import load_dotenv
import sentry_sdk
from sentry_sdk.integrations.logging import LoggingIntegration

# Load the environment variables from the .env file
load_dotenv()

# Configure logging to log to both a file and stderr
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)

if os.getenv("SENTRY_DSN"):
    sentry_sdk.init(
        dsn=os.getenv("SENTRY_DSN"),
        integrations=[
            LoggingIntegration(
                level=logging.INFO,
                event_level=logging.INFO,
            ),
        ],
        traces_sample_rate=0.2,
        profiles_sample_rate=0.2,
    )

# Define the URL for the Traefik API endpoint
TRAEFIK_API_URL = os.getenv("TRAEFIK_API_URL", "")
# Load SSH credentials from environment variables
PIHOLE_HOST = os.getenv("PIHOLE_HOST", "")
PIHOLE_USER = os.getenv("PIHOLE_USER", "")
PIHOLE_KEY = os.getenv("PIHOLE_KEY", "")

if not PIHOLE_HOST or not PIHOLE_USER or not PIHOLE_KEY:
    logging.error("Missing environment variables for SSH connection.")
    exit(1)


def get_swarm_ip_addresses():
    try:
        swarm_manager = os.getenv("SWARM_MANAGER_IP", "")
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(swarm_manager, username=PIHOLE_USER, key_filename=PIHOLE_KEY)

        _, stdout, _ = ssh.exec_command("docker node ls --format '{{.Hostname}}'")
        node_names = stdout.read().decode().splitlines()

        ssh.close()
        ip_addresses = []
        for node_name in node_names:
            try:
                ssh.connect(node_name, username=PIHOLE_USER, key_filename=PIHOLE_KEY)
                _, stdout, _ = ssh.exec_command("hostname -I")
                ip_address = stdout.read().decode().split()[0]
                ip_addresses.append(ip_address)
                ssh.close()
                print("Added IP address: ", ip_address, " for node: ", node_name)
            except Exception as e:
                logging.error(f"Error connecting to SSH: {node_name} {e}")
                continue

        return ip_addresses

    except paramiko.SSHException as e:
        logging.error(f"Error connecting to SSH: {e}")
        return []


def get_hosts_for_entrypoint(entrypoint):
    try:
        # Send a GET request to the Traefik API
        response = requests.get(TRAEFIK_API_URL)
        response.raise_for_status()  # Raise an exception for HTTP errors

        routers = response.json()  # Parse JSON response

        hosts = set()
        fqdn_pattern = re.compile(r"^(?=.{1,253}$)(?:(?!-)[A-Za-z0-9-]{1,63}(?<!-)\.)+[A-Za-z]{2,6}$")

        # Iterate through routers to find those with the specified entrypoint
        for router in routers:
            if entrypoint in router.get("entryPoints", []):
                rule = router.get("rule", "")
                if rule.startswith("Host(`"):
                    # Extract hosts
                    rule_hosts = rule.split("`")[1::2]
                    # Filter FQDN hosts and add to set
                    fqdn_hosts = {host for host in rule_hosts if fqdn_pattern.match(host)}
                    hosts.update(fqdn_hosts)

        return list(hosts)

    except requests.exceptions.RequestException as e:
        logging.error(f"Error connecting to Traefik API: {e}")
        return []


def write_swarm_conf(hosts, ip_addresses):
    sorted_hosts = sorted(hosts)
    sorted_ips = sorted(ip_addresses, key=lambda ip: tuple(map(int, ip.split("."))))

    with open("99-swarm.conf", "w") as file:
        for host in sorted_hosts:
            for ip in sorted_ips:
                file.write(f"host-record={host},{ip}\n")


def upload_file_to_remote():
    try:
        # Check if the SSH key file exists
        if not os.path.exists(PIHOLE_KEY):
            raise FileNotFoundError(f"SSH key file '{PIHOLE_KEY}' not found.")

        # Load the SSH key from the file
        ssh_key = paramiko.Ed25519Key(filename=PIHOLE_KEY)
        logging.info("SSH key loaded successfully.")

        # Establish SSH connection
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        logging.info("Connecting to SSH host...")
        ssh.connect(PIHOLE_HOST, username=PIHOLE_USER, pkey=ssh_key)
        logging.info("SSH connection established.")

        # Use SFTP to check if the remote file exists and compare its content with the local file
        sftp = ssh.open_sftp()
        remote_file_path = "/etc/dnsmasq.d/99-swarm.conf"
        local_file_path = "99-swarm.conf"
        try:
            with sftp.open(remote_file_path, "r") as remote_file:
                remote_content = remote_file.read().decode()
            with open(local_file_path, "r") as local_file:
                local_content = local_file.read()
            if remote_content == local_content:
                logging.info("No changes detected in 99-swarm.conf. Skipping upload.")
                sftp.close()
                ssh.close()
                return
        except FileNotFoundError:
            logging.info("Remote file not found. Proceeding with upload.")

        # Upload the file if it is different or does not exist
        logging.info("Uploading file...")

        sftp.put(local_file_path, remote_file_path)
        sftp.close()
        logging.info("File uploaded successfully to /etc/dnsmasq.d/99-swarm.conf")

        # Run the pihole-FTL --test command on the remote host
        _, _, stderr = ssh.exec_command("pihole-FTL --test")
        error = stderr.read().decode()

        if "dnsmasq: syntax check OK." in error:
            print("Syntax check passed: dnsmasq: syntax check OK.")
            # Restart the pihole-FTL service
            _, _, stderr = ssh.exec_command("service pihole-FTL restart")
            restart_error = stderr.read().decode()
            if restart_error:
                logging.error(f"Service restart failed: {restart_error}")
            else:
                logging.info("Service restarted successfully.")
        else:
            logging.error(f"Syntax check failed: {error}")

        ssh.close()
    except FileNotFoundError as fnf_error:
        print(fnf_error)
    except paramiko.SSHException as ssh_error:
        logging.error(f"SSH error: {ssh_error}")
    except Exception as e:
        logging.error(f"Error uploading file: {e}")


if __name__ == "__main__":

    if os.path.exists("99-swarm.conf"):
        os.remove("99-swarm.conf")

    entry_point = "websecure"
    ip_address = get_swarm_ip_addresses()

    hosts = get_hosts_for_entrypoint(entry_point)
    other_hosts = os.getenv("OTHER_HOSTS", "")
    if other_hosts:
        other_hosts = other_hosts.split(",")
    else:
        other_hosts = []

    # merge hosts with other_hosts
    hosts = hosts + other_hosts
    # remove duplicates
    hosts = list(dict.fromkeys(hosts))

    if hosts:
        write_swarm_conf(hosts, ip_address)
        upload_file_to_remote()
    else:
        logging.error(f"No hosts found for entrypoint '{entry_point}'")
