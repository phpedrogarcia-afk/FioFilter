"""FioOS policy. Current T01 eligibility equals the hardened default.

Earlier FioOS restrictions on discovery/diagnostics/success are now also in
core, pending specific transform contracts. Preserve the project identity
without maintaining an independent duplicate policy table.
"""
from fiofilter.profiles.default import DefaultProfile


class FioOSProfile(DefaultProfile):
    @property
    def profile_id(self):
        return "fioos"
