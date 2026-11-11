#!/usr/bin/env bash
# Push the locally built web and portfolio images to one Lightsail container service and deploy them.
# Prerequisites: AWS credentials in the environment (AWS_PROFILE after `aws login`, or exported
# AWS_ACCESS_KEY_ID/...), the lightsailctl plugin, and images built with
#   docker compose -f infra/aws/compose.yaml build
# Creating the service starts monthly billing, so the first run needs CREATE_SERVICE=yes.
set -euo pipefail

REGION="${AWS_REGION:-ap-northeast-2}"
SERVICE="${LIGHTSAIL_SERVICE:-mpri}"
POWER="${LIGHTSAIL_POWER:-micro}"

# No --profile here: an explicit profile would make the CLI ignore exported credentials.
lightsail() { aws lightsail --region "$REGION" "$@"; }
# tr: the Windows CLI ends text output with CRLF, which would break the state comparisons below.
service_field() { lightsail get-container-services --service-name "$SERVICE" --query "containerServices[0].$1" --output text | tr -d '\r'; }

wait_for_state() {
  for _ in $(seq 1 60); do
    state="$(service_field state)"
    echo "service state: $state"
    [ "$state" = "$1" ] && return 0
    sleep 20
  done
  echo "service did not reach $1" >&2
  return 1
}

push() {
  # lightsailctl prints: Refer to this image as ":<service>.<label>.<n>" in deployments.
  lightsail push-container-image --service-name "$SERVICE" --label "$1" --image "$2" \
    | tee /dev/stderr | { grep -o '":[^"]*"' || true; } | tr -d '"' | tail -1
}

if ! lightsail get-container-services --service-name "$SERVICE" >/dev/null 2>&1; then
  if [ "${CREATE_SERVICE:-}" != "yes" ]; then
    echo "Container service '$SERVICE' does not exist in $REGION. Re-run with CREATE_SERVICE=yes to create it (billed monthly)." >&2
    exit 1
  fi
  lightsail create-container-service --service-name "$SERVICE" --power "$POWER" --scale 1 >/dev/null
  wait_for_state READY
fi

api_image="$(push api mqs-api:local)"
web_image="$(push web mqs-web:local)"
if [ -z "$api_image" ] || [ -z "$web_image" ]; then
  echo "could not read the pushed image names" >&2
  exit 1
fi

containers="$(mktemp)"
endpoint="$(mktemp)"
trap 'rm -f "$containers" "$endpoint"' EXIT
cat >"$containers" <<JSON
{
  "api": {"image": "$api_image", "ports": {"3108": "HTTP"}},
  "web": {"image": "$web_image", "ports": {"3000": "HTTP"}}
}
JSON
cat >"$endpoint" <<JSON
{
  "containerName": "web",
  "containerPort": 3000,
  "healthCheck": {"path": "/", "intervalSeconds": 10, "timeoutSeconds": 5,
                  "healthyThreshold": 2, "unhealthyThreshold": 3, "successCodes": "200-399"}
}
JSON

version="$(lightsail create-container-service-deployment --service-name "$SERVICE" \
  --containers "file://$containers" --public-endpoint "file://$endpoint" \
  --query containerService.nextDeployment.version --output text | tr -d '\r')"
echo "deploying version $version"
# A failed deployment leaves the previous one active, so success means this version became current.
for _ in $(seq 1 60); do
  sleep 20
  [ "$(service_field currentDeployment.version)" = "$version" ] && break
  if [ "$(service_field nextDeployment)" = "None" ]; then
    echo "deployment $version failed; check the container logs in the Lightsail console" >&2
    exit 1
  fi
  echo "still deploying version $version"
done
[ "$(service_field currentDeployment.version)" = "$version" ] || { echo "deployment $version timed out" >&2; exit 1; }
echo "deployment $version: $(service_field currentDeployment.state)"
echo "url: $(service_field url)"
