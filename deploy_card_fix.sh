#!/bin/bash
# Deploy updated hvac-fan-card.js to Home Assistant www directory

SOURCE_FILE="ramses_extras/custom_components/ramses_extras/features/hvac_fan_card/www/hvac_fan_card/hvac-fan-card.js"
DEST_FILE="/home/willem/docker_files/hass/config/www/ramses_extras/features/hvac_fan_card/hvac-fan-card.js"

echo "📦 Deploying updated hvac-fan-card.js..."
echo "   Source: $SOURCE_FILE"
echo "   Destination: $DEST_FILE"

sudo cp "$SOURCE_FILE" "$DEST_FILE"

if [ $? -eq 0 ]; then
    echo "✅ File deployed successfully!"
    echo ""
    echo "Next steps:"
    echo "1. Restart Home Assistant to load the updated card"
    echo "2. Clear browser cache (Ctrl+Shift+R)"
    echo "3. Verify the card loads without errors"
else
    echo "❌ Failed to deploy file"
    exit 1
fi
