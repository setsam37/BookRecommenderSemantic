# Azure deployment: Azure Virtual Machines

The selected service is **Azure Virtual Machines**: an Ubuntu 24.04 Linux VM runs Docker, and its managed OS disk stores the Chroma index in a named volume. The disk persists across VM/container restarts. A managed identity reads only the selected OpenAI secret from Azure Key Vault. GitHub Actions runs app tests, builds the container, checks the UI without credentials, verifies volume persistence across container replacement, and compiles the Azure Bicep template on every push and pull request.

This is a single-VM demonstration in Azure public cloud. A network security group restricts port 7860 to your public IP range; SSH and other inbound ports are closed. Administration uses Azure **Run command**. The demo URL uses HTTP. Add HTTPS and application authentication before unrestricted public access. CI validates deployment but does not automatically create paid resources.

## Docker locally

Install Docker Engine with Compose or Docker Desktop. In the repository root:

```sh
cp .env.example .env
# Save your replacement OPENAI_API_KEY in .env, then:
docker compose up --build --detach
docker compose logs --follow recommender
```

On PowerShell use `Copy-Item .env.example .env` for the first command. Open <http://127.0.0.1:7860>. The image excludes `.env`, Git history, local caches, and notebooks, and runs as a non-root user. The key is passed only at runtime.

The first search embeds all 5,197 books through the paid OpenAI API. The `book-index` volume survives restarts, container replacement, and `docker compose down`. **`docker compose down --volumes` deletes the index and triggers rebuilding charges on the next search.** The existing index outside Docker is not automatically copied into this volume.

## Azure prerequisites

- An active subscription and permission to create a resource group, VM, networking, managed identity, and role assignment. Secret-scoped role assignment requires `Microsoft.Authorization/roleAssignments/write`; VM Contributor alone is insufficient.
- Azure CLI with Bicep, or Azure Cloud Shell in Bash mode. Choose a region and VM size allowed by your subscription. The template defaults to `Standard_B2s` and a 30 GiB Standard SSD managed OS disk.
- A dedicated resource group, an RBAC-enabled Key Vault in that group, and an existing secret named `openai-api-key`. The vault must allow the VM's outbound public-network access; private endpoints/restricted firewalls require additional networking.
- An SSH public key for the VM administrator, although SSH network access remains closed.

VM compute, managed disks, Standard public IPv4, Key Vault operations, and OpenAI usage can incur charges. Review the Azure estimate before creation. A free/student subscription does not guarantee that this configuration is free or available.

## Deploy

1. Sign in to Azure portal or run `az login`, then select your intended subscription. Create a dedicated resource group such as `book-recommender-rg` and an RBAC-enabled Key Vault with a globally unique name. In **Key Vault → Secrets**, save the replacement key as `openai-api-key`. Keep it out of chat, template parameters, shell history, and screenshots. Your account may need **Key Vault Secrets Officer** to create the secret; allow role changes to propagate.
2. Clone the repository and check out the reviewed deployment revision. While the PR is open, use its branch; `master` receives the files after merge. In Cloud Shell, generate a project-specific administrator SSH key if needed:

```sh
ssh-keygen -t rsa -b 3072 -f "$HOME/.ssh/book-recommender" -N ''
```

Do not overwrite an existing key. Keep the private key private; only the `.pub` file is a deployment input.

3. From the repository root, substitute your group, vault, and current public IPv4 CIDR (`YOUR_PUBLIC_IPV4/32`). `REVISION` must be a full, published Git commit containing the reviewed Docker deployment:

```sh
REVISION=$(git rev-parse HEAD)
az deployment group what-if --resource-group book-recommender-rg \
  --template-file deploy/azure-vm.bicep \
  --parameters allowedCidr=YOUR_PUBLIC_IPV4/32 codeCommit="$REVISION" \
    keyVaultName=YOUR_VAULT_NAME adminSshPublicKey="$(cat "$HOME/.ssh/book-recommender.pub")"
```

Review the resources and costs, then replace `what-if` with `create` using the same parameters. The template creates a VM, static public IP, network interface, network security group, virtual network, managed identity, and **Key Vault Secrets User** assignment scoped to that one secret. It does not create or overwrite the vault/secret. Password authentication is disabled; the private SSH key is not uploaded.

4. Read `appUrl` from deployment outputs. Deployment success does not mean cloud-init has finished installing Docker/building the image. Allow several minutes. Bootstrap retries identity/Key Vault access for approximately 10 minutes plus request time. Failed/empty key retrieval stops startup.
5. If the URL is unavailable, select the VM → **Run command → RunShellScript** and run:

```sh
tail -n 80 /var/log/cloud-init-output.log
docker ps
docker logs --tail 80 book-recommender
curl --fail http://127.0.0.1:7860/
```

Do not print `/opt/book-recommender/.env`. The URL is reachable only from your allowed IP. Submit a description, verify recommendations, then test a category and tone. Run `docker restart book-recommender` and search again to verify index reuse.

## Rotation, updates, and persistence

After changing the Key Vault secret, run this through Run command. Refresh must succeed before replacing the container; secrets are not printed:

```sh
set -euo pipefail
python3 /opt/book-recommender/azure_bootstrap.py --refresh-key
docker rm --force book-recommender
docker run --detach --name book-recommender --restart unless-stopped \
  --publish 7860:7860 --env-file /opt/book-recommender/.env \
  --mount source=book-index,target=/app/.cache/chroma \
  --security-opt no-new-privileges:true --cap-drop ALL \
  --log-opt max-size=10m --log-opt max-file=3 \
  book-recommender:DEPLOYED_COMMIT_SHA
```

Substitute the deployed commit SHA in the image tag. Updating template custom data does not rerun cloud-init on an existing VM. Build code updates on the same VM and recreate its container with the existing volume. Back up the disk/index before replacing or deleting the VM. Catalog/model changes deliberately create a new index. Update the NSG rule if your public IP changes.

## Evidence and cleanup

Record the published commit, successful **Tests** and **Container** workflows, service (**Azure Virtual Machines**), region, VM name, app URL, and a screenshot of real recommendations. A compiled template alone is not proof of a live deployment.

**Stop (deallocate)** the VM to stop compute billing; disks and static public IP can still incur charges. For full cleanup, back up anything needed, then delete the dedicated resource group and its project resources. The OS disk is configured for deletion with the VM, which deletes the index. Never delete a shared group/vault to clean up this demo. Key Vault soft-delete rules may retain a deleted vault.

The optional custom REST API is omitted; the deployed application is the existing Gradio UI.

References: [VM and Key Vault managed identity](https://learn.microsoft.com/en-us/azure/key-vault/general/tutorial-python-virtual-machine), [VM template reference](https://learn.microsoft.com/en-us/azure/templates/microsoft.compute/virtualmachines), [Key Vault RBAC](https://learn.microsoft.com/en-us/azure/key-vault/general/rbac-guide), [Bicep CLI](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/bicep-cli).
