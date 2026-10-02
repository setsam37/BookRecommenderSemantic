# AWS deployment: Amazon EC2

This project uses **Amazon EC2**, with Docker on Amazon Linux 2023. A named Docker volume stores the Chroma index on the instance's encrypted EBS root disk. GitHub Actions runs Python tests, builds the container, checks the UI without API credentials, verifies index-volume persistence across container replacement, and validates the CloudFormation template on every push and pull request.

This is a single-instance demonstration deployment. The security group limits port 7860 to `AllowedCidr`; administration uses AWS Systems Manager Session Manager instead of SSH. The demo URL uses HTTP. Do not open it to the whole Internet; use an HTTPS reverse proxy or load balancer and application authentication before turning it into a public service. There is no automatic deployment from CI, so a push cannot silently provision paid AWS resources.

## Run with Docker locally

Install Docker Engine with Compose, or Docker Desktop. In the repository root:

```sh
cp .env.example .env
# Set the replacement OPENAI_API_KEY in .env, then:
docker compose up --build --detach
docker compose logs --follow recommender
```

On Windows PowerShell use `Copy-Item .env.example .env` for the first command. Open <http://127.0.0.1:7860>. The API key is passed only at runtime: the image build context allows only runtime source/data, and excludes `.env`, Git history, and local caches. The container runs as a non-root user.

The first search builds an index for 5,197 books using the paid OpenAI API. The `book-index` volume survives container restarts, replacement, and `docker compose down`. **Do not use `docker compose down --volumes` unless you intend to delete the index and pay to rebuild it.** The local index created outside Docker is not automatically copied into this volume.

## Deploy on AWS

Prerequisites: an AWS account with billing enabled; permissions to create EC2, security group, IAM role/instance profile, and CloudFormation resources; a public subnet with an Internet Gateway route; and a new OpenAI key. Keep every resource in the same AWS region. The template defaults to `t3.medium` and a 30 GiB encrypted gp3 disk. EC2, EBS, public IPv4, and OpenAI usage can incur charges; consult the AWS estimate before creating the stack.

1. In **Systems Manager → Parameter Store**, create `/book-recommender/openai-api-key` as **SecureString**, using the default `aws/ssm` encryption key, and save the replacement OpenAI key as its value. Keep it out of the template, Git, screenshots, and chat. A custom KMS key needs an additional scoped `kms:Decrypt` permission and key policy; the supplied template assumes the default key.
2. In **CloudFormation**, create a stack by uploading `deploy/aws-ec2.yaml`. Suggested stack name: `book-recommender`.
3. Choose the VPC and a public subnet in it. Set `AllowedCidr` to your current public IPv4 followed by `/32`. Supply the full 40-character Git commit SHA containing the reviewed Docker changes as `CodeCommit` (run `git rev-parse HEAD`). The revision must be published to GitHub so the instance can download it. Choose the instance size and review the estimated cost.
4. Acknowledge IAM-resource creation and create the stack. It creates an EC2 instance, encrypted root disk, restricted security group, and an instance role that can read only the specified key parameter plus the standard Session Manager permissions. No SSH port is opened.
5. Wait for the stack, then open its **Outputs → AppUrl**. Bootstrap continues after CloudFormation reports `CREATE_COMPLETE`; allow several minutes for package/image installation. If the page is unavailable, open the instance through **Session Manager**, then run:

```sh
sudo tail -n 80 /var/log/cloud-init-output.log
sudo docker ps
sudo docker logs --tail 80 book-recommender
curl --fail http://127.0.0.1:7860/
```

6. Submit a book description and check that recommendations appear. The first search can take several minutes while the index builds. Test a category and emotional tone. Restart the container with `sudo docker restart book-recommender`, then search again to verify that the existing index is reused.

The instance needs outbound Internet access to download dependencies/source, retrieve the SSM parameter, and call OpenAI. A private subnet or blocked outbound network will not work with this template. If your public IP changes, update `AllowedCidr`; if you stop and start EC2, its public IP can change, so read the new address from the EC2 console.

## Key rotation and updates

After changing the Parameter Store value, open Session Manager and refresh the root-owned runtime file, then recreate the container. These commands print no key; substitute your AWS region and the deployed commit SHA:

```sh
sudo -i
set -euo pipefail
cd /opt/book-recommender
umask 077
OPENAI_KEY=$(aws ssm get-parameter --name /book-recommender/openai-api-key --with-decryption --region YOUR_REGION --query Parameter.Value --output text)
test -n "$OPENAI_KEY"
test "$OPENAI_KEY" != None
printf 'OPENAI_API_KEY=%s\n' "$OPENAI_KEY" > .env
unset OPENAI_KEY
printf 'OPENAI_EMBEDDING_MODEL=text-embedding-3-small\n' >> .env
docker rm --force book-recommender
docker run --detach --name book-recommender --restart unless-stopped \
  --publish 7860:7860 --env-file .env \
  --mount source=book-index,target=/app/.cache/chroma \
  --security-opt no-new-privileges:true --cap-drop ALL \
  --log-opt max-size=10m --log-opt max-file=3 \
  book-recommender:DEPLOYED_COMMIT_SHA
exit
```

For code updates, build the reviewed revision on the same instance, then recreate the container with the existing volume. Updating `CodeCommit` in CloudFormation changes user data but does not automatically rerun bootstrap on the existing instance. Back up the index before replacing the instance; a new catalog or embedding model deliberately creates a different index.

## Evidence and cleanup

For the assignment, record the GitHub commit, successful **Tests** and **Container** workflow runs, AWS service (**Amazon EC2**), region, instance ID, app URL, and a screenshot showing real recommendations. Do not claim a live deployment from a template alone; record the URL and check it after deploying.

Stopping EC2 pauses compute billing but EBS storage still incurs charges, and stopping does not guarantee all related costs cease. For complete stack cleanup, back up anything needed, then delete the CloudFormation stack. **The root disk and index are deleted when the instance is terminated.** The separately created Parameter Store secret is outside the stack; delete it separately when no longer needed. Do not delete an account's shared VPC or subnet.

The optional custom REST API is not included; the existing Gradio UI is the assignment's deployed application.

References: [EC2 CloudFormation resource](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-ec2-instance.html), [Session Manager setup](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-getting-started.html), [Parameter Store](https://docs.aws.amazon.com/systems-manager/latest/userguide/systems-manager-parameter-store.html).
