from .ashby import AshbyAdapter
from .greenhouse import GreenhouseAdapter
from .himalayas import HimalayasAdapter
from .jobicy import JobicyAdapter
from .jsonld import JsonLdAdapter
from .lever import LeverAdapter
from .personio import PersonioAdapter
from .remotive import RemotiveAdapter
from .smartrecruiters import SmartRecruitersAdapter
from .workable import WorkableAdapter

ADAPTERS = {
    "ashby": AshbyAdapter(),
    "greenhouse": GreenhouseAdapter(),
    "himalayas": HimalayasAdapter(),
    "jobicy": JobicyAdapter(),
    "jsonld": JsonLdAdapter(),
    "lever": LeverAdapter(),
    "personio": PersonioAdapter(),
    "remotive": RemotiveAdapter(),
    "smartrecruiters": SmartRecruitersAdapter(),
    "workable": WorkableAdapter(),
}

__all__ = ["ADAPTERS"]
