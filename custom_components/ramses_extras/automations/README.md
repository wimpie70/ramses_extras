# Humidity Control Automation

This directory contains automation templates for Ramses Extras features.

## 📋 Current Implementation

The integration automatically creates YAML automations when features are enabled:

### ✅ **Automatic Automation Creation:**
- **Template-Based**: Uses YAML templates with variable substitution
- **Device-Aware**: Automatically creates automations for discovered devices
- **Feature-Driven**: Only creates automation when feature is enabled
- **User-Friendly**: No manual YAML editing required

### ✅ **Template System:**
- **Variable Substitution**: `{{ device_id }}` and `{{ device_id_underscore }}`
- **Configurable Location**: Specified in `const.py` feature configuration
- **Multiple Devices**: Creates separate automation for each device
- **Safe Integration**: Preserves existing user automations

## 🔧 **How It Works**

### **1. Feature Enablement:**
When user enables "Humidity Control" in integration settings:
1. Integration discovers Ramses devices
2. Loads automation template from `automations/humidity_control_template.yaml`
3. Substitutes device-specific variables
4. Appends to user's `config/automations.yaml`

### **2. Template Variables:**
```yaml
# Template uses these variables:
alias: "Dehumidifier Control - {{ device_id }}"           # e.g., "32:153289"
entity_id: "sensor.{{ device_id_underscore }}_humidity"   # e.g., "sensor.32_153289_humidity"
```

### **3. Generated Automation:**
For device `32:153289`, template becomes:
```yaml
alias: "Dehumidifier Control - 32:153289"
entity_id: "sensor.32_153289_indoor_humidity"
# ... etc
```

## 📊 **Template Features:**

### **✅ **Humidity Control Template:**
- **Smart Monitoring**: Watches indoor humidity vs thresholds
- **Automatic Control**: Turns dehumidifier on/off based on conditions
- **Fan Integration**: Sets fan speed appropriately
- **Manual Override**: Detects and respects user's manual control
- **Default Setup**: Sets sensible defaults (50% min, 75% max)

### **✅ **Generated Automations:**
- **Per-Device**: Separate automation for each discovered device
- **Threshold-Based**: Uses configurable min/max humidity values
- **Logging**: Comprehensive activity logging
- **Override Detection**: Respects manual user control

## 🎯 **Adding New Automation Features:**

### **1. Create Template:**
```yaml
# automations/new_feature_template.yaml
automation:
  - alias: "New Feature - {{ device_id }}"
    # ... template automation
```

### **2. Update const.py:**
```python
"new_feature": {
    "name": "New Feature",
    "category": "automations",
    "location": "automations/new_feature_template.yaml",
    # ... other config
}
```

### **3. Integration Automatically:**
- Detects when feature is enabled
- Loads template from specified location
- Creates device-specific automations
- Handles multiple devices automatically

## 🔍 **Troubleshooting**

### **Check Automation Creation:**
```bash
# Verify automations were created:
grep -A 5 "Dehumidifier Control" config/automations.yaml

# Check integration logs:
grep -i "humidity control" home-assistant.log
```

### **Manual Automation Management:**
```yaml
# Users can still customize by editing config/automations.yaml
# The integration will preserve customizations on restart
```

## 🚀 **Benefits of This Approach:**

- **✅ **No Manual Setup**: Users don't need to copy/modify YAML
- **✅ **Multi-Device**: Works automatically with any number of devices
- **✅ **Maintainable**: Templates are clean and reusable
- **✅ **Safe**: Preserves existing automations
- **✅ **Flexible**: Easy to add new automation features

**The automation system is fully integrated and ready to use!** 🎉
