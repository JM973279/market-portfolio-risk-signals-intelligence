#!/usr/bin/env bash
# One-time setup for .github/workflows/deploy-lightsail.yml: lets GitHub Actions deploy the
# Lightsail service without storing any AWS key in GitHub (OIDC, 1-hour credentials).
#
# - Trust: only workflows on main of JM973279/market-portfolio-risk-signals-intelligence.
# - Permissions: Lightsail container image push/list/delete and deployment only (no other AWS service).
# Running it does not touch the current deployment. Safe to re-run.
# Prerequisite: AWS credentials in the environment (e.g. after `aws login`).
set -euo pipefail

REPO="${GITHUB_REPO:-JM973279/market-portfolio-risk-signals-intelligence}"
# The repository uses GitHub's immutable OIDC subject (owner and repository IDs), which keeps
# matching after a rename and never matches a re-created repository with the same name.
# Check with: gh api repos/$REPO/actions/oidc/customization/sub  (sub_claim_prefix)
SUB_PREFIX="${SUB_PREFIX:-repo:JM973279@310814418/market-portfolio-risk-signals-intelligence@1452353262}"
ROLE="${DEPLOY_ROLE:-mpri-github-lightsail-deploy}"
export AWS_REGION="${AWS_REGION:-ap-northeast-2}" AWS_DEFAULT_OUTPUT=text

account=$(aws sts get-caller-identity --query Account)
provider="arn:aws:iam::$account:oidc-provider/token.actions.githubusercontent.com"
if ! aws iam get-open-id-connect-provider --open-id-connect-provider-arn "$provider" >/dev/null 2>&1; then
  aws iam create-open-id-connect-provider --url https://token.actions.githubusercontent.com \
    --client-id-list sts.amazonaws.com --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1 >/dev/null
  echo "created OIDC provider token.actions.githubusercontent.com"
fi

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cat >"$work/trust.json" <<JSON
{"Version": "2012-10-17", "Statement": [{"Effect": "Allow",
  "Principal": {"Federated": "$provider"},
  "Action": "sts:AssumeRoleWithWebIdentity",
  "Condition": {"StringEquals": {
    "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
    "token.actions.githubusercontent.com:sub": "$SUB_PREFIX:ref:refs/heads/main"}}}]}
JSON
cat >"$work/policy.json" <<'JSON'
{"Version": "2012-10-17", "Statement": [{"Sid": "DeployMpriContainers", "Effect": "Allow",
  "Action": ["lightsail:GetContainerServices", "lightsail:GetContainerServiceDeployments",
             "lightsail:GetContainerImages", "lightsail:CreateContainerServiceRegistryLogin",
             "lightsail:RegisterContainerImage", "lightsail:CreateContainerServiceDeployment",
             "lightsail:DeleteContainerImage"],
  "Resource": "*"}]}
JSON

if aws iam get-role --role-name "$ROLE" >/dev/null 2>&1; then
  aws iam update-assume-role-policy --role-name "$ROLE" --policy-document "file://$work/trust.json"
else
  aws iam create-role --role-name "$ROLE" --max-session-duration 3600 \
    --description "GitHub Actions ($REPO main) deploys Lightsail mpri" \
    --assume-role-policy-document "file://$work/trust.json" >/dev/null
  echo "created role $ROLE"
fi
aws iam put-role-policy --role-name "$ROLE" --policy-name lightsail-mpri-deploy \
  --policy-document "file://$work/policy.json"

echo "Role ARN (set as the repository variable AWS_DEPLOY_ROLE_ARN):"
aws iam get-role --role-name "$ROLE" --query Role.Arn
