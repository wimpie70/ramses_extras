// Device Detection Test for HVAC Fan Card
// Run this in browser console when HVAC card editor is open
// Copy and paste this entire script into browser console (F12)

console.log('=== RAMSES EXTRAS DEVICE DETECTION TEST ===');

// Check if we're in Home Assistant context
if (typeof hass !== 'undefined') {
  console.log('✅ Home Assistant context available');
  const h = hass;
} else if (window.hass) {
  console.log('✅ Home Assistant available via window.hass');
  const h = window.hass;
} else {
  console.log('❌ Home Assistant not available');
  console.log('Make sure you are on a page with access to HA data');
}

console.log('\n=== ENTITY ANALYSIS ===');
const allEntities = Object.keys(h.states);
console.log('Total entities:', allEntities.length);

// Find fan-related entities
const fanEntities = allEntities.filter(
  (e) =>
    e.toLowerCase().includes('fan') ||
    e.toLowerCase().includes('ventilator') ||
    e.toLowerCase().includes('hvac')
);
console.log('Fan-related entities:', fanEntities.length, ':', fanEntities);

// Find sensor entities
const sensorEntities = allEntities.filter((e) => e.startsWith('sensor.'));
console.log('Sensor entities:', sensorEntities.length);

// Detailed analysis of fan entities
console.log('\n=== FAN ENTITY DETAILS ===');
fanEntities.forEach((entity) => {
  const state = h.states[entity];
  console.log(`${entity}:`, {
    state: state.state,
    attributes: state.attributes,
    device_class: state.attributes?.device_class,
    unit: state.attributes?.unit_of_measurement,
  });
});

console.log('\n=== DEVICE REGISTRY ANALYSIS ===');
if (h.devices) {
  console.log('Device registry available, devices:', Object.keys(h.devices).length);

  Object.values(h.devices).forEach((device) => {
    console.log(`Device: ${device.name}`);
    console.log(`  ID: ${device.id}`);
    console.log(`  Model: ${device.model}`);
    console.log(`  Manufacturer: ${device.manufacturer}`);
    console.log(`  Area: ${device.area_id}`);

    // Check if device has fan-related entities
    const deviceEntities = allEntities.filter(
      (entityId) => entityId.includes(device.id) || entityId.includes(device.name)
    );

    const fanDeviceEntities = deviceEntities.filter(
      (e) => e.includes('fan') || e.includes('ventilator') || e.includes('hvac')
    );

    if (fanDeviceEntities.length > 0) {
      console.log(`  Fan entities: ${fanDeviceEntities.length}:`, fanDeviceEntities);
      console.log('  🔥 This might be the HvacVentilator device!');
    }
  });
} else {
  console.log('❌ Device registry not available');
}

console.log('\n=== ENTITY PATTERN ANALYSIS ===');
const patterns = {
  fanInfo: allEntities.filter((e) => e.includes('_fan_info')),
  fanMode: allEntities.filter((e) => e.includes('_fan_mode')),
  fanSpeed: allEntities.filter((e) => e.includes('_fan_speed')),
  indoorTemp: allEntities.filter((e) => e.includes('_indoor_temp')),
  outdoorTemp: allEntities.filter((e) => e.includes('_outdoor_temp')),
  supplyTemp: allEntities.filter((e) => e.includes('_supply_temp')),
  exhaustTemp: allEntities.filter((e) => e.includes('_exhaust_temp')),
  bypass: allEntities.filter((e) => e.includes('_bypass')),
};

console.log('Entity patterns found:');
Object.entries(patterns).forEach(([name, entities]) => {
  console.log(`  ${name}: ${entities.length} entities`);
  if (entities.length > 0) {
    console.log(`    Examples: ${entities.slice(0, 3).join(', ')}`);
  }
});

console.log('\n=== SUGGESTED DETECTION PATTERNS ===');
console.log('Based on the analysis above, the HvacVentilator detection should look for:');

// Find devices with fan_info + temperature entities
const hvacCandidates = [];
patterns.fanInfo.forEach((fanEntity) => {
  const baseName = fanEntity.replace('sensor.', '').replace('_fan_info', '');
  const deviceId = baseName.replace(/_/g, ':');

  // Check if this device has temperature entities
  const tempEntities = [
    ...patterns.indoorTemp,
    ...patterns.outdoorTemp,
    ...patterns.supplyTemp,
    ...patterns.exhaustTemp,
  ].filter((e) => e.includes(baseName));

  if (tempEntities.length > 0) {
    hvacCandidates.push({
      deviceId,
      fanEntity,
      tempEntities,
      totalEntities: tempEntities.length + 1,
    });
  }
});

console.log('HvacVentilator candidates:');
hvacCandidates.forEach((candidate) => {
  console.log(`  Device ${candidate.deviceId}:`);
  console.log(`    Fan entity: ${candidate.fanEntity}`);
  console.log(`    Temperature entities: ${candidate.tempEntities.length}`);
  console.log(`    Total entities: ${candidate.totalEntities}`);
});

console.log('\n=== RECOMMENDED DETECTION LOGIC ===');
if (hvacCandidates.length > 0) {
  console.log('✅ Found potential HvacVentilator devices!');
  console.log('Use this detection pattern in the editor:');
  console.log(`
// Look for entities like:
${hvacCandidates[0].fanEntity}
${hvacCandidates[0].tempEntities.slice(0, 2).join('\n')}

// Extract device ID: ${hvacCandidates[0].deviceId}
`);
} else {
  console.log('❌ No clear HvacVentilator patterns found');
  console.log('Check if Ramses RF integration is properly loaded');
  console.log('Or if the device has different entity naming patterns');
}

console.log('\n=== TEST COMPLETE ===');
console.log('Copy the suggested detection pattern to the editor code!');
