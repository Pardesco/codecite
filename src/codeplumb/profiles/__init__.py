from codeplumb.profiles.base import Heading, Profile, normalize_number
from codeplumb.profiles.generic import GenericProfile
from codeplumb.profiles.ibc import IBCProfile
from codeplumb.profiles.oac import OACProfile

PROFILES: dict[str, type[Profile]] = {
    "ibc": IBCProfile,
    "oac": OACProfile,
    "generic": GenericProfile,
}


def get_profile(name: str) -> Profile:
    try:
        return PROFILES[name]()
    except KeyError:
        raise ValueError(f"unknown profile '{name}'; available: {', '.join(PROFILES)}") from None


__all__ = ["PROFILES", "Heading", "Profile", "get_profile", "normalize_number"]
