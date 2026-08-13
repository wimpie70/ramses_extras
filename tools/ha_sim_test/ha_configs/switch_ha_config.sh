#!/usr/bin/env bash
# Switch ha-sim between "minimal" (fast testing) and "full" (normal use) configs.
#
# Usage:
#   ./switch_ha_config.sh minimal   # strip down for ha_sim_test
#   ./switch_ha_config.sh full      # restore all integrations + packages
#
# Restarts the container after switching.

set -euo pipefail

PROFILE="${1:-minimal}"
CONTAINER="${2:-ha-sim}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

case "$PROFILE" in
  minimal|full) ;;
  *)
    echo "Usage: $0 <minimal|full> [container-name]"
    echo "  minimal  — strip to essential integrations for fast ha_sim_test runs"
    echo "  full     — restore all integrations, packages, and features"
    exit 1
    ;;
esac

echo "Switching $CONTAINER to '$PROFILE' config..."

# Copy configuration.yaml
docker cp "$SCRIPT_DIR/configuration.$PROFILE.yaml" "$CONTAINER:/config/configuration.yaml"
echo "  configuration.$PROFILE.yaml → /config/configuration.yaml"

# Copy core.config_entries
docker cp "$SCRIPT_DIR/core.config_entries.$PROFILE.json" "$CONTAINER:/config/.storage/core.config_entries"
echo "  core.config_entries.$PROFILE.json → /config/.storage/core.config_entries"

# Handle zone_testing_package.yaml
if [ "$PROFILE" = "full" ]; then
  docker cp "$SCRIPT_DIR/zone_testing_package.yaml" "$CONTAINER:/config/packages/zone_testing_package.yaml"
  echo "  zone_testing_package.yaml → /config/packages/"
else
  docker exec "$CONTAINER" rm -f /config/packages/zone_testing_package.yaml 2>/dev/null || true
  echo "  removed zone_testing_package.yaml"
fi

echo "Restarting $CONTAINER..."
docker restart "$CONTAINER" >/dev/null

echo "Done — $CONTAINER is now in '$PROFILE' mode."
