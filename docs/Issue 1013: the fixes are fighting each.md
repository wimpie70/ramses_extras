Issue 1013: the fixes are fighting each other
What PR 1096 fixed
PR 1096 restored two pieces of old eavesdropping behavior:

A TRV already bound as an actuator may also be the zone sensor.
Sensor matching uses recent, temporally correlated 30C9 traffic.
The representative sensor is attached using is_sensor=True. eavesdropper.py:562-665

The TRV-broadcast path also explicitly acknowledges that a TRV may serve both roles. eavesdropper.py:687-725

Its focused test passes locally:



text
2 passed
The user’s evidence proves PR 1096 works initially
The early Part.schema.txt contained discovered TRV sensors, including:



yaml
'07':
  sensor: 04:034722
'06':
  sensor: 04:056675
'00':
  sensor: 04:034720
0B:
  sensor: 04:034692
08:
  sensor: 04:208998
The final schema retained the dedicated thermostats:



yaml
'01':
  sensor: 22:012299
'03':
  sensor: 34:058721
But every TRV-based sensor: assignment disappeared.

That is not an ambiguous RF inference failure. It is a deterministic ramses_cc transformation.

Where ramses_cc removes the result
sync_learned_topology() first correctly copies the discovered sensor from the learned RF schema:

schemas.py:1619-1640

It then runs the issue-813 sanitization logic. That logic assumes a TRV should not be both sensor and actuator:

If the sensor is a TRV and no dedicated thermostat exists, it sets sensor = None.
If there is no actuator list, it creates one and sets sensor = None.
If the TRV appears in both roles, it again clears sensor.
schemas.py:1686-1771

There is also a unit test explicitly encoding the incorrect assumption:

“A TRV is never a zone sensor”

test_schemas.py:2389-2419

Evohome contradicts that assumption: a TRV is physically an actuator but its temperature sensor can also be selected as the representative zone sensor.

Why manually configured systems still work
Issue 887 added an exception for sensors already present in the original config schema:

schemas.py:1593-1604

That explains the observed split:

Manually configured sensor: 04:xxxxxx survives.
Automatically learned sensor: 04:xxxxxx is removed.
Therefore manually configured systems have current_temperature; clean discovery does not.
Why the issue-976 fix should remain
The current ingestion path only routes a TRV’s 30C9 to the parent zone when it is:

The designated parent.sensor, or
The sole actuator and no sensor is defined.
ingestion.py:344-377

That is the correct protection against issue 976’s fluctuating temperatures.

We should not restore the old “any actuator updates the zone” behavior. Instead, we should preserve the correctly discovered representative sensor.

Correct fix for issue 1013
Change the ramses_cc normalization rule to model the two roles independently:

A TRV must remain in actuators.
A TRV may simultaneously remain in sensor.
If a dedicated thermostat (01:, 22:, 34:) exists, it should still take priority as sensor.
A user-authored sensor must remain authoritative.
A learned representative TRV must no longer be nulled merely because it is also an actuator.
In practical terms:

Keep the code that adds the TRV to actuators.
Remove the assignments that set the learned TRV sensor to None.
Remove or rewrite the duplicate-role clearing block.
Preserve the dedicated-thermostat promotion behavior.
Reverse the incorrect unit test at lines 2389–2419.
This resolves issue 1013 without undoing issue 813, 887, or 976.
---
Historical evidence
Issue 813 did not decide that TRVs cannot be sensors
Issue 813 concerned:

Devices going into the wrong orphan list.
Dedicated thermostats being placed under actuators.
A TRV incorrectly occupying sensor when a dedicated thermostat existed.
The reported correction was:



yaml
sensor: 34:058721
actuators:
  - 04:056679
  - 04:219929
That establishes that a dedicated thermostat should take priority. It does not establish that a TRV can never be a representative sensor when there is no dedicated thermostat.

The actual issue-813 PRs addressed orphan routing and thermostat placement—not a general prohibition on TRV sensors.

Issue 887 explicitly expected the dual role
The user showed the old working schema:



yaml
sensor: 04:056673
actuators:
  - 04:034720
  - 04:056673
They reported it as a bug that saving the schema changed sensor to null.

That issue was closed after explicitly configured TRV sensors were preserved. So the accepted behavior already was: a TRV may be listed in both fields.

PR 1070 relies on the dual role
The regression test for issue 976 contains this exact schema:



json
{
  "sensor": "04:005646",
  "actuators": [
    "04:005646",
    "04:005647"
  ]
}
That is deliberate:

sensor identifies the authoritative source for current_temperature.
actuators identifies devices controlling heat output.
One physical TRV can perform both roles.
The issue-976 fix uses zone.sensor to prevent the other TRV from overwriting the zone temperature. Removing the representative TRV from sensor defeats that protection.

PR 1096 also deliberately expects the dual role
Its expected schema is:



json
{
  "sensor": "04:200001",
  "actuators": [
    "04:200001",
    "04:200002"
  ]
}
PR 1096 was approved and merged specifically to recover the representative TRV.

Current ramses_rf model supports it
The schema validates sensor and actuators independently. It does not require them to be disjoint. schemas.py:196-215

The topology rules explicitly permit TrvActuator as both:



python
SZ_ACTUATORS: ("BdrSwitch", "TrvActuator", "UfhCircuit")
SZ_SENSOR: ("Controller", "Thermostat", "TrvActuator")
topology.py:416-453

When loading a zone, ramses_rf registers the sensor first, then independently registers all actuators. Therefore the same device ID may occupy both roles. zones.py:610-650

What went wrong in ramses_cc
The current test claims:

“A TRV is never a zone sensor — it measures valve position, not room temperature.”

That statement is technically incorrect: Evohome TRVs do measure temperature, and one can be selected as the representative zone sensor.

test_schemas.py:2389-2419

The corresponding normalization code overcorrected issue 813 by treating sensor and actuators as mutually exclusive. schemas.py:1686-1771

The correct distinction is:

Dedicated thermostat present: promote it to sensor; all TRVs remain actuators.
Representative TRV discovered: preserve it as sensor and ensure it is also in actuators.
Other TRVs: actuators only.
User explicitly selected a sensor: preserve that choice.
Refined HA simulator assertions
These assertions are therefore correct:



text
Confirms the config entry retains the representative TRV as sensor.
Confirms the same TRV also remains in actuators.
I would make them more explicit:

The discovered representative TRV is persisted as the zone’s authoritative sensor.
The representative TRV remains in actuators, because its actuator role is independent.
Other TRVs remain actuators but do not become the sensor.
A dedicated thermostat, when present, takes priority over a TRV as sensor.
Only the designated sensor updates zone current_temperature.
The relationship survives topology sync, save, and reload.
