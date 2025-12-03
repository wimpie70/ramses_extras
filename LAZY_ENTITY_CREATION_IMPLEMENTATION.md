# Lazy Entity Creation Implementation Plan

## Overview

This document outlines the implementation of **Option 1: Lazy Entity Creation** with **Feature-Specific Config Flows** to solve the entity creation timing issue in Ramses Extras.

## Problem Statement

**Current Issue**: When enabling features, entities are created for all compatible devices, but users don't know which devices they actually need until they add cards to the dashboard and make selections.

**Solution**: Entities are created only when users explicitly select devices through:

- **Card-based features**: Entity creation triggered by card configuration
- **Automation-only features**: Entity creation triggered by feature-specific config flow

## Architecture Overview

### New Configuration Flow Structure

```
🏠 Main Config Flow                    🔧 Feature Config Submenu
┌─────────────────┐                  ┌──────────────────┐
│ Features:       │  [Configure]     │ {Feature Name}   │
│                 │  ───────────────>│ Device Selection:│
│ ☑️ Humidity      │                  │ ☑️ Device A      │
│ ☑️ HVAC Fan      │                  │ ☑️ Device B      │
│                 │  <────────────── │ ☐ Device C      │
│ [Save]          │   [Save & Return]│ [Save & Return]  │
└─────────────────┘                  └──────────────────┘
       ↑                                           │
       │              State preserved              │
       └───────────────────────────────────────────┘
```

### Entity Creation Flow

| Feature Type        | Trigger                                   | Entity Creation |
| ------------------- | ----------------------------------------- | --------------- |
| **Card-based**      | User adds card + selects device           | Immediate       |
| **Automation-only** | User configures feature + selects devices | On save         |
| **Complex**         | Both card AND config flow                 | Both triggers   |

## Implementation Phases

### Phase 1: Core Framework Updates

- Enhanced Feature Registry with config flow support
- Generic Device Selection Framework (feature-agnostic)
- Lazy Entity Creation Manager (reusable patterns only)

**⚠️ Important**: Framework components must remain feature-agnostic and reusable. Any feature-specific logic should be implemented in the individual feature folders, not in the framework.

### Phase 2: Config Flow System

- Feature Config Flow Base Class
- Enhanced Main Config Flow with "Configure" buttons
- Navigation between main flow and submenus

### Phase 3: Feature Migration

- Update humidity control with config flow
- Keep HVAC fan card as card-only
- Add optional config flow to hello world card

### Phase 4: Entity Lifecycle Updates

- Platform Setup for lazy creation
- Selective Entity Factory
- Cleanup for unselected devices

### Phase 5: Clean Implementation

- Direct migration to new system
- No legacy compatibility concerns
- Full implementation of lazy creation

## Key Benefits

✅ **Solves timing issue**: Entities created only when actually needed
✅ **Maintains feature-centric architecture**: Each feature owns its configuration
✅ **User control**: Clear device selection for automation features
✅ **Intuitive UX**: Familiar HA config flow pattern with submenus
✅ **Clean implementation**: No legacy compatibility overhead
✅ **Scalable**: Easy to add new features with their own config flows

## Implementation Progress

### Phase 1: Core Framework Updates [COMPLETED ✅]

- [x] Enhanced Feature Registry with config flow support
- [x] Generic Device Selection Framework (feature-agnostic)
- [x] Lazy Entity Creation Manager (reusable patterns only)

### Phase 2: Config Flow System [COMPLETED ✅]

- [x] Feature Config Flow Base Class
- [x] Enhanced Main Config Flow with "Configure" buttons
- [x] Navigation between main flow and submenus
- [x] Configuration options display showing device selection requirements

### Phase 3: Feature Migration [PENDING]

- [ ] Update humidity control with config flow
- [ ] Keep HVAC fan card as card-only
- [ ] Add optional config flow to hello world card

### Phase 4: Entity Lifecycle Updates [PENDING]

- [ ] Platform Setup for lazy creation
- [ ] Selective Entity Factory
- [ ] Cleanup for unselected devices

### Phase 5: Clean Implementation [PENDING]

- [ ] Direct migration to new system
- [ ] No legacy compatibility concerns
- [ ] Full implementation of lazy creation

## Implementation Steps

1. **✅ Plan approved** - Implementation plan reviewed and approved
2. **🔄 Starting Phase 1**: Framework foundation
3. **Implement incrementally**: Test each phase before proceeding
4. **Validate**: Ensure clean implementation without legacy concerns

This architecture provides a clean, scalable solution that maintains the feature-centric design while solving the entity creation timing challenge.
