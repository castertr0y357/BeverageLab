"""Soda recommendation engine subclass."""

from .base import BaseEngine

class SodaEngine(BaseEngine):
    """Engine specific to Soda Synthesis."""
    drink_type: str = 'SODA'
