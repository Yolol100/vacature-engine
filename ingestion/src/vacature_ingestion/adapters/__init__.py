from .ashby import AshbyAdapter
from .greenhouse import GreenhouseAdapter
from .jsonld import JsonLdAdapter
from .lever import LeverAdapter
from .smartrecruiters import SmartRecruitersAdapter

ADAPTERS = {
    "ashby": AshbyAdapter(),
    "greenhouse": GreenhouseAdapter(),
    "jsonld": JsonLdAdapter(),
    "lever": LeverAdapter(),
    "smartrecruiters": SmartRecruitersAdapter(),
}

__all__ = ["ADAPTERS"]
