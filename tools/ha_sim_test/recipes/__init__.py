"""Recipe modules for ha_sim_test.

Each module in this package defines one or more recipes (either as a
:class:`ha_sim_test.base.Recipe` subclass or via the
:func:`@recipe <ha_sim_test.registry.recipe>` decorator).  Importing this
package (or calling :func:`ha_sim_test.registry.discover_recipes`) imports
every module here so recipes self-register.

Naming convention (suggested, not enforced):
    ``r<NN>_<short_slug>.py``  e.g. ``r06_zone_binding.py``,
    ``r29_bdr_appliance_control.py``.  The two-digit number matches the
    original RECIPE N comment.

The ``_example.py`` module demonstrates both registration styles and is the
only recipe here until the real ones are migrated.
"""

from __future__ import annotations
