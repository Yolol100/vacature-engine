"""Policy-free bulk vacancy ingestion."""

from .models import OBSERVATION_CONTRACT_VERSION, SourceSpec
from .runner import IngestionRunner

__all__ = ["OBSERVATION_CONTRACT_VERSION", "SourceSpec", "IngestionRunner"]
__version__ = "0.7.0"
