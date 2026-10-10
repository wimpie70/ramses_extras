Issue 1019: HGI is accidentally polled once per day
This is independent of the zone-sensor problem.

Root cause
Devices without a specific schedule receive the fallback:



python
"DEFAULT": {
    Code._10E0: INTERVAL_DAILY,
}
polling.py:37-88

There is no HGI schedule, so an HGI gets the default daily 10E0.poll.

The poll manager builds a request to the device:

polling.py:386-420

For a real HGI ID such as 18:130140, build_rq_cmd() initially creates:



text
18:000730 -> 18:130140
helpers.py:68-90

Before queueing, the protocol replaces the placeholder source with the active gateway ID:

base.py:291-335

The resulting command becomes:



text
18:130140 -> 18:130140
That is an invalid RAMSES address set. I reproduced it directly:



text
built:   18:000730 18:130140 --:------
patched: 18:130140 18:130140 --:------
PacketInvalid: Bad frame: Invalid address set
The report appearing after approximately 24 hours is consistent with INTERVAL_DAILY.

Correct fix for issue 1019
The polling manager should never poll an HGI, local or foreign.

Preferred surgical fix:



python
if getattr(device, "_SLUG", None) == DevType.HGI:
    return {}
in resolve_schedule_for_device().

Alternatively, an explicit empty HGI schedule can be added, but an early return is stronger because it also prevents a custom/default merge from accidentally scheduling HGI polling later.

Tests should verify:

Local HGI resolves to no schedule.
Foreign HGI resolves to no schedule.
poll_due_commands() does not create or dispatch HGI commands.
Ordinary CTL/BDR/OTB polling remains unchanged.
A protocol-level check for same-source/destination commands could be added later as defensive hardening, but it is not the primary fix. The invalid command should never be created by polling.
