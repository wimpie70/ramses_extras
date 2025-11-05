# Humidity Control Decision Flow Diagram
# Split into two separate automations to prevent interference with manual control

## System Overview (Mermaid)

```mermaid
flowchart TD
    subgraph Main Humidity Control Automation
        START1[Start<br/>Humidity Changes<br/>• Indoor Humidity<br/>• Outdoor Humidity<br/>• Offset Config<br/>• Max/Min Threshold] --> COND1{Switch ON?}

        COND1 -->|NO| END1[No Action<br/>Manual Control<br/>Preserved]
        COND1 -->|YES| D1{Indoor Humidity<br/>Greater than Max?}

        D1 -->|YES| I1{Absolute Indoor<br/>Greater than<br/>Outdoor + Offset?}
        D1 -->|NO| F1{Indoor Humidity<br/>Less than Min?}

        I1 -->|YES| E1[Set Fan to HIGH<br/>Binary Sensor ON]
        I1 -->|NO| J1[Set Fan to LOW<br/>Binary Sensor OFF]

        F1 -->|YES| K1{Absolute Indoor<br/>Less than<br/>Outdoor - Offset?}
        F1 -->|NO| H1[No Action<br/>Maintain State]

        K1 -->|YES| G1[Set Fan to HIGH<br/>Binary Sensor ON]
        K1 -->|NO| L1[Set Fan to LOW<br/>Binary Sensor OFF]

        E1 --> END1
        J1 --> END1
        G1 --> END1
        L1 --> END1
        H1 --> END1
    end

    subgraph Reset Automation
        START2[Start<br/>Switch OFF<br/>Event] --> ACTION2[Set Fan to AUTO<br/>Binary Sensor OFF]
        ACTION2 --> END2[END]
    end

    style START1 fill:#e1f5fe,color:#000000
    style COND1 fill:#fff3e0,color:#000000
    style D1 fill:#fff3e0,color:#000000
    style I1 fill:#fff3e0,color:#000000
    style F1 fill:#fff3e0,color:#000000
    style K1 fill:#fff3e0,color:#000000
    style E1 fill:#e8f5e8,color:#000000
    style J1 fill:#ffcdd2,color:#000000
    style G1 fill:#e8f5e8,color:#000000
    style L1 fill:#ffcdd2,color:#000000
    style H1 fill:#f3e5f5,color:#000000
    style END1 fill:#f5f5f5,color:#000000
    style START2 fill:#ffebee,color:#000000
    style ACTION2 fill:#ffebee,color:#000000
    style END2 fill:#f5f5f5,color:#000000
```

## State Transitions

| Current State | Condition | New State | Binary Sensor |
|---------------|-----------|-----------|---------------|
| **Main Humidity Control Automation** (Switch ON only) |
| Fan LOW/AUTO | Indoor RH > Max% + Indoor abs > Outdoor abs + Offset | Fan HIGH | ON |
| Fan LOW/AUTO | Indoor RH > Max% + Indoor abs <= Outdoor abs + Offset | Fan LOW | OFF |
| Fan HIGH/AUTO | Indoor RH < Min% + Indoor abs < Outdoor abs - Offset | Fan HIGH | ON |
| Fan HIGH/AUTO | Indoor RH < Min% + Indoor abs >= Outdoor abs - Offset | Fan LOW | OFF |
| Fan HIGH/LOW | Indoor RH Between Min/Max% | No Change | No Change |
| **Reset Automation** (Separate) |
| Any | Switch OFF Event | Fan AUTO | OFF |
| **Manual Control Preservation** |
| Any (Switch OFF) | Any Humidity Change | No Change | No Change |

## Key Entities Monitored

### Main Humidity Control Automation
- **Triggers:**
  - `sensor.indoor_relative_humidity_{device}` - Primary trigger for threshold comparisons (%)
  - `sensor.indoor_absolute_humidity_{device}` - For absolute humidity comparison logic (g/m³)
  - `sensor.outdoor_absolute_humidity_{device}` - For absolute humidity comparison logic (g/m³)
  - `number.absolute_humidity_offset_{device}` - Absolute offset value (g/m³)
  - `number.max_humidity_{device}` - Max relative humidity threshold (%)
  - `number.min_humidity_{device}` - Min relative humidity threshold (%)

- **Conditions:**
  - `switch.dehumidify_{device}` - Only runs when switch is ON

### Reset Automation (Separate)
- **Triggers:**
  - `switch.dehumidify_{device}` - Only triggers when switch is turned OFF (`to: "off"`)

- **Actions:**
  - Sets fan to AUTO when humidity control is disabled

- **Outputs (Not Triggers):**
  - `sensor.fan_speed_{device}` - Result of automation actions
  - `binary_sensor.dehumidifying_active_{device}` - Reflects current system state

- **Actions:**
  - `ramses_cc.send_command` - Control fan speed
  - Binary sensor state updates automatically

## Threshold Visualization (Mermaid)

```mermaid
graph TD
    subgraph Humidity Levels
        A[Min Relative Humidity<br/>65%]
        B[Acceptable Range<br/>No Action]
        C[Max Relative Humidity<br/>75%]
        D[Indoor: 80% RH<br/>15.0 g/m³ abs<br/>Outdoor: 8.0 g/m³ abs]
        E[Indoor: 80% RH<br/>15.0 g/m³ abs<br/>Outdoor: 14.0 g/m³ abs]
        F[Indoor: 55% RH<br/>6.0 g/m³ abs<br/>Outdoor: 12.0 g/m³ abs]
        G[Indoor: 62% RH<br/>7.0 g/m³ abs<br/>Outdoor: 8.0 g/m³ abs]
        H[Indoor: 70% RH<br/>10.0 g/m³ abs<br/>Outdoor: 9.0 g/m³ abs]
    end

    D --> I[Fan HIGH<br/>Binary ON<br/>80% > 75% + 15.0 > 8.0 + 0.5<br/>Active Dehumidification]
    E --> J[Fan LOW<br/>Binary OFF<br/>80% > 75% + 15.0 < 14.0 + 0.5<br/>Avoid Bringing Moisture]
    F --> K[Fan HIGH<br/>Binary ON<br/>55% < 65% + 6.0 < 12.0 - 0.5<br/>Active Humidification]
    G --> L[Fan LOW<br/>Binary OFF<br/>62% < 65% + 7.0 > 8.0 - 0.5<br/>Avoid Over-Humidifying]
    H --> M[No Action<br/>Current State<br/>70% Between 65-75%]

    A --- B --- C

    style A fill:#ffebee,color:#000000
    style B fill:#e8f5e8,color:#000000
    style C fill:#ffebee,color:#000000
    style D fill:#ffcdd2,color:#000000
    style E fill:#ffcdd2,color:#000000
    style F fill:#c8e6c9,color:#000000
    style G fill:#c8e6c9,color:#000000
    style H fill:#e1f5fe,color:#000000
    style I fill:#e8f5e8,color:#000000
    style J fill:#ffcdd2,color:#000000
    style K fill:#e8f5e8,color:#000000
    style L fill:#ffcdd2,color:#000000
    style M fill:#f3e5f5,color:#000000
```

This flow ensures:
1. **Energy Efficiency**: Only activates when necessary
2. **User Control**: Manual override capability
3. **Smart Operation**: No unnecessary changes within acceptable ranges
4. **Clear Feedback**: Binary sensor shows actual dehumidification status
