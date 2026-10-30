# licenses.py — permissive-license policy for the archived corpus.
# Author: Vaibhav (Vaibhav Agarwal) — the archiver
# Contact: nekomeowpurr@proton.me | GitHub: https://github.com/thisisforlearn/archive
# Project authority: Vaibhav holds final decision power over this project.
# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

# Canonical FMA license class labels (dataset card of benjamin-paine/free-music-archive-full).
FMA_LICENSES: dict[int, tuple[str, str]] = {
    0: ("CC-BY 1.0", "https://creativecommons.org/licenses/by/1.0/"),
    1: ("CC-BY 2.0", "https://creativecommons.org/licenses/by/2.0/"),
    2: ("CC-BY 2.5", "https://creativecommons.org/licenses/by/2.5/"),
    3: ("CC-BY 3.0", "https://creativecommons.org/licenses/by/3.0/"),
    4: ("CC-BY 4.0", "https://creativecommons.org/licenses/by/4.0/"),
    5: ("CC-BY-NC 2.0", "https://creativecommons.org/licenses/by-nc/2.0/"),
    6: ("CC-BY-NC 2.1", "https://creativecommons.org/licenses/by-nc/2.1/"),
    7: ("CC-BY-NC 2.5", "https://creativecommons.org/licenses/by-nc/2.5/"),
    8: ("CC-BY-NC 3.0", "https://creativecommons.org/licenses/by-nc/3.0/"),
    9: ("CC-BY-NC 4.0", "https://creativecommons.org/licenses/by-nc/4.0/"),
    10: ("CC-BY-NC-ND 2.0", "https://creativecommons.org/licenses/by-nc-nd/2.0/"),
    11: ("CC-BY-NC-ND 2.1", "https://creativecommons.org/licenses/by-nc-nd/2.1/"),
    12: ("CC-BY-NC-ND 2.5", "https://creativecommons.org/licenses/by-nc-nd/2.5/"),
    13: ("CC-BY-NC-ND 3.0", "https://creativecommons.org/licenses/by-nc-nd/3.0/"),
    14: ("CC-BY-NC-ND 4.0", "https://creativecommons.org/licenses/by-nc-nd/4.0/"),
    15: ("CC-BY-NC-SA 2.0", "https://creativecommons.org/licenses/by-nc-sa/2.0/"),
    16: ("CC-BY-NC-SA 2.1", "https://creativecommons.org/licenses/by-nc-sa/2.1/"),
    17: ("CC-BY-NC-SA 2.5", "https://creativecommons.org/licenses/by-nc-sa/2.5/"),
    18: ("CC-BY-NC-SA 3.0", "https://creativecommons.org/licenses/by-nc-sa/3.0/"),
    19: ("CC-BY-NC-SA 4.0", "https://creativecommons.org/licenses/by-nc-sa/4.0/"),
    20: ("CC-BY-ND 2.0", "https://creativecommons.org/licenses/by-nd/2.0/"),
    21: ("CC-BY-ND 2.5", "https://creativecommons.org/licenses/by-nd/2.5/"),
    22: ("CC-BY-ND 3.0", "https://creativecommons.org/licenses/by-nd/3.0/"),
    23: ("CC-BY-ND 4.0", "https://creativecommons.org/licenses/by-nd/4.0/"),
    24: ("CC-BY-SA 2.0", "https://creativecommons.org/licenses/by-sa/2.0/"),
    25: ("CC-BY-SA 2.5", "https://creativecommons.org/licenses/by-sa/2.5/"),
    26: ("CC-BY-SA 3.0", "https://creativecommons.org/licenses/by-sa/3.0/"),
    27: ("CC-BY-SA 4.0", "https://creativecommons.org/licenses/by-sa/4.0/"),
    28: ("CC-NC-Sampling+ 1.0", "https://creativecommons.org/licenses/nc-sampling+/1.0/"),
    29: ("CC-Sampling+ 1.0", "https://creativecommons.org/licenses/sampling+/1.0/"),
    30: ("FMA Sound Recording Common Law", "https://freemusicarchive.org/Sound_Recording_Common_Law"),
    31: ("Free Art License", "https://artlibre.org/licence/lal/en"),
    32: ("Free Music Philosophy (FMP)", "https://irdial.com/free_and_easy.htm"),
    33: ("CC0 1.0", "https://creativecommons.org/publicdomain/zero/1.0/"),
    34: ("Public Domain", "https://creativecommons.org/publicdomain/zero/1.0/"),
}


def license_name(code: int) -> str:
    return FMA_LICENSES.get(int(code), (f"Unknown license code {code}", ""))[0]


def license_url(code: int) -> str:
    return FMA_LICENSES.get(int(code), ("", ""))[1]


class PermitPolicy:
    """Decides which tracks are archive-able.

    Policies:
      permissive — license-name analysis only (default; flags recorded in manifest).
      strict     — permissive name AND FMA flags must agree (commercial+derivatives).
      flags      — FMA allow_commercial_use/allow_derivatives flags only.
      all        — everything (NOT recommended).
    """

    def __init__(self, policy: str = "permissive", include_sampling: bool = False) -> None:
        self.policy = policy
        self.include_sampling = include_sampling

    @staticmethod
    def _flags_ok(flags) -> bool:
        try:
            return int(flags[0]) == 1 and int(flags[1]) == 1
        except Exception:
            return True

    def _name_ok(self, name: str) -> bool:
        name = name.lower()
        if "common law" in name:
            return False
        if "nc" in name or "nd" in name:
            return False
        if "sampling+" in name:
            return bool(self.include_sampling)
        return (
            name.startswith("cc-by") or "cc0" in name or "public domain" in name
            or "free art" in name or "free music philosophy" in name
        )

    def check(self, code: int, flags) -> bool:
        name = license_name(code).lower()
        if self.policy == "all":
            return True
        if self.policy == "flags":
            return self._flags_ok(flags)
        ok = self._name_ok(name)
        if self.policy == "strict":
            ok = ok and self._flags_ok(flags)
        return ok


def attribution_line(cfg) -> str:
    """Standard archiver-credit + original-source encouragement line."""
    return (
        f"Uploaded by {cfg.archivist_name} (the archiver) — {cfg.archivist_email} "
        f"— {cfg.archivist_github}. Archived from Free Music Archive "
        f"(https://freemusicarchive.org) — please check out and support the original artists "
        f"at their source pages."
    )
