# upload keys to swarm hosts
# questo va lanciato per avere la chiave sugli swarm in modo da poter lanciare dopo lo script


from dotenv import load_dotenv
import os
import paramiko

load_dotenv()

SSH_USER = "root"
PUBLIC_KEY_FILE = "ed25519_pihole.pub"

swarm_manager = os.getenv("SWARM_MANAGER_IP")
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(swarm_manager, username=SSH_USER)

_, stdout, _ = ssh.exec_command("docker node ls --format '{{.Hostname}}'")
node_names = stdout.read().decode().splitlines()

ssh.close()
ip_addresses = []
for node_name in node_names:
    ssh.connect(node_name, username=SSH_USER)
    # append public key to existing ~/.ssh/authorized_keys
    with open(PUBLIC_KEY_FILE, "r") as f:
        public_key = f.read()
    _, stdout, _ = ssh.exec_command(f"echo '{public_key}' >> ~/.ssh/authorized_keys")
    ssh.close()
    print(f"Uploaded key to {node_name}")
print("Upload complete")
