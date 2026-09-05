from .ashby import AshbyAdapter
from .greenhouse import GreenhouseAdapter
from .himalayas import HimalayasAdapter
from .jobicy import JobicyAdapter
from .jsonld import JsonLdAdapter
from .lever import LeverAdapter
from .remotive import RemotiveAdapter
from .smartrecruiters import SmartRecruitersAdapter

ADAPTERS = {
    "ashby": AshbyAdapter(),
    "greenhouse": GreenhouseAdapter(),
    "himalayas": HimalayasAdapter(),
    "jobicy": JobicyAdapter(),
    "jsonld": JsonLdAdapter(),
    "lever": LeverAdapter(),
    "remotive": RemotiveAdapter(),
    "smartrecruiters": SmartRecruitersAdapter(),
}

__all__ = ["ADAPTERS"]
