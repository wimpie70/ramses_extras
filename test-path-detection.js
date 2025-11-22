/**
 * Test file for environment-aware path detection
 * This demonstrates how the new path detection works
 */

// Import the paths module
import {
  getCurrentEnvironment,
  getEnvironmentDebugInfo,
  getAllPaths,
  HELPER_PATHS,
  getHelperPath,
} from './custom_components/ramses_extras/www/helpers/paths.js';

console.log('🧪 Testing Environment-Aware Path Detection\n');

// Test 1: Check current environment
console.log('📍 Current Environment:', getCurrentEnvironment());
console.log('📝 Environment Description:', getEnvironmentDebugInfo());

// Test 2: Show all paths
console.log('\n📂 All Paths:');
const allPaths = getAllPaths();
console.log(JSON.stringify(allPaths, null, 2));

// Test 3: Test helper path resolution
console.log('\n🔗 Helper Path Examples:');
console.log('CARD_COMMANDS:', HELPER_PATHS.CARD_COMMANDS);
console.log('CARD_SERVICES:', HELPER_PATHS.CARD_SERVICES);

// Test 4: Test manual path resolution
console.log('\n🛠️ Manual Path Resolution:');
console.log('card-commands.js:', getHelperPath('card-commands.js'));
console.log('card-services.js:', getHelperPath('card-services.js'));

// Test 5: Test environment override
console.log('\n⚙️ Testing Environment Override:');
import { setEnvironment } from './custom_components/ramses_extras/www/helpers/paths.js';

// Test with production environment
setEnvironment('production');
console.log('Production paths:');
console.log('CARD_COMMANDS:', HELPER_PATHS.CARD_COMMANDS);

// Test with test environment
setEnvironment('test');
console.log('Test paths:');
console.log('CARD_COMMANDS:', HELPER_PATHS.CARD_COMMANDS);

// Reset to auto-detection (just clear the global override)
if (typeof window !== 'undefined') {
  delete window.RAMSES_EXTRAS_ENV;
}

console.log('\n✅ Path detection test completed!');
