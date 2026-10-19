from .ashby import AshbyAdapter
from .serpapi_google import SerpApiGoogleAdapter
from .greenhouse import GreenhouseAdapter
from .himalayas import HimalayasAdapter
from .jobicy import JobicyAdapter
from .jsonld import JsonLdAdapter
from .lever import LeverAdapter
from .personio import PersonioAdapter
from .publicfeeds import PublicFeedsAdapter
from .remoteok import RemoteOkAdapter
from .remotive import RemotiveAdapter
from .smartrecruiters import SmartRecruitersAdapter
from .weworkremotely import WeWorkRemotelyAdapter
from .workable import WorkableAdapter

ADAPTERS = {
    "ashby": AshbyAdapter(),
    "serpapi_google": SerpApiGoogleAdapter(),
    "greenhouse": GreenhouseAdapter(),
    "himalayas": HimalayasAdapter(),
    "jobicy": JobicyAdapter(),
    "jsonld": JsonLdAdapter(),
    "lever": LeverAdapter(),
    "personio": PersonioAdapter(),
    "publicfeeds": PublicFeedsAdapter(),
    "remoteok": RemoteOkAdapter(),
    "remotive": RemotiveAdapter(),
    "smartrecruiters": SmartRecruitersAdapter(),
    "weworkremotely": WeWorkRemotelyAdapter(),
    "workable": WorkableAdapter(),
}

__all__ = ["ADAPTERS"]
