import os
import re

import paramiko
import requests
from dotenv import load_dotenv

# Load the environment variables from the .env file
load_dotenv()

# Define the URL for the Traefik API endpoint
TRAEFIK_API_URL = os.getenv("TRAEFIK_API_URL")
# Load the IP addresses from the environment variable
IP_ADDRESSES = os.getenv("SWARM_IP_ADDRESSES").split(",")
# Load SSH credentials from environment variables
SSH_HOST = "192.168.2.2"
SSH_USER = os.getenv("SSH_USER")
SSH_KEY_FILE = "ed25519_pihole"


def get_hosts_for_entrypoint(entrypoint):
    try:
        # Send a GET request to the Traefik API
        response = requests.get(TRAEFIK_API_URL)
        response.raise_for_status()  # Raise an exception for HTTP errors

        routers = response.json()  # Parse JSON response

        hosts = set()
        fqdn_pattern = re.compile(
            r"^(?=.{1,253}$)(?:(?!-)[A-Za-z0-9-]{1,63}(?<!-)\.)+[A-Za-z]{2,6}$"
        )

        # Iterate through routers to find those with the specified entrypoint
        for router in routers:
            if entrypoint in router.get("entryPoints", []):
                rule = router.get("rule", "")
                if rule.startswith("Host(`"):
                    # Extract hosts
                    rule_hosts = rule.split("`")[1::2]
                    # Filter FQDN hosts and add to set
                    fqdn_hosts = {
                        host for host in rule_hosts if fqdn_pattern.match(host)
                    }
                    hosts.update(fqdn_hosts)

        return list(hosts)

    except requests.exceptions.RequestException as e:
        print(f"Error connecting to Traefik API: {e}")
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
        if not os.path.exists(SSH_KEY_FILE):
            raise FileNotFoundError(f"SSH key file '{SSH_KEY_FILE}' not found.")

        # Load the SSH key from the file
        ssh_key = paramiko.Ed25519Key(filename=SSH_KEY_FILE)
        print("SSH key loaded successfully.")

        # Establish SSH connection
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        print("Connecting to SSH host...")
        ssh.connect(SSH_HOST, username=SSH_USER, pkey=ssh_key)
        print("SSH connection established.")

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
                print("No changes detected in 99-swarm.conf. Skipping upload.")
                sftp.close()
                ssh.close()
                return
        except FileNotFoundError:
            print("Remote file not found. Proceeding with upload.")

        # Upload the file if it is different or does not exist
        print("Uploading file...")
        sftp.put(local_file_path, remote_file_path)
        sftp.close()
        print("File uploaded successfully to /etc/dnsmasq.d/99-swarm.conf")

        # Run the pihole-FTL --test command on the remote host
        _, _, stderr = ssh.exec_command("pihole-FTL --test")
        error = stderr.read().decode()

        if "dnsmasq: syntax check OK." in error:
            print("Syntax check passed: dnsmasq: syntax check OK.")
            # Restart the pihole-FTL service
            _, _, stderr = ssh.exec_command("service pihole-FTL restart")
            restart_error = stderr.read().decode()
            if restart_error:
                print(f"Service restart failed: {restart_error}")
            else:
                print("Service restarted successfully.")
        else:
            print(f"Syntax check failed: {error}")

        ssh.close()
    except FileNotFoundError as fnf_error:
        print(fnf_error)
    except paramiko.SSHException as ssh_error:
        print(f"SSH error: {ssh_error}")
    except Exception as e:
        print(f"Error uploading file: {e}")


if __name__ == "__main__":
    entry_point = "websecure"
    hosts = get_hosts_for_entrypoint(entry_point)

    if hosts:
        write_swarm_conf(hosts, IP_ADDRESSES)
        upload_file_to_remote()
    else:
        print(f"No hosts found for entrypoint '{entry_point}'")
